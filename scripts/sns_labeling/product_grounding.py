"""Product-first outfit grounding for IMC campaign image generation.

This module moves product selection before image generation. The generated
campaign image receives the influencer reference as the pose/composition anchor
and exactly one selected product image as a garment-fit anchor. Product images
often include a model wearing the garment; that model is intentionally ignored
so the influencer reference remains the only human/pose source.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Optional

from sns_labeling.product_router import (
    ProductMatch,
    route_bottom_product,
    route_hero_product,
)


CODE_LABELS = {
    "TS": "top / tee",
    "WJ": "top / wind jacket",
    "DJ": "top / denim jacket",
    "SET": "set-up",
    "SH": "shoes",
    "WP": "bottom / wide pants",
    "PT": "bottom / pants",
}

TOP_CODES = {"TS", "WJ", "DJ", "SET"}
BOTTOM_CODES = {"WP", "PT"}


def _clean_token(s: str) -> str:
    s = Path(s).stem if "." in s else s
    s = re.sub(r"^(representative_)?V\d+_src\d+_", "", s, flags=re.I)
    s = re.sub(r"__variant_[A-Fa-f0-9]+", "", s)
    return re.sub(r"[_-]+", " ", s).strip()


def _infer_color(match: ProductMatch) -> str:
    names = [_clean_token(match.hero_image.name)]
    for p in match.color_variants[:3]:
        names.append(_clean_token(p.name))
    joined = " / ".join(n for n in names if n)
    return joined or "see product image"


def _brief_from_match(match: ProductMatch, role: str) -> dict:
    category = CODE_LABELS.get(match.code, CODE_LABELS.get(match.code_folder, match.code))
    color = _infer_color(match)
    strategy = match.hero_strategy or ""
    reference_type = (
        "model-worn fit/length reference"
        if "representative" in strategy
        else "product-only packshot/detail reference"
    )
    must_preserve = [
        "exact color and color blocking from product image",
        "logo/graphic placement and scale",
        "silhouette, length, fit, and fabric drape",
        "visible material texture and seams",
    ]
    if role == "bottom":
        must_preserve = [
            "exact pant color from product image",
            "waistline position and wide-leg volume",
            "fabric drape and crease direction",
            "hem width and length",
        ]

    return {
        "role": role,
        "code": match.code,
        "code_folder": match.code_folder,
        "category": category,
        "lifestyle": match.lifestyle_folder,
        "source_file": str(match.hero_image).replace("\\", "/"),
        "source_type": reference_type,
        "hero_strategy": strategy,
        "color_signal": color,
        "must_preserve": must_preserve,
        "ignore_from_product_image": [
            "the product-photo model's face, body, pose, proportions, and gesture",
            "the product-photo background, lighting, camera angle, crop, and styling",
            "any non-selected garments, bags, accessories, shoes, or props in the product image",
        ],
    }


def _auto_focus(spec, top: Optional[ProductMatch], bottom: Optional[ProductMatch]) -> str:
    hero_code = ((spec.hero_garment or {}).get("code") or "").strip().upper()
    if hero_code in BOTTOM_CODES and bottom:
        return "bottom"
    if hero_code in TOP_CODES and top:
        return "top"
    if top:
        return "top"
    if bottom:
        return "bottom"
    return "top"


def build_outfit_manifest(spec, *, focus: str = "auto") -> Optional[dict]:
    """Resolve exactly one top-or-bottom product for the campaign."""
    top = route_hero_product(spec)
    bottom = route_bottom_product(spec)
    if top is None and bottom is None:
        return None
    requested_focus = (focus or "auto").strip().lower()
    selected_role = requested_focus if requested_focus in {"top", "bottom"} else _auto_focus(spec, top, bottom)
    selected = top if selected_role == "top" else bottom
    if selected is None:
        selected_role = "bottom" if selected_role == "top" else "top"
        selected = bottom if selected_role == "bottom" else top
    if selected is None:
        return None

    selected_brief = _brief_from_match(selected, selected_role)
    companion_role = "bottom" if selected_role == "top" else "top"
    manifest = {
        "schema_version": "single-product-grounding-2.0",
        "mode": "reference_pose_single_product_campaign_generation",
        "brand": spec.brand,
        "season": spec.season,
        "lifestyle": spec.lifestyle,
        "requested_focus": requested_focus,
        "selected_role": selected_role,
        "selected_match": selected.to_dict(),
        "candidate_top_match": top.to_dict() if top else None,
        "candidate_bottom_match": bottom.to_dict() if bottom else None,
        # Backward-compatible active slots. Only the selected product is active.
        "top_match": selected.to_dict() if selected_role == "top" else None,
        "bottom_match": selected.to_dict() if selected_role == "bottom" else None,
        "product_brief": {
            "selected": selected_brief,
            selected_role: selected_brief,
            companion_role: {
                "role": companion_role,
                "mode": "generated_by_model",
                "instruction": (
                    f"Generate the {companion_role} garment, bags, accessories, "
                    "shoes, and styling from the campaign tone rather than from a product image."
                ),
            },
            "global_rules": [
                "Image 1, the influencer reference, is the only source for pose, body position, composition, and camera angle.",
                "Image 2, the product image, is only a fit/length/detail reference for the selected garment.",
                "If the product image contains a person, ignore that person's face, body, pose, proportions, background, and styling.",
                "Use exactly one fixed product garment: the selected top or selected bottom, never both.",
                "Generate all non-selected garments, bags, accessories, shoes, and props to match the scene mood.",
                "Generate the editorial image with the selected product from the beginning; do not paste or swap it later.",
            ],
        },
    }
    return manifest


def write_outfit_manifest(manifest: dict, out_dir: Path) -> None:
    """Write product manifests and copy selected product images for galleries."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "outfit_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    selected_role = manifest.get("selected_role")
    slots = []
    if manifest.get("selected_match"):
        slots.append(("selected_match", "selected_product"))
    if selected_role == "top" and manifest.get("top_match"):
        slots.append(("top_match", "hero_product"))
    if selected_role == "bottom" and manifest.get("bottom_match"):
        slots.append(("bottom_match", "bottom_product"))

    seen: set[str] = set()
    for key, prefix in slots:
        match = manifest.get(key)
        if not match:
            continue
        src = Path(match["hero_image"])
        identity = f"{prefix}:{src}"
        if identity in seen:
            continue
        seen.add(identity)
        (out_dir / f"{prefix}.json").write_text(
            json.dumps(match, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if src.exists():
            try:
                shutil.copy2(src, out_dir / f"{prefix}_used{src.suffix}")
            except Exception:
                pass


def product_image_paths(manifest: Optional[dict]) -> list[Path]:
    """Return product image paths in prompt/input order.

    New manifests return exactly one selected product path. Older manifests
    without `selected_match` preserve their previous top/bottom behavior.
    """
    if not manifest:
        return []
    selected = manifest.get("selected_match")
    if selected:
        p = Path(selected.get("hero_image") or "")
        return [p] if p.exists() else []

    paths: list[Path] = []
    for key in ("top_match", "bottom_match"):
        match = manifest.get(key)
        if not match:
            continue
        p = Path(match.get("hero_image") or "")
        if p.exists():
            paths.append(p)
    return paths


def format_product_prompt_section(manifest: Optional[dict]) -> str:
    """Human-readable product DNA section injected into image prompts."""
    if not manifest:
        return "No product images attached. Use the written WEARING brief only."

    brief = manifest.get("product_brief") or {}
    blocks = []
    selected = brief.get("selected")
    selected_role = manifest.get("selected_role") or (selected or {}).get("role")
    companion_role = "bottom" if selected_role == "top" else "top"
    companion = brief.get(companion_role) or {}
    if selected:
        blocks.append(
            "IMAGE 2 - SELECTED PRODUCT FIT/LENGTH REFERENCE ONLY:\n"
            f"- Selected garment role: {selected_role}\n"
            f"- Category: {selected.get('category')} [{selected.get('code')} -> {selected.get('code_folder')}]\n"
            f"- Lifestyle folder: {selected.get('lifestyle')}\n"
            f"- Product image type: {selected.get('source_type')}\n"
            f"- Color/file signal: {selected.get('color_signal')}\n"
            f"- Preserve only this garment DNA: {', '.join(selected.get('must_preserve') or [])}\n"
            f"- Ignore from product image: {', '.join(selected.get('ignore_from_product_image') or [])}"
        )
    if companion:
        blocks.append(
            "COMPLEMENTARY WARDROBE TO GENERATE:\n"
            f"- Generate the {companion_role}, shoes, bag, accessories, and props from the scene tone.\n"
            "- Do not copy any non-selected garment visible in the product photo.\n"
            "- Keep the full outfit coherent with the influencer reference pose and campaign mood."
        )
    rules = "\n".join(f"- {r}" for r in (brief.get("global_rules") or []))
    return "\n\n".join(blocks + [f"PRODUCT-FIRST RULES:\n{rules}"])


__all__ = [
    "build_outfit_manifest",
    "format_product_prompt_section",
    "product_image_paths",
    "write_outfit_manifest",
]
