"""Score each marketing record vs brand-dna's `marketing_dna` distributions
and return top-K image references with explanations.

Usage:
    from sns_labeling.mood_query import query_marketing_pool
    refs = query_marketing_pool(brand_dna, "27SS WJ", k=8)
    # refs = [{"post_id","handle","brand","image","score","matched_axes","record"}]
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_POOL = PROJECT_ROOT / "source" / "sns-influencer-output" / "labels_marketing_index.jsonl"
BRAND_DNA_DIR = PROJECT_ROOT / "st_cut-dev" / "brand-dna"


def _load_alignment(brand_dna: dict) -> Optional[dict]:
    """Load VLM-built brand_dna ↔ pool-taxonomy alignment if present.

    Looked up at brand-dna/_{brand}_alignment.json (built by build_alignment.py).
    Returns None when missing — caller falls back to hand-dict mappings.
    """
    brand = (brand_dna.get("brand") or "").lower().split()[0]
    if not brand:
        return None
    p = BRAND_DNA_DIR / f"_{brand}_alignment.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _apply_alignment(dist: dict[str, float], axis: str,
                      alignment: Optional[dict],
                      hand_map: dict[str, str]) -> dict[str, float]:
    """Distribute brand_dna probability mass into pool-taxonomy values.

    Priority: alignment.json (1:N weighted) > hand_map (1:1) > token as-is.
    """
    out: dict[str, float] = {}
    align_axis = ((alignment or {}).get("alignments") or {}).get(axis) or {}
    for tok, p in dist.items():
        targets = align_axis.get(tok) or align_axis.get(tok.lower())
        if targets:
            for t in targets:
                v = t.get("target")
                w = float(t.get("weight") or 0)
                if v and w > 0:
                    out[v] = out.get(v, 0) + p * w
        else:
            ours = hand_map.get(tok) or hand_map.get(tok.lower()) or tok
            out[ours] = out.get(ours, 0) + p
    return out

# ---- Vocabulary alignment between brand-dna distributions and our taxonomy ----

POSE_DNA_TO_OURS = {
    "stand": "full body shot",   # closest match in our taxonomy
    "sit": "sitting",
    "lean": "sitting",           # closest neighbour
    "walk": "walking",
    "recline": "sitting",
    "squat": "sitting",
}

EXPRESSION_DNA_TO_OURS = {
    "cool": "cool",
    "neutral": "expressionless",
    "serene": "expressionless",
    "confident": "cool",
    "candid": "expressionless",
    "dreamy": "expressionless",
    "playful": "smile",
}

# brand-dna marketing_dna.expression.gaze_distribution → our taxonomy 'gaze direction'
GAZE_DNA_TO_OURS = {
    "camera":     "front",
    "front":      "front",
    "down":       "downward",
    "downward":   "downward",
    "left/right": "side",
    "side":       "side",
    "distant":    "avoiding gaze",
    "away":       "avoiding gaze",
    "up":         "upward",
    "upward":     "upward",
}

# brand_rules.avoid keywords → ban from our taxonomy values (mood/location/style)
AVOID_TOKEN_MAP = {
    "한국 스트릿": {"mood": ["urban", "street"], "location": ["street", "city"]},
    "Y2K 포즈": {"styling.fashion_style": ["y2k"]},
    "거울셀피": {},  # not a label dimension
    "그래피티": {},
    "네온사인": {},
    "인더스트리얼": {"mood": ["hip"]},
    "정적인 올드머니 포즈": {"styling.fashion_style": ["old money look"]},
    "프리미엄 럭셔리 인테리어": {"location": ["café"]},
    "유러피안 건축물": {"location": ["café"]},
    "리조트/풀사이드": {"location": ["pool", "beach"]},
    "파스텔 배경": {"styling.overall_fashion_color_tone": ["pastel tone"]},
    "자연 아웃도어": {"location": ["park/nature/forest", "beach"]},
    "캠핑/트레일": {"location": ["park/nature/forest", "outdoor-exercise"]},
    "일본 감성": {},
    "환한 미소": {"expression": ["smile"]},
    "이를 보이는 미소": {"expression": ["smile"]},
    "밝은 team color": {"styling.overall_fashion_color_tone": ["vivid"]},
    "테니스코트": {},
    "지프/SUV": {"location": ["car"]},
    "athletic 에너지": {"styling.fashion_style": ["sporty"]},
    "두꺼운 기능성 소재": {},
    "환하게 웃기": {"expression": ["smile"]},
    "애교/큐트": {"expression": ["smile"]},
    "과한 액션/러닝": {"pose": ["exercise (running/tennis etc)"]},
    "아웃도어 탐험 포즈": {"pose": ["exercise (running/tennis etc)"]},
    "정적인": {"pose": ["sitting"]},
    "극단적 하이패션 포즈": {},
    "귀여운/아기자기한 포즈": {"styling.fashion_style": ["feminine"]},
    "과한 섹시": {},
    "과한 에너지": {"mood": ["active"]},
    "과한 스포츠 액티비티": {"pose": ["exercise (running/tennis etc)"]},
    "남성 중심 콘텐츠": {"model.gender": ["male"]},
    "아웃도어/자연 배경": {"location": ["park/nature/forest", "beach"]},
}

# Season/category boosts: per token a list of (axis, value, weight)
# Axis is one of: pose, expression, location, mood, fashion_style, color_tone,
#                 coordination, season, gender
SEASON_CATEGORY_BOOSTS = {
    "SS": [("season_weather", "summer", 1.0),
           ("season_weather", "spring", 0.5),
           ("season_weather", "sunny day", 0.5)],
    "FW": [("season_weather", "winter", 1.0),
           ("season_weather", "autumn", 0.7)],
    # category hints (matched on text containing these tokens)
    "WJ": [("location", "park/nature/forest", 0.4),
           ("location", "café", 0.3),
           ("location", "street", 0.3)],
    "DOWN": [("season_weather", "winter", 0.8),
             ("location", "city", 0.4)],
    "PADDING": [("season_weather", "winter", 0.8),
                ("location", "city", 0.4)],
    "PADDED": [("season_weather", "winter", 0.8),
                ("location", "city", 0.4)],
    "PUFFER": [("season_weather", "winter", 0.8),
                ("location", "city", 0.4)],
    "SETUP": [("fashion_style", "casual", 0.3),
              ("fashion_style", "luxury", 0.3),
              ("coordination_method", "set-up", 0.6),
              ("coordination_method", "tone-on-tone", 0.4)],
    "PANTS": [("fashion_style", "casual", 0.3)],
    "TEE": [("fashion_style", "casual", 0.4)],
    "WINDBREAKER": [("location", "park/nature/forest", 0.5)],
    "SHOES": [("pose", "walking", 0.5)],
    "BAG": [("coordination_method", "tone-on-tone", 0.3)],
}


# ---------------------------- Distribution helpers ----------------------------

def _parse_pct(s) -> float:
    if s is None:
        return 0.0
    if isinstance(s, (int, float)):
        return float(s) / (100.0 if abs(s) > 1.5 else 1.0)
    m = re.match(r"\s*([\d.]+)\s*%?", str(s))
    return float(m.group(1)) / 100.0 if m else 0.0


def _normalise_dist(d: dict) -> dict[str, float]:
    """Convert a {token: '74%' or 0.74} mapping into a probability dict."""
    out: dict[str, float] = {}
    if not isinstance(d, dict):
        return out
    total = 0.0
    for k, v in d.items():
        p = _parse_pct(v)
        out[str(k).lower()] = p
        total += p
    if total > 0 and abs(total - 1.0) > 0.01:
        out = {k: v / total for k, v in out.items()}
    return out


MOOD_DNA_TO_OURS = {
    "minimalist premium": "chic",
    "quiet luxury": "luxurious",
    "urban casual": "hip",
    "urban street": "hip",
    "urban cool": "hip",
    "lifestyle": "relaxed",
    "luxury": "luxurious",
    "studio neutral": "chic",
    "outdoor adventure": "active",
    "sporty": "active",
    "adventurous premium": "active",
}

LOC_DNA_TO_OURS = {
    "korean studio": "café",
    "studio": "café",
    "mediterranean/resort": "beach",
    "mediterranean": "beach",
    "outdoor nature": "park/nature/forest",
    "european street": "street",
    "indoor cafe": "café",
    "urban city": "city",
    "outdoor adventure": "park/nature/forest",
    "indoor": "café",
    "beach": "beach",
}


def _extract_targets(brand_dna: dict) -> dict[str, dict[str, float]]:
    """Extract usable target distributions for our axes from brand_dna.

    Uses VLM-built `_{brand}_alignment.json` for 1:N weighted distribution
    when available; falls back to per-axis hand-dicts otherwise.
    """
    alignment = _load_alignment(brand_dna)
    md = brand_dna.get("marketing_dna") or {}
    bg = md.get("background") or {}

    pose_d = _normalise_dist((md.get("pose") or {}).get("stance_distribution") or {})
    expr_d = _normalise_dist((md.get("expression") or {}).get("base_distribution") or {})
    gaze_d = _normalise_dist((md.get("expression") or {}).get("gaze_distribution") or {})
    mood_d = _normalise_dist(bg.get("mood_distribution") or {})
    loc_d = _normalise_dist(bg.get("location_distribution") or {})

    return {
        "pose":       _apply_alignment(pose_d, "pose", alignment, POSE_DNA_TO_OURS),
        "expression": _apply_alignment(expr_d, "expression", alignment, EXPRESSION_DNA_TO_OURS),
        "gaze":       _apply_alignment(gaze_d, "gaze", alignment, GAZE_DNA_TO_OURS),
        "mood":       _apply_alignment(mood_d, "mood", alignment, MOOD_DNA_TO_OURS),
        "location":   _apply_alignment(loc_d, "location", alignment, LOC_DNA_TO_OURS),
    }


def _avoid_tokens(brand_dna: dict) -> list[str]:
    md = brand_dna.get("marketing_dna") or {}
    out: list[str] = []
    for sub in ("pose", "expression", "background"):
        rules = (md.get(sub) or {}).get("brand_rules") or {}
        for tok in rules.get("avoid", []) or rules.get("금지", []) or []:
            out.append(str(tok))
    return out


def _avoid_axes(brand_dna: dict) -> dict[str, set[str]]:
    """{ axis: { taboo values } } drawn from brand_rules.avoid."""
    out: dict[str, set[str]] = {}
    for tok in _avoid_tokens(brand_dna):
        for k, v in tok.items() if isinstance(tok, dict) else []:
            out.setdefault(k, set()).update(v)
        mapped = AVOID_TOKEN_MAP.get(tok) or {}
        for axis, vals in mapped.items():
            out.setdefault(axis, set()).update(vals)
    return out


def _category_boosts(season_category: str) -> list[tuple[str, str, float]]:
    boosts: list[tuple[str, str, float]] = []
    sc_upper = (season_category or "").upper()
    for token, lst in SEASON_CATEGORY_BOOSTS.items():
        if token in sc_upper:
            boosts.extend(lst)
    return boosts


# ----------------------------- Record scoring -----------------------------

def _score_record(
    rec: dict,
    targets: dict[str, dict[str, float]],
    boosts: list[tuple[str, str, float]],
    avoid: dict[str, set[str]],
    brand_filter: Optional[set[str]],
    confidence_floor: float,
) -> tuple[float, list[str]]:
    """Return (score, reasons[])."""
    a = rec.get("account") or {}
    if brand_filter and (a.get("brand") not in brand_filter):
        return -1.0, ["brand-mismatch"]
    ft = rec.get("free_text") or {}
    conf = ft.get("_confidence")
    if conf is not None and conf < confidence_floor:
        return -1.0, [f"low-confidence({conf})"]

    m = rec.get("model") or {}
    bg = rec.get("background") or {}
    st = rec.get("styling") or {}

    pose_v = m.get("pose")
    expr_v = m.get("expression")
    gaze_v = m.get("gaze direction")
    mood_v = bg.get("mood")
    loc_v = bg.get("location")
    season_v = bg.get("season/weather")
    style_v = st.get("fashion style")
    coord_v = st.get("coordination method")
    tone_v = st.get("overall fashion color tone")

    score = 0.0
    reasons: list[str] = []

    # axis weights (sum 1.0; gaze added after re-labeling)
    AXIS_WEIGHT = {"pose": 0.25, "expression": 0.15, "gaze": 0.15,
                    "mood": 0.25, "location": 0.20}

    def _hit(axis: str, value):
        if not value:
            return
        target = targets.get(axis) or {}
        p = target.get(str(value).lower(), 0.0) if value else 0.0
        if p > 0:
            sc = p * AXIS_WEIGHT[axis]
            nonlocal score
            score += sc
            reasons.append(f"{axis}={value}({int(p*100)}%)")

    _hit("pose", pose_v)
    _hit("expression", expr_v)
    _hit("gaze", gaze_v)
    _hit("mood", mood_v)
    _hit("location", loc_v)

    # season/category boosts
    for axis, val, w in boosts:
        cur = {
            "pose": pose_v, "expression": expr_v, "mood": mood_v,
            "location": loc_v, "season_weather": season_v,
            "fashion_style": style_v, "coordination_method": coord_v,
            "overall_fashion_color_tone": tone_v,
        }.get(axis)
        if cur and str(cur).lower() == str(val).lower():
            score += 0.10 * w
            reasons.append(f"+{axis}={val}({w:+.1f})")

    # avoid penalties
    for axis, taboos in avoid.items():
        cur = {
            "pose": pose_v, "expression": expr_v, "mood": mood_v,
            "location": loc_v, "fashion_style": style_v,
        }.get(axis)
        if cur and str(cur).lower() in {t.lower() for t in taboos}:
            score -= 0.20
            reasons.append(f"-{axis}={cur} avoid")

    # confidence as small multiplier (0.7 → 0.7×, 1.0 → 1.0×)
    if conf is not None:
        score *= max(0.5, float(conf))
        reasons.append(f"conf×{conf}")
    return score, reasons


# ----------------------------------- API -----------------------------------

def query_marketing_pool(
    brand_dna: dict,
    season_category: str,
    *,
    k: int = 10,
    pool_path: Path | str = DEFAULT_POOL,
    brand_filter: Optional[list[str]] = None,
    confidence_floor: float = 0.7,
) -> list[dict]:
    """Score every record and return the top-K reference selections."""
    targets = _extract_targets(brand_dna)
    boosts = _category_boosts(season_category)
    avoid = _avoid_axes(brand_dna)
    bf = set(brand_filter) if brand_filter else None

    pool_path = Path(pool_path)
    if not pool_path.exists():
        raise FileNotFoundError(pool_path)

    scored: list[tuple[float, list[str], dict]] = []
    with pool_path.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            s, reasons = _score_record(rec, targets, boosts, avoid, bf, confidence_floor)
            if s > 0:
                scored.append((s, reasons, rec))
    scored.sort(key=lambda x: -x[0])
    selected = scored[:k]
    return [
        {
            "rank": i + 1,
            "score": round(s, 4),
            "matched_axes": rs,
            "post_id": (rec.get("account") or {}).get("post_id"),
            "handle": (rec.get("account") or {}).get("handle"),
            "brand": (rec.get("account") or {}).get("brand"),
            "post_url": (rec.get("account") or {}).get("post_url"),
            "image": (rec.get("image") or {}).get("path"),
            "model": rec.get("model"),
            "background": rec.get("background"),
            "styling": rec.get("styling"),
            "confidence": (rec.get("free_text") or {}).get("_confidence"),
            "notes": (rec.get("free_text") or {}).get("_notes"),
        }
        for i, (s, rs, rec) in enumerate(selected)
    ]


def explain_targets(brand_dna: dict, season_category: str) -> dict:
    """Return what targets the matcher will use (for transparency / proposal)."""
    return {
        "targets": _extract_targets(brand_dna),
        "season_category_boosts": _category_boosts(season_category),
        "avoid_axes": {k: sorted(v) for k, v in _avoid_axes(brand_dna).items()},
    }


__all__ = [
    "query_marketing_pool",
    "query_marketing_pool_v2",
    "explain_targets",
    "DEFAULT_POOL",
]


# ----------------------------- v2 selector -----------------------------

# Score channel weights (sum 1.0 for the marketing channel).
V2_DISCRETE_WEIGHT = 0.55
V2_EMBED_WEIGHT = 0.35
V2_HANDLE_WEIGHT = 0.10


def _brand_text(brand_dna: dict, season_category: str) -> str:
    """Build a single-paragraph text describing the brand for embedding."""
    md = brand_dna.get("marketing_dna") or {}
    bg = md.get("background") or {}
    bits = []
    pos = brand_dna.get("positioning") or brand_dna.get("design_coordinate")
    if pos:
        bits.append(f"positioning: {pos}")
    moods = brand_dna.get("mood")
    if isinstance(moods, list) and moods:
        bits.append("brand mood: " + ", ".join(moods[:5]))

    def _top(d, n=3):
        if not isinstance(d, dict):
            return []
        items = sorted(d.items(),
                        key=lambda kv: -_parse_pct(kv[1]))
        return [k for k, _ in items[:n]]

    pose_top = _top((md.get("pose") or {}).get("stance_distribution"))
    expr_top = _top((md.get("expression") or {}).get("base_distribution"))
    gaze_top = _top((md.get("expression") or {}).get("gaze_distribution"))
    mood_top = _top(bg.get("mood_distribution"))
    loc_top = _top(bg.get("location_distribution"))
    if pose_top:
        bits.append("preferred pose: " + ", ".join(pose_top))
    if expr_top:
        bits.append("expression: " + ", ".join(expr_top))
    if gaze_top:
        bits.append("gaze: " + ", ".join(gaze_top))
    if mood_top:
        bits.append("background mood: " + ", ".join(mood_top))
    if loc_top:
        bits.append("location: " + ", ".join(loc_top))
    bits.append(f"season/category: {season_category}")
    return ". ".join(bits)


def _embedding_scores(records: list[dict],
                      brand_text: str) -> dict[str, float]:
    """post_id → cosine sim (in [-1,1]). Returns {} if cache or API fails."""
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
        q = embed_text(brand_text)
    except Exception as e:
        print(f"[warn] embed_text failed: {type(e).__name__}: {e}")
        return {}
    sims = cosine_similarity(q, matrix)
    out: dict[str, float] = {}
    for rec in records:
        pid = (rec.get("account") or {}).get("post_id")
        if pid and pid in id_to_row:
            out[pid] = float(sims[id_to_row[pid]])
    return out


def _handle_diversity_factor(records: list[dict]) -> dict[int, float]:
    """For each record id, return 1/n where n = #posts by same handle in pool.

    Scaled to (0, 1]; lone handles get 1.0, prolific handles fractional.
    """
    handle_counts: dict[str, int] = {}
    for rec in records:
        h = (rec.get("account") or {}).get("handle") or "_no_handle"
        handle_counts[h] = handle_counts.get(h, 0) + 1
    out: dict[int, float] = {}
    for rec in records:
        h = (rec.get("account") or {}).get("handle") or "_no_handle"
        n = handle_counts[h]
        out[id(rec)] = 1.0 / n if n > 0 else 1.0
    return out


def query_marketing_pool_v2(
    brand_dna: dict,
    season_category: str,
    *,
    k: int = 6,
    pool_path: Path | str = DEFAULT_POOL,
    brand_filter: Optional[list[str]] = None,
    confidence_floor: float = 0.7,
    use_embedding: bool = True,
    clash_threshold: int = 4,
) -> list[dict]:
    """v2 reference selector: discrete + embedding + 3-stage diversity filter.

    1. Score = 0.55*discrete + 0.35*embed_cosine + 0.10*handle_diversity_factor
    2. Handle dedup → highest-score row per handle.
    3. Stratified slot allocation by target mood × location.
    4. Axis-clash filter: drop near-duplicates that share ≥4/5 axes; refill.
    """
    from sns_labeling.selector_v2 import select_v2

    targets = _extract_targets(brand_dna)
    boosts = _category_boosts(season_category)
    avoid = _avoid_axes(brand_dna)
    bf = set(brand_filter) if brand_filter else None

    pool_path = Path(pool_path)
    if not pool_path.exists():
        raise FileNotFoundError(pool_path)

    # Pass 1: discrete score per record (re-uses _score_record).
    raw: list[tuple[float, list[str], dict]] = []
    with pool_path.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            s, reasons = _score_record(rec, targets, boosts, avoid, bf, confidence_floor)
            if s > 0:
                raw.append((s, reasons, rec))

    if not raw:
        return []

    # Pass 2: embedding sim and handle diversity multipliers.
    pool_records = [t[2] for t in raw]
    embed_map = (_embedding_scores(pool_records, _brand_text(brand_dna, season_category))
                 if use_embedding else {})
    handle_factor = _handle_diversity_factor(pool_records)

    # Pass 3: combine into v2 score.
    combined: list[tuple[float, list[str], dict]] = []
    for s_disc, reasons, rec in raw:
        pid = (rec.get("account") or {}).get("post_id")
        emb = embed_map.get(pid, 0.0) if pid else 0.0
        # cosine [-1,1] → clip to [0,1] for additive blend
        emb_pos = max(0.0, emb)
        hf = handle_factor.get(id(rec), 1.0)
        s_v2 = (V2_DISCRETE_WEIGHT * s_disc
                + V2_EMBED_WEIGHT * emb_pos
                + V2_HANDLE_WEIGHT * hf)
        new_reasons = list(reasons)
        if embed_map:
            new_reasons.append(f"embed={emb:+.3f}")
        new_reasons.append(f"hf×{hf:.2f}")
        combined.append((s_v2, new_reasons, rec))

    combined.sort(key=lambda t: -t[0])

    # Stratified + axis-clash via selector_v2.
    final = select_v2(combined,
                       target_mood=targets.get("mood") or {},
                       target_loc=targets.get("location") or {},
                       k=k, clash_threshold=clash_threshold)

    return [
        {
            "rank": i + 1,
            "score": round(s, 4),
            "matched_axes": rs,
            "post_id": (rec.get("account") or {}).get("post_id"),
            "handle": (rec.get("account") or {}).get("handle"),
            "brand": (rec.get("account") or {}).get("brand"),
            "post_url": (rec.get("account") or {}).get("post_url"),
            "image": (rec.get("image") or {}).get("path"),
            "model": rec.get("model"),
            "background": rec.get("background"),
            "styling": rec.get("styling"),
            "confidence": (rec.get("free_text") or {}).get("_confidence"),
            "notes": (rec.get("free_text") or {}).get("_notes"),
        }
        for i, (s, rs, rec) in enumerate(final)
    ]
