"""Adapter: external `labels_raw/*.json` → our schema (`schemas.empty_label_record`).

Approach:
- Static vocab maps for fields with known synonym/case mismatches.
- A taxonomy inverse-index for free-text fields (silhouette_or_length, additional_details)
  that automatically routes a string to the right (cat, attribute_key) bucket.
- Out-of-vocabulary values are stored in `_extra` so nothing is silently lost.

Public API:
    build_inverse_index(taxonomy) -> dict
    adapt_record(their_record, taxonomy, inv_index, image_path=None,
                 brand_full=None) -> our_record
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from sns_labeling.schemas import empty_label_record

# ---- Brand codes used in the external dataset ------------------------------

BRAND_CODE_TO_FULL = {
    "DV": "duvetica",
    "DX": "discovery",
    "MLB": "mlb",
}

# ---- Vocab maps (theirs -> ours; None means OOV → null) --------------------

CAT_NORM: dict[str, Optional[str]] = {
    # case-fix only
    "outer": "Outer", "Outer": "Outer",
    "bottom": "Bottom", "Bottom": "Bottom",
    "inner": "Inner", "Inner": "Inner",
    "bag": "Bag", "Bag": "Bag",
    "shoes": "Shoes", "Shoes": "Shoes",
    "headwear": "Headwear", "Headwear": "Headwear",
    "onepiece": "Onepiece", "Onepiece": "Onepiece",
    "eyewear": "Eyewear", "Eyewear": "Eyewear",
    "neckwear": "Neckwear", "Neckwear": "Neckwear",
    "hosiery": "Hosiery", "Hosiery": "Hosiery",
    # swimwear variants merged
    "swimwear": "Swimwear",
    "swimwear inner": "Swimwear", "Swimwear inner": "Swimwear",
    "swimwear bottoms": "Swimwear", "Swimwear bottoms": "Swimwear",
    "swimwear onepiece": "Swimwear", "Swimwear onepiece": "Swimwear",
    # truly OOV
    "accessory": None, "Accessory": None, "accessories": None,
    "wristwear": None, "Wristwear": None,
    "underwear": None, "Underwear": None,
}

GENDER_MAP = {
    "male": "male", "female": "female",
    "Male": "male", "Female": "female",
    "unknown": None, "not applicable": None, "Not Applicable": None,
}

AGE_MAP = {
    "child": "child", "teenager": "teenager",
    "young adult": "youth", "Young Adult": "youth",
    "youth": "youth", "Youth": "youth",
    "adult": "adult", "Adult": "adult",
    "middle-aged": "middle-aged", "Middle-aged": "middle-aged",
    "elderly": "elderly", "Elderly": "elderly",
    "unknown": None, "not applicable": None, "Not Applicable": None,
}

POSE_MAP = {
    "sitting": "sitting", "walking": "walking",
    "looking back": "looking back",
    "aerial shot": "aerial shot",
    "low angle shot": "low angle shot",
    "full body shot": "full body shot",
    "exercise (running/tennis etc)": "exercise (running/tennis etc)",
    # OOV (their common values)
    "posing": None, "standing": None, "mid shot": None,
    "lying down": None, "sleeping": None, "close-up": None,
}

EXPRESSION_MAP = {
    "smile": "smile", "smiling": "smile",
    "expressionless": "expressionless", "neutral": "expressionless",
    "surprised": "surprised", "surprise": "surprised",
    "cool": "cool", "wink": "wink",
    "yawning": None, "relaxed": None, "no person": None,
}

LOCATION_MAP = {
    # direct (our values)
    "street": "street",
    "café": "café", "cafe": "café",
    "park/nature/forest": "park/nature/forest",
    "park": "park/nature/forest", "nature": "park/nature/forest",
    "forest": "park/nature/forest",
    "beach": "beach", "gym": "gym",
    "festival": "festival", "festival-like": "festival-like",
    "party": "party",
    "city": "city", "campus": "campus",
    "car": "car", "stadium": "stadium",
    "flight": "flight",
    "outdoor-exercise": "outdoor-exercise",
    "travel": "travel", "pool": "pool",
    "shopping/store": "shopping/store",
    "shopping": "shopping/store", "store": "shopping/store",
    "shop": "shopping/store",
    # OOV
    "indoor": None, "studio": None, "home": None,
    "bedroom": None, "bathroom": None, "kitchen": None,
    "bar": None, "restaurant": None, "office": None, "null": None,
}

OVERALL_COLOR_TONE_MAP = {
    "neutral tone": "neutral tone", "neutral": "neutral tone",
    "pastel tone": "pastel tone", "pastel": "pastel tone",
    "vivid": "vivid",
    "tone-on-tone": "tone-on-tone", "tone on tone": "tone-on-tone",
    "monotone": "monotone", "monochrome": "monotone", "mono": "monotone",
    "warm": None, "cool": None, "contrast": None, "hero color": None,
}

FASHION_STYLE_MAP = {
    "casual": "casual", "street": "street", "business": "business",
    "formal": "formal", "sporty": "sporty", "luxury": "luxury",
    "feminine": "feminine", "gorpcore": "gorpcore", "workwear": "workwear",
    "y2k": "y2k", "old money look": "old money look", "preppy": "preppy",
    "bodycon": "bodycon",
    # close synonyms
    "luxurious": "luxury",
    # ambiguous → null (preserved in _extra)
    "chic": None, "minimal": None,
    "not applicable": None, "Not Applicable": None,
    "unknown": None, "none": None,
}

COORDINATION_MAP = {
    # our: layered, tone-on-tone, set-up, mix & match, low-rise, oversized
    "layered": "layered",
    "tone-on-tone": "tone-on-tone", "tone on tone": "tone-on-tone",
    "set-up": "set-up", "set up": "set-up", "setup": "set-up",
    "mix & match": "mix & match", "mix and match": "mix & match",
    "low-rise": "low-rise", "low rise": "low-rise",
    "oversized": "oversized",
    # OOV
    "layering": "layered",
    "tonal": "tone-on-tone",
}

SEASON_WEATHER_MAP = {
    "sunny day": "sunny day", "sunny": "sunny day",
    "rainy day": "rainy day", "rainy": "rainy day",
    "spring": "spring", "summer": "summer",
    "autumn": "autumn", "fall": "autumn",
    "winter": "winter",
    "unknown": None,
}

# Pattern in their data sometimes contains graphic_print values.
GRAPHIC_PRINT_TOKENS = {"lettering", "monogram", "iconographic",
                        "typography", "character", "photoreal", "abstract",
                        "graphic print"}

# Pattern direct synonyms
PATTERN_MAP = {
    "solid": "solid", "stripe": "stripe", "stripes": "stripe",
    "dots": "dots", "polka dots": "dots",
    "floral": "floral",
    "gingham-check": "gingham-check", "gingham": "gingham-check",
    "tartan-check": "tartan-check", "tartan": "tartan-check",
    "plaid": "tartan-check",
    "chevron": "chevron",
    "houndstooth": "houndstooth",
    "paisley": "paisley",
    "argyle": "argyle",
    "camouflage": "camouflage", "camo": "camouflage",
    "zebra pattern": "zebra pattern", "zebra": "zebra pattern",
    "leopard pattern": "leopard pattern", "leopard": "leopard pattern",
    "crocodile pattern": "crocodile pattern", "crocodile": "crocodile pattern",
    "tie dye": "tie dye", "tie-dye": "tie dye",
    "marbling": "marbling",
}


# ---- Inverse index over the whole taxonomy --------------------------------

def build_inverse_index(tax: dict) -> dict[str, list[tuple[str, str]]]:
    """Build {value_lower: [(scope, attr_key), ...]}.

    scope = "shared:<bin>"  (e.g., "shared:common")
          | "cat:<Cat>"     (e.g., "cat:Outer")
    """
    inv: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for bin_name, bin_keys in tax["shared"].items():
        for k, vals in bin_keys.items():
            for v in vals:
                inv[v.lower().strip()].append((f"shared:{bin_name}", k))
    for cat, info in tax["categories"].items():
        for k, vals in info["attribute_keys"].items():
            for v in vals:
                inv[v.lower().strip()].append((f"cat:{cat}", k))
    return inv


def _route_free_value(
    value: str, current_cat: Optional[str], inv: dict
) -> Optional[tuple[str, str, str]]:
    """Try to route a free-text value to (scope, attr_key, canonical_value).

    Preference order:
      1. exact match within current_cat
      2. exact match in any cat (deterministic: first by alphabetical scope)
      3. exact match in shared bin
      4. None (caller stores in leftover)
    """
    if not value:
        return None
    key = value.lower().strip()
    matches = inv.get(key)
    if not matches:
        return None
    if current_cat:
        cat_target = f"cat:{current_cat}"
        for scope, attr in matches:
            if scope == cat_target:
                return (scope, attr, value)
    cat_matches = sorted([m for m in matches if m[0].startswith("cat:")])
    if cat_matches:
        scope, attr = cat_matches[0]
        return (scope, attr, value)
    sh_matches = sorted([m for m in matches if m[0].startswith("shared:")])
    if sh_matches:
        scope, attr = sh_matches[0]
        return (scope, attr, value)
    return None


# ---- Field-level transforms ----------------------------------------------

def _norm_cat(cat) -> Optional[str]:
    if not cat:
        return None
    return CAT_NORM.get(str(cat).strip(), None)


def _norm_subcat(cat: Optional[str], sub_cat, tax: dict) -> Optional[str]:
    if not sub_cat or not cat:
        return None
    sc = str(sub_cat).strip()
    allowed = tax["categories"].get(cat, {}).get("subcategories", [])
    if sc in allowed:
        return sc
    sc_l = sc.lower()
    for a in allowed:
        if a.lower() == sc_l:
            return a
    return None


def _norm_number_of_people(v) -> Optional[str]:
    if v in (None, "", "unknown"):
        return None
    s = str(v).strip().lower()
    if s == "0":
        return None
    if s == "1":
        return "single"
    if s == "2":
        return "couple"
    if s.isdigit() and int(s) >= 3:
        return "group"
    if s in ("group", "single", "couple", "family"):
        return s
    return None


def _norm_pattern(v: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Return (pattern_value, graphic_print_value).

    Their `pattern` field sometimes carries graphic_print tokens.
    """
    if not v:
        return None, None
    s = str(v).strip().lower()
    if s in PATTERN_MAP:
        return PATTERN_MAP[s], None
    if s in GRAPHIC_PRINT_TOKENS:
        return None, s if s != "graphic print" else None
    return None, None


