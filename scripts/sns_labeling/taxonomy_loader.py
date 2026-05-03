"""Load taxonomy JSON and build prompts/schemas for the 2-pass VLM pipeline.

Pass-1: build_detection_prompt(taxonomy)
Pass-2: build_attribute_prompt(taxonomy, detected_cats, brand_hint)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

# ---- Loading -------------------------------------------------------------

def load_taxonomy(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        tax = json.load(f)
    if "categories" not in tax or "shared" not in tax:
        raise ValueError(f"taxonomy at {path} missing required keys")
    return tax


def category_names(tax: dict) -> list[str]:
    return list(tax["categories"].keys())


# ---- Pass 1: Category Detection -----------------------------------------

DETECTION_TEMPLATE = """You are a fashion image annotator. Look at the image and decide which of the following PRODUCT categories are clearly VISIBLE and worn/shown by the subject(s).

Allowed categories (use these exact strings):
{cat_list}

Rules:
- Only include categories that are CLEARLY visible. Do NOT guess.
- If multiple items of the same category appear, list it only once.
- It is okay to return an empty list if the image shows no fashion items (e.g., pure landscape, text-only graphic).
- Do not invent new category names.

Also detect the shoot context (always answer):
- has_model    : true if at least one human model is in the image, else false.
- has_background: true if a recognizable background/scene is present, else false.
- has_styling  : true if a coordinated outfit (i.e., a styled look, not a flat-lay product) is visible, else false.

Respond ONLY with valid JSON of this shape, no markdown, no commentary:
{{
  "categories": ["Outer", "Bottom"],
  "has_model": true,
  "has_background": true,
  "has_styling": true
}}
"""


def build_detection_prompt(tax: dict) -> str:
    cat_list = "\n".join(f"  - {c}" for c in category_names(tax))
    return DETECTION_TEMPLATE.format(cat_list=cat_list)


# ---- Pass 2: Attribute Extraction ---------------------------------------

ATTRIBUTE_INTRO = """You are a fashion image annotator. Fill the JSON template below from the image.

