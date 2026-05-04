"""Product-aware variant of mood_query.

Pool source: `labels_adapted_index.jsonl` (has items[] + common — product info kept)
Scoring extends marketing axes with product signals:
    - common.color matches DNA color (base/key/accent) tiers
    - common.fabrication / material align with DNA fabric guidance
    - items[].cat overlaps category implied by season_category
    - items[].sub_cat closeness to brand garment_types

Marketing axis weights are dialed down (0.7) and product axes get the
remaining ~0.3 budget so the two channels combine without one drowning
the other. Same return shape as `mood_query.query_marketing_pool`.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from sns_labeling.mood_query import (
    _avoid_axes,
    _category_boosts,
    _extract_targets,
    _record_image_path,
    _parse_pct,  # type: ignore  # may not exist; will fall back if not exported
    _normalise_dist,  # type: ignore
)
from project_paths import SOURCE_DIR

# Import-friendly fallbacks
try:
    from sns_labeling.mood_query import _parse_pct as _pp  # noqa
except Exception:
    _pp = None

DEFAULT_POOL_PRODUCT = SOURCE_DIR / "labels_adapted_index.jsonl"

# Marketing axis weights (5-axis: pose/expr/gaze/mood/loc, total 0.70)
AXIS_WEIGHT = {"pose": 0.18, "expression": 0.10, "gaze": 0.10,
                "mood": 0.18, "location": 0.14}
# Product axis weights (the new 0.3 budget)
PRODUCT_WEIGHT = {
    "color": 0.10,         # tier-aware bonus
    "fabrication": 0.05,
    "material": 0.05,
    "cat_match": 0.07,     # season_category category vs items[].cat
    "sub_cat_keyword": 0.03,
}

# Map "WJ"/"SETUP"/etc. → which top-level cat must be visible in items[]
CATEGORY_TO_CAT = {
    "WJ": "Outer", "DOWN": "Outer", "JACKET": "Outer", "WINDBREAKER": "Outer",
    "SETUP": "Outer",   # setup usually has outer + bottom; we boost Outer
    "PANTS": "Bottom", "WP": "Bottom",
    "TEE": "Inner", "TS": "Inner",
    "SH": "Shoes", "SHOES": "Shoes",
    "BAG": "Bag",
    "DJ": "Outer",
    "WB": "Outer",   # Discovery 'windbreaker'
}


def _resolve_target_cat(season_category: str) -> Optional[str]:
    sc = (season_category or "").upper().split()
    for tok in sc:
        if tok in CATEGORY_TO_CAT:
            return CATEGORY_TO_CAT[tok]
    return None


def _resolve_target_subcat_keywords(brand_dna: dict, season_category: str) -> list[str]:
    """Pull garment_types tokens from brand_dna for the target category."""
    cats = brand_dna.get("categories") or {}
    sc_upper = (season_category or "").upper()
    # try alias resolution similar to campaign_proposal._scene_garment_brief
    for ckey in cats.keys():
        token = ckey.upper().replace("_", "")
        if any(t in sc_upper.replace(" ", "") for t in (token, ckey.upper())):
            cat = cats[ckey] or {}
            tokens = []
            for src in (cat.get("items"), cat.get("garment_types"), cat.get("key_items")):
                if isinstance(src, list):
                    tokens.extend(src)
            return [t.lower() for t in tokens if isinstance(t, str)]
    # data_driven_guardrails fallback
    ddg = brand_dna.get("data_driven_guardrails") or {}
    for ckey, info in ddg.items():
        if not isinstance(info, dict):
            continue
        token = ckey.upper().replace("_", "")
        if any(t in sc_upper.replace(" ", "") for t in (token, ckey.upper())):
            return [t.lower() for t in (info.get("garment_types") or []) if isinstance(t, str)]
    return []


def _flat_color_palette(brand_dna: dict) -> dict[str, float]:
    """Return {color_name_lower: weight} merged from base/key/accent tiers."""
    out: dict[str, float] = {}
    color = brand_dna.get("color") or {}
    tier_weights = {"base": 1.0, "key": 0.7, "accent": 0.4}
    for tier, w in tier_weights.items():
        block = color.get(tier) or {}
        for c in (block.get("colors") or []):
            if isinstance(c, dict) and c.get("name"):
                out[c["name"].lower().strip()] = max(out.get(c["name"].lower().strip(), 0), w)
    return out


def _allowed_fabrications(brand_dna: dict, season_category: str) -> set[str]:
    sc_upper = (season_category or "").upper()
    out: set[str] = set()
    fabric = brand_dna.get("fabric") or {}
    for k in ("material_actual", "material_original", "material"):
        v = fabric.get(k)
        if isinstance(v, list):
            out.update(s.lower() for s in v if isinstance(s, str))
    # category-specific tokens
    cats = brand_dna.get("categories") or {}
    for ckey, info in cats.items():
        if not isinstance(info, dict):
            continue
        token = ckey.upper().replace("_", "")
        if any(t in sc_upper.replace(" ", "") for t in (token, ckey.upper())):
            for kp in (info.get("key_points") or "").split(","):
                out.add(kp.strip().lower())
    return out


def _allowed_materials(brand_dna: dict) -> set[str]:
    fabric = brand_dna.get("fabric") or {}
    out: set[str] = set()
    for k in ("material", "material_actual", "material_original"):
        v = fabric.get(k)
        if isinstance(v, list):
            out.update(s.lower() for s in v if isinstance(s, str))
    return out


def _color_overlap_score(rec_colors: list[str], palette: dict[str, float]) -> tuple[float, list[str]]:
    if not rec_colors:
        return 0.0, []
    score = 0.0
    matches: list[str] = []
    for col in rec_colors:
        c = (col or "").lower().strip()
        # exact or tier-substring (e.g., "ivory" in palette under "ivory and beige")
        for pal_name, w in palette.items():
            if c == pal_name or c in pal_name or pal_name in c:
                score += w
                matches.append(f"{c}=~{pal_name}({w:.1f})")
                break
    # cap score so no record gets runaway from 5+ colors
    return min(score, 2.0), matches


def _score_record_product(
    rec: dict,
    targets: dict[str, dict[str, float]],
    boosts: list[tuple[str, str, float]],
    avoid: dict[str, set[str]],
    brand_filter: Optional[set[str]],
    confidence_floor: float,
    *,
    target_cat: Optional[str],
    target_subcat_kws: list[str],
    color_palette: dict[str, float],
    allowed_fabrications: set[str],
    allowed_materials: set[str],
) -> tuple[float, list[str]]:
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
    common = rec.get("common") or {}
    items = rec.get("items") or []

    pose_v = m.get("pose")
    expr_v = m.get("expression")
    gaze_v = m.get("gaze direction")
    mood_v = bg.get("mood")
    loc_v = bg.get("location")
    season_v = bg.get("season/weather")
    style_v = st.get("fashion style")

    score = 0.0
    reasons: list[str] = []

    # ---- marketing axes (downscaled) ----
    def _hit(axis: str, value):
        nonlocal score
        if not value:
            return
        target = targets.get(axis) or {}
        p = target.get(str(value).lower(), 0.0)
        if p > 0:
            sc = p * AXIS_WEIGHT[axis]
            score += sc
            reasons.append(f"{axis}={value}({int(p*100)}%×{AXIS_WEIGHT[axis]:.2f})")

    _hit("pose", pose_v)
    _hit("expression", expr_v)
    _hit("gaze", gaze_v)
    _hit("mood", mood_v)
    _hit("location", loc_v)

    # ---- season/category boosts (kept) ----
    for axis, val, w in boosts:
        cur = {
            "pose": pose_v, "expression": expr_v, "mood": mood_v,
            "location": loc_v, "season_weather": season_v,
            "fashion_style": style_v,
        }.get(axis)
        if cur and str(cur).lower() == str(val).lower():
            score += 0.07 * w
            reasons.append(f"+{axis}={val}({w:+.1f})")

    # ---- avoid penalties (kept) ----
    for axis, taboos in avoid.items():
        cur = {
            "pose": pose_v, "expression": expr_v, "mood": mood_v,
            "location": loc_v, "fashion_style": style_v,
        }.get(axis)
        if cur and str(cur).lower() in {t.lower() for t in taboos}:
            score -= 0.15
            reasons.append(f"-{axis}={cur} avoid")

    # ---- product signals (NEW) ----
    # color tier overlap
    rec_colors = common.get("color") or []
    col_score, col_matches = _color_overlap_score(rec_colors, color_palette)
    if col_score > 0:
        weighted = min(col_score, 1.5) * (PRODUCT_WEIGHT["color"] / 1.5)
        score += weighted
        reasons.append(f"+color[{','.join(col_matches[:3])}](+{weighted:.3f})")

    # fabrication/material name presence
    fab = (common.get("fabrication") or "").lower().strip()
    if fab and any(fab in tok or tok in fab for tok in allowed_fabrications):
        score += PRODUCT_WEIGHT["fabrication"]
        reasons.append(f"+fab={fab}(+{PRODUCT_WEIGHT['fabrication']})")

    mat = (common.get("material") or "").lower().strip()
    if mat and mat in allowed_materials:
        score += PRODUCT_WEIGHT["material"]
        reasons.append(f"+mat={mat}(+{PRODUCT_WEIGHT['material']})")

    # category coverage: does items[] include the target cat?
    item_cats = {(it.get("cat") or "") for it in items}
    if target_cat and target_cat in item_cats:
        score += PRODUCT_WEIGHT["cat_match"]
        reasons.append(f"+cat={target_cat}(+{PRODUCT_WEIGHT['cat_match']})")

    # sub_cat keyword overlap
    if target_subcat_kws:
        sub_text = " ".join(((it.get("sub_cat") or "").lower()) for it in items)
        if any(kw in sub_text for kw in target_subcat_kws if kw):
            score += PRODUCT_WEIGHT["sub_cat_keyword"]
            reasons.append(f"+sub_cat~kws(+{PRODUCT_WEIGHT['sub_cat_keyword']})")

    # ---- confidence multiplier (kept) ----
    if conf is not None:
        score *= max(0.5, float(conf))
        reasons.append(f"conf×{conf}")
    return score, reasons


def query_marketing_pool_product(
    brand_dna: dict,
    season_category: str,
    *,
    k: int = 10,
    pool_path: Path | str = DEFAULT_POOL_PRODUCT,
    brand_filter: Optional[list[str]] = None,
    confidence_floor: float = 0.7,
) -> list[dict]:
    """Product-aware Top-K selection. Same return shape as marketing variant."""
    targets = _extract_targets(brand_dna)
    boosts = _category_boosts(season_category)
    avoid = _avoid_axes(brand_dna)
    bf = set(brand_filter) if brand_filter else None
    target_cat = _resolve_target_cat(season_category)
    target_subcat_kws = _resolve_target_subcat_keywords(brand_dna, season_category)
    color_palette = _flat_color_palette(brand_dna)
    allowed_fab = _allowed_fabrications(brand_dna, season_category)
    allowed_mat = _allowed_materials(brand_dna)

    pool_path = Path(pool_path)
    if not pool_path.exists():
        raise FileNotFoundError(pool_path)

    scored: list[tuple[float, list[str], dict]] = []
    with pool_path.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            s, reasons = _score_record_product(
                rec, targets, boosts, avoid, bf, confidence_floor,
                target_cat=target_cat, target_subcat_kws=target_subcat_kws,
                color_palette=color_palette,
                allowed_fabrications=allowed_fab,
                allowed_materials=allowed_mat,
            )
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
            "image": _record_image_path(rec),
            "model": rec.get("model"),
            "background": rec.get("background"),
            "styling": rec.get("styling"),
            "common": rec.get("common"),                # ★ NEW: product info preserved
            "items": rec.get("items"),                  # ★ NEW: product info preserved
            "confidence": (rec.get("free_text") or {}).get("_confidence"),
            "notes": (rec.get("free_text") or {}).get("_notes"),
        }
        for i, (s, rs, rec) in enumerate(selected)
    ]


def query_marketing_pool_product_v2(
    brand_dna: dict,
    season_category: str,
    *,
    k: int = 6,
    pool_path: Path | str = DEFAULT_POOL_PRODUCT,
    brand_filter: Optional[list[str]] = None,
    confidence_floor: float = 0.7,
    use_embedding: bool = True,
    clash_threshold: int = 4,
) -> list[dict]:
    """Product-aware v2 selector. Same diversity stages as mood_query v2."""
    from sns_labeling.selector_v2 import select_v2
    from sns_labeling.mood_query import (
        V2_DISCRETE_WEIGHT, V2_EMBED_WEIGHT, V2_HANDLE_WEIGHT,
        _brand_text, _embedding_scores, _handle_diversity_factor,
    )

    targets = _extract_targets(brand_dna)
    boosts = _category_boosts(season_category)
    avoid = _avoid_axes(brand_dna)
    bf = set(brand_filter) if brand_filter else None
    target_cat = _resolve_target_cat(season_category)
    target_subcat_kws = _resolve_target_subcat_keywords(brand_dna, season_category)
    color_palette = _flat_color_palette(brand_dna)
    allowed_fab = _allowed_fabrications(brand_dna, season_category)
    allowed_mat = _allowed_materials(brand_dna)

    pool_path = Path(pool_path)
    if not pool_path.exists():
        raise FileNotFoundError(pool_path)

    raw: list[tuple[float, list[str], dict]] = []
    with pool_path.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            s, reasons = _score_record_product(
                rec, targets, boosts, avoid, bf, confidence_floor,
                target_cat=target_cat, target_subcat_kws=target_subcat_kws,
                color_palette=color_palette,
                allowed_fabrications=allowed_fab,
                allowed_materials=allowed_mat,
            )
            if s > 0:
                raw.append((s, reasons, rec))

    if not raw:
        return []

    pool_records = [t[2] for t in raw]
    embed_map = (_embedding_scores(pool_records,
                                    _brand_text(brand_dna, season_category))
                 if use_embedding else {})
    handle_factor = _handle_diversity_factor(pool_records)

    combined: list[tuple[float, list[str], dict]] = []
    for s_disc, reasons, rec in raw:
        pid = (rec.get("account") or {}).get("post_id")
        emb = embed_map.get(pid, 0.0) if pid else 0.0
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
            "image": _record_image_path(rec),
            "model": rec.get("model"),
            "background": rec.get("background"),
            "styling": rec.get("styling"),
            "common": rec.get("common"),
            "items": rec.get("items"),
            "confidence": (rec.get("free_text") or {}).get("_confidence"),
            "notes": (rec.get("free_text") or {}).get("_notes"),
        }
        for i, (s, rs, rec) in enumerate(final)
    ]


__all__ = [
    "query_marketing_pool_product",
    "query_marketing_pool_product_v2",
    "DEFAULT_POOL_PRODUCT",
    "AXIS_WEIGHT",
    "PRODUCT_WEIGHT",
]
