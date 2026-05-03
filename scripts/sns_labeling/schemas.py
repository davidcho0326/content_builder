"""Output JSON schema + input _meta.csv column constants for the labeling agent."""
from __future__ import annotations

# Columns of the input sidecar `_meta.csv` (folder-level).
META_COLUMNS = (
    "file",        # required, matches image filename
    "post_url",
    "posted_at",   # ISO date string preferred
    "likes",
    "comments",
    "views",
    "saved",
    "caption",
    "hashtags",    # comma- or space-separated tokens; '#' optional
)

# Numeric metric columns (best-effort cast to int; blanks -> None).
META_NUMERIC = ("likes", "comments", "views", "saved")


def empty_label_record(image_file: str) -> dict:
    """Return a fresh skeleton matching the agreed output schema."""
    return {
        "image": {"file": image_file, "path": None, "sha256": None,
                  "width": None, "height": None},
        "account": None,  # filled from _meta.csv if matched
        "detected_categories": [],
        "items": [],            # [{cat, sub_cat, attributes: {...}}]
        "common": {},
        "model": {},
        "background": {},
        "styling": {},
        "free_text": {"caption_summary": None, "trend_keywords": []},
        "vlm": {
            "model": None,
            "passes": 0,
            "input_tokens": None,
            "output_tokens": None,
            "labeled_at": None,
            "taxonomy_version": None,
        },
        "errors": [],
    }


__all__ = ["META_COLUMNS", "META_NUMERIC", "empty_label_record"]