STRICT RULES:
1. For every attribute key, you MUST choose a value EXACTLY from the provided list. If no value in the list matches what you see, output null. Never invent values.
2. For "items[].sub_cat", choose ONE value from the subcategory list of that category. If unclear, output null.
3. For "common.color", return a list of 1-3 values from the color list (most prominent first). For all other keys, return a single string or null.
4. For "common.brand", only fill in if a logo or brand mark is clearly readable; otherwise null.
5. Free-text fields (under "free_text") are short Korean descriptions: caption_summary = 1 sentence; trend_keywords = up to 3 short phrases capturing visual trends.
6. Output ONLY the JSON below with values filled in. No markdown, no extra prose.
"""


def _kv_lines(mapping: dict[str, list[str]]) -> str:
    """Render attr_key + allowed-values list (one per line)."""
    out = []
    for k, vs in mapping.items():
        v_str = ", ".join(repr(v) for v in vs)
        out.append(f'    - "{k}": [{v_str}]')
    return "\n".join(out)


def build_attribute_schema(tax: dict, detected: Iterable[str]) -> dict:
    """Build the empty schema the VLM should fill (returned as Python dict)."""
    items_template = []
    for cat in detected:
        if cat not in tax["categories"]:
            continue
        info = tax["categories"][cat]
        attr_keys = list(info["attribute_keys"].keys())
        items_template.append(
            {
                "cat": cat,
                "sub_cat": None,
                "attributes": {k: None for k in attr_keys},
            }
        )

    schema = {
        "items": items_template,
        "common": {k: None for k in tax["shared"]["common"].keys()},
        "model": {k: None for k in tax["shared"]["model"].keys()},
        "background": {k: None for k in tax["shared"]["background"].keys()},
        "styling": {k: None for k in tax["shared"]["styling"].keys()},
        "free_text": {"caption_summary": None, "trend_keywords": []},
    }
    # special-case common.color list
    schema["common"]["color"] = []
    return schema


def build_attribute_prompt(
    tax: dict,
    detected: list[str],
    *,
    brand_hint: str | None = None,
) -> str:
    """Build the Pass-2 prompt with the dynamic schema and per-key vocab inline."""
    skeleton = build_attribute_schema(tax, detected)

    # Per-category attribute vocabularies
    cat_blocks = []
    for cat in detected:
        if cat not in tax["categories"]:
            continue
        info = tax["categories"][cat]
        sub_cats = info.get("subcategories", [])
        attr_keys = info.get("attribute_keys", {})
        sub_str = ", ".join(repr(s) for s in sub_cats) if sub_cats else "(none)"
        block = (
            f"### Category: {cat}\n"
            f"  sub_cat (allowed values): [{sub_str}]\n"
            f"  attribute keys + allowed values:\n"
            f"{_kv_lines(attr_keys) if attr_keys else '    (none)'}"
        )
        cat_blocks.append(block)

    # Shared bins
    shared_blocks = []
    for bin_name in ("common", "model", "background", "styling"):
        keys = tax["shared"].get(bin_name, {})
        shared_blocks.append(
            f"### Shared: {bin_name}\n{_kv_lines(keys) if keys else '    (none)'}"
        )

    hint = ""
    if brand_hint:
        hint = (
            f"\nBrand context (caller-provided, use as a hint only — DO NOT force-fill if not visible): {brand_hint}\n"
        )

    schema_str = json.dumps(skeleton, ensure_ascii=False, indent=2)

    return (
        f"{ATTRIBUTE_INTRO}\n"
        f"{hint}\n"
        f"## Allowed vocabulary for detected categories:\n"
        + "\n\n".join(cat_blocks)
        + "\n\n## Allowed vocabulary for shared bins:\n"
        + "\n\n".join(shared_blocks)
        + "\n\n## Fill this JSON exactly (replace nulls with values; keep keys; output JSON only):\n"
        f"```json\n{schema_str}\n```\n"
    )


# ---- Validation: clamp VLM output to closed vocabulary -----------------

def clamp_to_vocab(tax: dict, raw: dict) -> tuple[dict, list[str]]:
    """Force VLM output to taxonomy values; return (cleaned_dict, warnings)."""
    warnings: list[str] = []

    def _coerce(value, allowed: list[str], path: str):
        if value in (None, "", []):
            return None
        if isinstance(value, list):
            cleaned = []
            for v in value:
                cv, warn = _coerce_scalar(v, allowed, path)
                if warn:
                    warnings.append(warn)
                if cv is not None:
                    cleaned.append(cv)
            return cleaned or None
        return _coerce_scalar(value, allowed, path)[0]

    def _coerce_scalar(value, allowed: list[str], path: str):
        if value is None or value == "":
            return None, None
        s = str(value).strip()
        if s.lower() == "null":
            return None, None
        if s in allowed:
            return s, None
        # case-insensitive match
        lower_map = {a.lower(): a for a in allowed}
        if s.lower() in lower_map:
            return lower_map[s.lower()], None
        return None, f"out-of-vocab @ {path}: {value!r}"

    out = {
        "items": [],
        "common": {},
        "model": {},
        "background": {},
        "styling": {},
        "free_text": raw.get("free_text") or {"caption_summary": None, "trend_keywords": []},
    }

    # items
    for it in raw.get("items") or []:
        cat = it.get("cat")
        if cat not in tax["categories"]:
            warnings.append(f"unknown cat in items: {cat!r}")
            continue
        cat_info = tax["categories"][cat]
        sub_allowed = cat_info["subcategories"]
        attrs_allowed = cat_info["attribute_keys"]

        sub_val, warn = _coerce_scalar(it.get("sub_cat"), sub_allowed, f"items[{cat}].sub_cat")
        if warn:
            warnings.append(warn)
        attrs_clean = {}
        for k, allowed in attrs_allowed.items():
            v = (it.get("attributes") or {}).get(k)
            cv = _coerce(v, allowed, f"items[{cat}].attributes.{k}")
            attrs_clean[k] = cv
        out["items"].append({"cat": cat, "sub_cat": sub_val, "attributes": attrs_clean})

    # shared bins
    for bin_name in ("common", "model", "background", "styling"):
        bin_keys = tax["shared"].get(bin_name, {})
        bin_in = raw.get(bin_name) or {}
        for k, allowed in bin_keys.items():
            v = bin_in.get(k)
            cv = _coerce(v, allowed, f"{bin_name}.{k}")
            out[bin_name][k] = cv

    return out, warnings


__all__ = [
    "load_taxonomy",
    "category_names",
    "build_detection_prompt",
    "build_attribute_prompt",
    "build_attribute_schema",
    "clamp_to_vocab",
]
