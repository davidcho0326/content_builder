"""Label a single SNS fashion image via Gemini VLM (2-pass).

Stages:
  1. Pass-1 detection : which product categories are visible.
  2. Pass-2 fill      : VLM fills a category-conditioned schema using closed vocab.
  3. Post-processing  : clamp values to taxonomy, merge account info, package output.

Public API:
    label_image(img_path, *, taxonomy, account=None, model=None) -> dict

CLI (dry-run a single image):
    python -m sns_labeling.label_image \\
        --image  data/duvetica/instagram/insta_001_*.jpg \\
        --taxonomy taxonomy/labeling_taxonomy.json \\
        [--out path.json] [--brand duvetica]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Optional

# allow `python -m sns_labeling.label_image` from project root or scripts/
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR.parent))

from sns_labeling import vlm_client
from sns_labeling.schemas import empty_label_record
from sns_labeling.taxonomy_loader import (
    build_attribute_prompt,
    build_detection_prompt,
    category_names,
    clamp_to_vocab,
    load_taxonomy,
)


def _sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _detect(tax: dict, img, *, model: Optional[str]) -> dict:
    prompt = build_detection_prompt(tax)
    return vlm_client.call_vlm_json(prompt, img, model=model)


def _fill(tax: dict, img, detected: list[str], *, model, brand_hint) -> dict:
    prompt = build_attribute_prompt(tax, detected, brand_hint=brand_hint)
    return vlm_client.call_vlm_json(prompt, img, model=model)


def _validate_detected(tax: dict, raw_dets: list) -> list[str]:
    allowed = set(category_names(tax))
    out: list[str] = []
    seen: set[str] = set()
    for c in raw_dets or []:
        if not isinstance(c, str):
            continue
        if c in allowed and c not in seen:
            out.append(c)
            seen.add(c)
    return out


def label_image(
    img_path: str | Path,
    *,
    taxonomy: dict,
    account: Optional[dict] = None,
    model: Optional[str] = None,
) -> dict:
    img_path = Path(img_path)
    rec = empty_label_record(img_path.name)
    rec["image"]["path"] = str(img_path).replace("\\", "/")
    rec["vlm"]["model"] = model or vlm_client.DEFAULT_MODEL
    rec["vlm"]["taxonomy_version"] = taxonomy.get("version")
    rec["vlm"]["labeled_at"] = _now_iso()
    rec["account"] = account

    try:
        rec["image"]["sha256"] = _sha256(img_path)
        img = vlm_client.preprocess(img_path)
        rec["image"]["width"], rec["image"]["height"] = img.size

        # ---- Pass 1 ----
        p1 = _detect(taxonomy, img, model=model)
        det_data = p1["data"]
        rec["detected_categories"] = _validate_detected(
            taxonomy, det_data.get("categories")
        )
        rec.setdefault("_detection_meta", {})
        rec["_detection_meta"] = {
            "has_model": bool(det_data.get("has_model")),
            "has_background": bool(det_data.get("has_background")),
            "has_styling": bool(det_data.get("has_styling")),
        }
        rec["vlm"]["passes"] = 1
        in_tok = p1["usage"].get("input_tokens") or 0
        out_tok = p1["usage"].get("output_tokens") or 0

        # ---- Pass 2 ----
        if rec["detected_categories"]:
            brand_hint = (account or {}).get("brand") if account else None
            p2 = _fill(
                taxonomy,
                img,
                rec["detected_categories"],
                model=model,
                brand_hint=brand_hint,
            )
            cleaned, warns = clamp_to_vocab(taxonomy, p2["data"])
            rec["items"] = cleaned["items"]
            rec["common"] = cleaned["common"]
            rec["model"] = cleaned["model"]
            rec["background"] = cleaned["background"]
            rec["styling"] = cleaned["styling"]
            rec["free_text"] = cleaned["free_text"]
            rec["vlm"]["passes"] = 2
            in_tok += p2["usage"].get("input_tokens") or 0
            out_tok += p2["usage"].get("output_tokens") or 0
            if warns:
                rec["errors"].extend(f"clamp: {w}" for w in warns)

        rec["vlm"]["input_tokens"] = in_tok or None
        rec["vlm"]["output_tokens"] = out_tok or None
    except Exception as e:
        rec["errors"].append(f"label_image failed: {type(e).__name__}: {e}")

    return rec


# ---- CLI ---------------------------------------------------------------

def _main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Label a single image (dry-run)")
    ap.add_argument("--image", required=True)
    ap.add_argument(
        "--taxonomy",
        default=str(
            Path(__file__).resolve().parents[2]
            / "taxonomy"
            / "labeling_taxonomy.json"
        ),
    )
    ap.add_argument("--out", default=None, help="Output JSON path (default: print)")
    ap.add_argument("--brand", default=None, help="Brand context hint")
    ap.add_argument("--model", default=None, help="Override VLM model")
    args = ap.parse_args()

    tax = load_taxonomy(args.taxonomy)
    account = {"brand": args.brand} if args.brand else None
    rec = label_image(args.image, taxonomy=tax, account=account, model=args.model)

    text = json.dumps(rec, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"[OK] wrote {args.out}")
    else:
        print(text)
    return 0 if not rec["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(_main())