# ---- Item-level adaptation ------------------------------------------------

def _adapt_item(it: dict, tax: dict, inv: dict) -> tuple[Optional[dict], dict]:
    """Adapt one of their items[] to ours. Returns (item_or_None, extras_for_this_item)."""
    cat = _norm_cat(it.get("cat"))
    extras = {
        "_orig_cat": it.get("cat"),
        "_orig_sub_cat": it.get("sub_cat"),
        "leftover_details": [],
        "ambiguous_details": [],
    }
    if cat is None:
        # Drop item from items[] but keep originals in extras
        extras["_dropped_reason"] = "cat OOV"
        return None, extras

    sub_cat = _norm_subcat(cat, it.get("sub_cat"), tax)
    cat_info = tax["categories"][cat]
    attr_keys = list(cat_info["attribute_keys"].keys())
    attributes = {k: None for k in attr_keys}

    def _try_assign(value: Optional[str]) -> Optional[str]:
        """Route a value into attributes; return 'assigned'|'leftover'|None."""
        if not value:
            return None
        routed = _route_free_value(str(value), cat, inv)
        if routed is None:
            return "leftover"
        scope, attr, canon = routed
        if scope == f"cat:{cat}":
            if attr in attributes and not attributes[attr]:
                attributes[attr] = canon
                return "assigned"
            else:
                # already assigned – record as ambiguous
                return "ambiguous"
        # shared scope is handled by per-record common/* aggregation, not here
        return None

    # silhouette_or_length
    sil = it.get("silhouette_or_length")
    if sil:
        result = _try_assign(sil)
        if result == "leftover":
            extras["leftover_details"].append(f"silhouette_or_length={sil}")
        elif result == "ambiguous":
            extras["ambiguous_details"].append(f"silhouette_or_length={sil}")

    # additional_details (free array)
    for d in (it.get("additional_details") or []):
        if not d:
            continue
        result = _try_assign(d)
        if result == "leftover":
            extras["leftover_details"].append(d)
        elif result == "ambiguous":
            extras["ambiguous_details"].append(d)

    item_out = {"cat": cat, "sub_cat": sub_cat, "attributes": attributes}
    return item_out, extras


