"""Selector v3 — Option α (persona/pose anchor only).

Designed for the IMC-plan-driven pipeline. Each scene picks N reference
images that match the scene's *persona* (age/gender) and have *clean
editorial poses*. The scene's setting/mood/tone/visual are deliberately
NOT used in scoring — those are injected directly into the image-gen
prompt and synthesized by the LLM.

Why this split:
- The 5,774-record SNS pool was crawled from brand-follower posts; it
  rarely contains scene-specific content like "Jamsil baseball stadium
  cheer line" or "Waterbomb backstage."
- Trying to anchor those scenes to ref labels would force bad matches.
- Better: ref provides pose/composition/persona-look anchor; LLM fills
  setting/mood/styling from the campaign brief text.

Usage:
    from sns_labeling.imc_plan_loader import load_campaign_spec
    from sns_labeling.selector_v3 import select_for_scene
    spec = load_campaign_spec("path/to/imc_plan.json")
    used: set[str] = set()
    for scene in spec.scenes:
        persona = spec.persona_by_id(scene.persona_match) or spec.personas[0]
        refs = select_for_scene(scene, persona, n=6, used_handles=used)
        for r in refs:
            used.add(r["handle"])
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable, Optional

import numpy as np

# Allow `python selector_v3.py ...` direct invocation by ensuring scripts/
# is on sys.path before the relative import.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from sns_labeling.imc_plan_loader import Persona, Scene
from project_paths import PROJECT_ROOT, SOURCE_DIR, resolve_project_path


DEFAULT_POOL = SOURCE_DIR / "labels_marketing_index.jsonl"


# ---------- weights ---------------------------------------------------------

W_PERSONA_DEMO = 0.50
W_POSE_QUALITY = 0.35
W_LIFESTYLE_HINT = 0.15


# ---------- discrete pose scoring -------------------------------------------

# Higher = better editorial anchor. Negative = penalty.
POSE_QUALITY = {
    "full body shot": 1.00,
    "knee shot": 0.85,
    "half body shot": 0.65,
    "upper body shot": 0.55,
    "close up shot": 0.30,
    "headshot": 0.20,
    "back shot": 0.40,
    "side shot": 0.55,
    "mirror selfie": -0.50,
    "selfie": -0.30,
    "group shot": -0.40,
}

# Composition/framing bonuses; multiplied lightly.
COMPOSITION_BONUS = {
    "wide shot": 0.10,
    "long shot": 0.10,
    "full shot": 0.10,
    "mid shot": 0.05,
    "close-up": -0.05,
}

# Hard pose negatives — surface as penalty in scoring.
POSE_NEGATIVES = {
    "mirror selfie", "selfie", "peace sign",
    "duck face", "v sign", "heart sign", "finger heart",
}


# ---------- age-group mapping (pool labels → numeric range) ------------------

# Pool uses VLM-labeled age groups. Map to approximate numeric range.
AGE_GROUP_TO_RANGE = {
    "child": (0, 12),
    "teen": (13, 19),
    "youth": (15, 24),
    "young adult": (20, 30),
    "adult": (25, 40),
    "middle aged": (35, 55),
    "senior": (55, 99),
    "20s": (20, 29),
    "30s": (30, 39),
}


def _age_overlap(persona: Persona, label: Optional[str]) -> float:
    """0~1 overlap between persona age range and pool age-group range."""
    if persona.age_min is None or persona.age_max is None or not label:
        return 0.5  # neutral when unknown
    rng = AGE_GROUP_TO_RANGE.get(str(label).strip().lower())
    if not rng:
        return 0.3
    pa, pb = persona.age_min, persona.age_max
    ra, rb = rng
    inter = max(0, min(pb, rb) - max(pa, ra))
    union = max(1, max(pb, rb) - min(pa, ra))
    return inter / union


def _gender_match(persona_gender: Optional[str], rec_gender: Optional[str]) -> float:
    """1.0 exact match, 0.5 either side missing, 0.0 mismatch."""
    pg = (persona_gender or "").lower() or None
    rg = (rec_gender or "").lower() or None
    if pg is None or rg is None:
        return 0.5
    return 1.0 if pg == rg else 0.0


# ---------- per-record scoring -----------------------------------------------

def _str(v) -> str:
    """Coerce label fields (sometimes list, sometimes string, sometimes None)."""
    if v is None:
        return ""
    if isinstance(v, list):
        return ", ".join(str(x) for x in v if x).strip()
    return str(v).strip()


def _score_pose(rec: dict) -> tuple[float, list[str]]:
    m = rec.get("model") or {}
    bg = rec.get("background") or {}
    pose = _str(m.get("pose")).lower()
    comp = _str(bg.get("shooting composition")).lower()
    n_people = _str(m.get("number of people")).lower()
    notes: list[str] = []

    base = POSE_QUALITY.get(pose, 0.30)
    notes.append(f"pose:{pose}={base:+.2f}")
    if pose in POSE_NEGATIVES:
        base += -0.25
        notes.append("pose-negative")

    bonus = COMPOSITION_BONUS.get(comp, 0.0)
    if bonus:
        notes.append(f"comp:{comp}={bonus:+.2f}")

    if "single" in n_people:
        bonus += 0.10
        notes.append("single+0.10")
    elif "group" in n_people or "multiple" in n_people:
        bonus -= 0.10
        notes.append("group-0.10")

    # Clip to [0, 1] window (negative pose still hurts via base)
    raw = max(-0.50, min(1.10, base + bonus))
    # Map to 0~1 by clipping negatives to 0 (we lose info on bad poses
    # but they're filtered later via threshold)
    return max(0.0, raw), notes


def _score_persona_demo(rec: dict, persona: Persona) -> tuple[float, list[str]]:
    m = rec.get("model") or {}
    age_label = _str(m.get("age group")) or None
    rec_gender = _str(m.get("gender")) or None

    age_s = _age_overlap(persona, age_label)
    gen_s = _gender_match(persona.gender, rec_gender)
    notes = [f"age:{age_label}={age_s:.2f}", f"gender:{rec_gender}={gen_s:.2f}"]
    return (age_s * 0.6 + gen_s * 0.4), notes


def _persona_text(persona: Persona) -> str:
    """Persona as natural-language text for embedding query (lifestyle hint)."""
    bits = [
        f"persona: {persona.name}.",
        f"demographics: {persona.demo}." if persona.demo else "",
        f"jobs to be done: {' / '.join(persona.jtbd[:3])}." if persona.jtbd else "",
        f"situations: {' / '.join(persona.situations[:2])}." if persona.situations else "",
    ]
    return " ".join(b for b in bits if b)


def _record_text_for_embedding(rec: dict) -> str:
    """Mirror embed_pool.record_text — same encoding so cache aligns."""
    m = rec.get("model") or {}
    bg = rec.get("background") or {}
    st = rec.get("styling") or {}

    def _v(x):
        if isinstance(x, list):
            x = ", ".join(str(i) for i in x if i)
        return str(x or "unspecified").strip() or "unspecified"

    return (f"pose: {_v(m.get('pose'))}. expression: {_v(m.get('expression'))}. "
            f"gaze: {_v(m.get('gaze direction'))}. mood: {_v(bg.get('mood'))}. "
            f"location: {_v(bg.get('location'))}. style: {_v(st.get('fashion style'))}. "
            f"coordination: {_v(st.get('coordination method'))}.")


def _record_image_path(rec: dict, pool_path: Path) -> str | None:
    raw = (rec.get("image") or {}).get("path")
    if not raw:
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = resolve_project_path(p)
    return str(p)


def _embedding_lifestyle_scores(records: list[dict],
                                  persona: Persona) -> dict[str, float]:
    """Cosine similarity of persona text vs cached record embeddings.

    Falls back to {} when embedding cache or API is unavailable; caller treats
    missing keys as 0.0 (lifestyle hint becomes 0, only persona/pose drive).
    """
    try:
        from sns_labeling.embedder import (
            load_cache, embed_text, cosine_similarity,
        )
    except Exception:
        return {}
    id_to_row, matrix = load_cache()
    if not id_to_row or matrix.size == 0:
        return {}
    try:
        q = embed_text(_persona_text(persona))
    except Exception as e:
        print(f"[selector_v3] embed_text failed: {type(e).__name__}: {e}")
        return {}
    sims = cosine_similarity(q, matrix)
    out: dict[str, float] = {}
    for rec in records:
        pid = (rec.get("account") or {}).get("post_id")
        if pid and pid in id_to_row:
            out[pid] = float(sims[id_to_row[pid]])
    return out


# ---------- main API ---------------------------------------------------------

def select_for_scene(
    scene: Scene,
    persona: Persona,
    *,
    n: int = 6,
    used_handles: Optional[set[str]] = None,
    pool_path: Path | str = DEFAULT_POOL,
    brand_filter: Optional[Iterable[str]] = None,
    confidence_floor: float = 0.7,
    use_embedding: bool = True,
) -> list[dict]:
    """Pick N references for one Scene + Persona.

    Score = 0.50 * persona_demo + 0.35 * pose_quality + 0.15 * lifestyle_hint

    The scene's tone/mood/visual/location is INTENTIONALLY ignored — those
    cues belong in the image-gen prompt, not here.

    used_handles is mutated by caller across scenes to enforce cross-scene
    handle uniqueness. This selector itself only reads it.
    """
    used = set(used_handles or set())
    bf = set(brand_filter) if brand_filter else None

    pool_path = Path(pool_path)
    if not pool_path.exists():
        raise FileNotFoundError(pool_path)

    # Pass 1: load pool, apply hard filters, compute discrete partial scores.
    candidates: list[tuple[float, float, list[str], dict]] = []
    # tuple: (persona_demo_score, pose_quality_score, reasons, rec)
    with pool_path.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            a = rec.get("account") or {}
            handle = a.get("handle")
            if handle and handle in used:
                continue
            if bf and a.get("brand") not in bf:
                continue
            ft = rec.get("free_text") or {}
            conf = ft.get("_confidence")
            if conf is not None and conf < confidence_floor:
                continue

            pd, pd_notes = _score_persona_demo(rec, persona)
            if pd <= 0:
                # gender mismatch when both known → drop
                continue

            pq, pq_notes = _score_pose(rec)
            reasons = pd_notes + pq_notes
            if conf is not None:
                reasons.append(f"conf={conf}")
            candidates.append((pd, pq, reasons, rec))

    if not candidates:
        return []

    # Pass 2: embedding-based lifestyle hint (optional).
    pool_records = [t[3] for t in candidates]
    emb_map = (_embedding_lifestyle_scores(pool_records, persona)
               if use_embedding else {})

    # Pass 3: combine into total score.
    scored: list[tuple[float, list[str], dict]] = []
    for pd, pq, reasons, rec in candidates:
        pid = (rec.get("account") or {}).get("post_id")
        emb = emb_map.get(pid, 0.0) if pid else 0.0
        emb_pos = max(0.0, emb)
        total = (W_PERSONA_DEMO * pd
                 + W_POSE_QUALITY * pq
                 + W_LIFESTYLE_HINT * emb_pos)
        full_reasons = list(reasons)
        if emb_map:
            full_reasons.append(f"embed={emb:+.3f}")
        full_reasons.append(
            f"score=PD×{pd:.2f}+PQ×{pq:.2f}+LH×{emb_pos:.2f}={total:.3f}"
        )
        scored.append((total, full_reasons, rec))

    scored.sort(key=lambda t: -t[0])

    # Pass 4: per-handle dedup within scene + take top-n.
    seen_handles: set[str] = set()
    selected: list[tuple[float, list[str], dict]] = []
    for s, rs, rec in scored:
        h = (rec.get("account") or {}).get("handle")
        if h and h in seen_handles:
            continue
        if h:
            seen_handles.add(h)
        selected.append((s, rs, rec))
        if len(selected) >= n:
            break

    return [
        {
            "rank": i + 1,
            "score": round(s, 4),
            "matched_axes": rs,
            "post_id": (rec.get("account") or {}).get("post_id"),
            "handle": (rec.get("account") or {}).get("handle"),
            "brand": (rec.get("account") or {}).get("brand"),
            "post_url": (rec.get("account") or {}).get("post_url"),
            "image": _record_image_path(rec, pool_path),
            "model": rec.get("model"),
            "background": rec.get("background"),
            "styling": rec.get("styling"),
            "free_text": rec.get("free_text"),
            "confidence": (rec.get("free_text") or {}).get("_confidence"),
            "scene_id": scene.slug,
            "persona_id": persona.id,
        }
        for i, (s, rs, rec) in enumerate(selected)
    ]


def select_for_campaign(
    spec,  # CampaignSpec
    *,
    n_per_scene: int = 6,
    pool_path: Path | str = DEFAULT_POOL,
    brand_filter: Optional[Iterable[str]] = None,
    confidence_floor: float = 0.7,
    use_embedding: bool = True,
) -> dict[str, list[dict]]:
    """Convenience: pick refs for all scenes in a CampaignSpec.

    Returns {scene_slug: [refs...]}. Cross-scene handle uniqueness enforced.
    """
    used: set[str] = set()
    out: dict[str, list[dict]] = {}
    for scene in spec.scenes:
        persona = spec.persona_by_id(scene.persona_match)
        if persona is None and spec.personas:
            persona = spec.personas[0]
        if persona is None:
            out[scene.slug] = []
            continue
        refs = select_for_scene(
            scene, persona,
            n=n_per_scene,
            used_handles=used,
            pool_path=pool_path,
            brand_filter=brand_filter,
            confidence_floor=confidence_floor,
            use_embedding=use_embedding,
        )
        out[scene.slug] = refs
        for r in refs:
            if r.get("handle"):
                used.add(r["handle"])
    return out


__all__ = [
    "select_for_scene",
    "select_for_campaign",
    "W_PERSONA_DEMO", "W_POSE_QUALITY", "W_LIFESTYLE_HINT",
]


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) < 2:
        print("usage: python selector_v3.py <imc_plan.json> [n_per_scene]",
              file=sys.stderr)
        sys.exit(1)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sns_labeling.imc_plan_loader import load_campaign_spec
    spec = load_campaign_spec(sys.argv[1])
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    result = select_for_campaign(spec, n_per_scene=n)
    for scene in spec.scenes:
        refs = result.get(scene.slug, [])
        print(f"\n=== {scene.slug} (persona {scene.persona_match}) — {len(refs)} refs ===")
        for r in refs:
            m = r.get("model") or {}
            bg = r.get("background") or {}
            print(f"  rank{r['rank']}: @{r['handle']:20s} score={r['score']:.4f}  "
                  f"age={m.get('age group')} gender={m.get('gender')} "
                  f"pose={m.get('pose')}")
