"""Marketing-context-only schema + projection from adapted record.

Drops product info (items[], detected_categories, common, errors, _extra.items)
and keeps marketing dimensions that align with brand-dna's `marketing_dna`:
    - model      (gender / age group / pose / expression / gaze direction /
                  hair style / skin tone / number of people)
    - background (location / mood / season-weather /
                  color tone-filter / shooting composition)
    - styling    (fashion style / coordination method /
                  overall fashion color tone)

Plus retained metadata: image, account, free_text, vlm.
"""
from __future__ import annotations

# CSV column order (flat scalars only; lists/objects joined to strings).
CSV_COLUMNS = [
    "brand", "post_id", "handle", "post_url", "image_path",
    # model
    "gender", "age_group", "pose", "expression", "gaze_direction",
    "hair_style", "skin_tone", "number_of_people",
    # background
    "location", "mood", "season_weather", "color_tone_filter",
    "shooting_composition",
    # styling
    "fashion_style", "coordination_method", "overall_fashion_color_tone",
    # auxiliary
    "confidence", "notes_short",
    "vlm_model", "taxonomy_version", "labeled_at",
]

# Mapping from CSV column → (record path, default).
_MODEL_KEYS = {
    "gender": "gender",
    "age_group": "age group",
    "pose": "pose",
    "expression": "expression",
    "gaze_direction": "gaze direction",
    "hair_style": "hair style",
    "skin_tone": "skin tone",
    "number_of_people": "number of people",
}
_BG_KEYS = {
    "location": "location",
    "mood": "mood",
    "season_weather": "season/weather",
    "color_tone_filter": "color tone/filter",
    "shooting_composition": "shooting composition",
}
_STYLING_KEYS = {
    "fashion_style": "fashion style",
    "coordination_method": "coordination method",
    "overall_fashion_color_tone": "overall fashion color tone",
}


def project_to_marketing(adapted: dict) -> dict:
    """Strict projection: drop product fields, keep marketing context."""
    extra_in = adapted.get("_extra") or {}
    extra_out = {k: extra_in[k] for k in ("person_orig", "background_orig", "styling_orig")
                 if extra_in.get(k)}

    out = {
        "image": dict(adapted.get("image") or {}),
        "account": dict(adapted.get("account") or {}),
        "model": dict(adapted.get("model") or {}),
        "background": dict(adapted.get("background") or {}),
        "styling": dict(adapted.get("styling") or {}),
        "free_text": dict(adapted.get("free_text") or {}),
        "vlm": dict(adapted.get("vlm") or {}),
    }
    if extra_out:
        out["_extra"] = extra_out
    return out


def to_csv_row(rec: dict) -> dict:
    """Flatten a marketing record to a CSV row dict."""
    a = rec.get("account") or {}
    img = rec.get("image") or {}
    m = rec.get("model") or {}
    bg = rec.get("background") or {}
    st = rec.get("styling") or {}
    ft = rec.get("free_text") or {}
    vlm = rec.get("vlm") or {}

    notes = (ft.get("_notes") or "")
    if len(notes) > 280:
        notes = notes[:277] + "..."

    row = {
        "brand": a.get("brand"),
        "post_id": a.get("post_id"),
        "handle": a.get("handle"),
        "post_url": a.get("post_url"),
        "image_path": img.get("path"),
        "confidence": ft.get("_confidence"),
        "notes_short": notes,
        "vlm_model": vlm.get("model"),
        "taxonomy_version": vlm.get("taxonomy_version"),
        "labeled_at": vlm.get("labeled_at"),
    }
    for col, key in _MODEL_KEYS.items():
        row[col] = m.get(key)
    for col, key in _BG_KEYS.items():
        row[col] = bg.get(key)
    for col, key in _STYLING_KEYS.items():
        row[col] = st.get(key)
    return row


__all__ = ["CSV_COLUMNS", "project_to_marketing", "to_csv_row"]