# ---- Record-level adaptation ----------------------------------------------

def adapt_record(
    their: dict,
    tax: dict,
    inv: dict,
    *,
    image_path: Optional[str] = None,
    brand_full: Optional[str] = None,
) -> dict:
    """Convert one external record to our schema."""
    post_id = their.get("post_id") or "(unknown)"
    label = their.get("label") or {}
    person = label.get("person") or {}
    bg = label.get("background") or {}
    st = label.get("styling") or {}
    items_in = label.get("items") or []

    rec = empty_label_record(f"{post_id}.jpg")
    rec["image"]["path"] = image_path
    # account
    rec["account"] = {
        "brand": brand_full or (their.get("brand") or "").lower() or None,
        "source": "instagram",
        "handle": their.get("handle"),
        "post_url": their.get("post_url"),
        "posted_at": None,
        "metrics": None,
        "caption": None,
        "hashtags": [],
        "_orig_brand": their.get("brand"),
        "post_id": post_id,
    }

    # vlm
    usage = their.get("usage") or {}
    rec["vlm"] = {
        "model": their.get("model"),
        "passes": 1,
        "input_tokens": usage.get("prompt_token_count"),
        "output_tokens": usage.get("candidates_token_count"),
        "labeled_at": their.get("labeled_at"),
        "taxonomy_version": tax.get("version"),
    }

    # items
    extras_per_item = []
    aggregate_colors: list[str] = []
    aggregate_pattern_count: dict[str, int] = defaultdict(int)
    aggregate_graphic: dict[str, int] = defaultdict(int)
    aggregate_fab_count: dict[str, int] = defaultdict(int)
    aggregate_mat_count: dict[str, int] = defaultdict(int)

    for it in items_in:
        item_out, extras = _adapt_item(it, tax, inv)
        # collect common.* candidates from raw item even if cat dropped
        col = (it.get("color") or "").strip().lower()
        if col and col in {c.lower() for c in tax["shared"]["common"]["color"]}:
            canon = next(c for c in tax["shared"]["common"]["color"] if c.lower() == col)
            if canon not in aggregate_colors:
                aggregate_colors.append(canon)
        # pattern / graphic_print
        pat, gp = _norm_pattern(it.get("pattern"))
        if pat:
            aggregate_pattern_count[pat] += 1
        if gp:
            aggregate_graphic[gp] += 1
        # fabrication
        fab = (it.get("fabrication") or "").strip().lower()
        if fab:
            for canon in tax["shared"]["common"]["fabrication"]:
                if canon.lower() == fab:
                    aggregate_fab_count[canon] += 1
                    break
        # material
        mat = (it.get("material") or "").strip().lower()
        if mat:
            for canon in tax["shared"]["common"]["material"]:
                if canon.lower() == mat:
                    aggregate_mat_count[canon] += 1
                    break

        if item_out:
            rec["items"].append(item_out)
        extras_per_item.append(extras)

    rec["detected_categories"] = []
    seen = set()
    for it in rec["items"]:
        if it["cat"] not in seen:
            rec["detected_categories"].append(it["cat"])
            seen.add(it["cat"])

    # common
    rec["common"] = {k: None for k in tax["shared"]["common"].keys()}
    rec["common"]["color"] = aggregate_colors[:3] if aggregate_colors else []
    if aggregate_pattern_count:
        rec["common"]["pattern"] = max(aggregate_pattern_count.items(), key=lambda x: x[1])[0]
    if aggregate_graphic:
        rec["common"]["graphic print"] = max(aggregate_graphic.items(), key=lambda x: x[1])[0]
    if aggregate_fab_count:
        rec["common"]["fabrication"] = max(aggregate_fab_count.items(), key=lambda x: x[1])[0]
    if aggregate_mat_count:
        rec["common"]["material"] = max(aggregate_mat_count.items(), key=lambda x: x[1])[0]

    # model
    rec["model"] = {k: None for k in tax["shared"]["model"].keys()}
    rec["model"]["gender"] = GENDER_MAP.get(person.get("gender"))
    rec["model"]["age group"] = AGE_MAP.get(person.get("age_group"))
    rec["model"]["pose"] = POSE_MAP.get(person.get("pose"))
    rec["model"]["expression"] = EXPRESSION_MAP.get(person.get("expression"))
    rec["model"]["number of people"] = _norm_number_of_people(person.get("number_of_people"))

    # background
    rec["background"] = {k: None for k in tax["shared"]["background"].keys()}
    rec["background"]["location"] = LOCATION_MAP.get(
        (bg.get("location") or "").strip().lower()
    )
    mood = (bg.get("mood") or "").strip()
    if mood and mood in tax["shared"]["background"]["mood"]:
        rec["background"]["mood"] = mood
    rec["background"]["season/weather"] = SEASON_WEATHER_MAP.get(
        (bg.get("season_weather") or "").strip().lower()
    )

    # styling
    rec["styling"] = {k: None for k in tax["shared"]["styling"].keys()}
    rec["styling"]["fashion style"] = FASHION_STYLE_MAP.get(
        (st.get("fashion_style") or "").strip().lower()
    )
    rec["styling"]["overall fashion color tone"] = OVERALL_COLOR_TONE_MAP.get(
        (st.get("overall_color_tone") or "").strip().lower()
    )
    rec["styling"]["coordination method"] = COORDINATION_MAP.get(
        (st.get("coordination_method") or "").strip().lower()
    )

    # free_text
    rec["free_text"] = {
        "caption_summary": None,
        "trend_keywords": [],
        "_notes": (label.get("notes") or "")[:2000] or None,
        "_confidence": label.get("confidence"),
    }

    # _extra: capture everything we couldn't fit
    rec["_extra"] = {
        "items": extras_per_item,
        "person_orig": {k: person.get(k) for k in ("gender","age_group","number_of_people","pose","expression")
                          if person.get(k) is not None and rec["model"].get(_field_for_person(k)) is None},
        "background_orig": {k: bg.get(k) for k in ("location","mood","season_weather")
                              if bg.get(k) is not None and _bg_is_null(rec, k)},
        "styling_orig": {k: st.get(k) for k in ("fashion_style","overall_color_tone","coordination_method")
                            if st.get(k) is not None and _styling_is_null(rec, k)},
    }
    # Drop empty extras buckets to reduce noise
    rec["_extra"] = {k: v for k, v in rec["_extra"].items() if v}

    return rec


def _field_for_person(k: str) -> str:
    return {
        "gender": "gender", "age_group": "age group",
        "number_of_people": "number of people",
        "pose": "pose", "expression": "expression",
    }[k]

def _bg_is_null(rec: dict, k: str) -> bool:
    m = {"location":"location","mood":"mood","season_weather":"season/weather"}
    return rec["background"].get(m[k]) is None

def _styling_is_null(rec: dict, k: str) -> bool:
    m = {"fashion_style":"fashion style",
         "overall_color_tone":"overall fashion color tone",
         "coordination_method":"coordination method"}
    return rec["styling"].get(m[k]) is None


__all__ = [
    "BRAND_CODE_TO_FULL",
    "build_inverse_index",
    "adapt_record",
]
