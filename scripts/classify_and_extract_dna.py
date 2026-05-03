# WORKFLOW_BYPASS_OK: strategy-cut-builder DNA extraction (2026-04-30)
"""Classify Duvetica images (product vs marketing) and extract DNA attributes

Phase 1: VLM classifies each image as 'product' or 'marketing'
Phase 2: Extract DNA from each type:
  - Product: silhouette, color, fabric, fit, length, garment_type (5-attribute)
  - Marketing: pose, expression, background (preset format)

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/classify_and_extract_dna.py
"""

import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv

load_dotenv()

from PIL import Image
from google import genai
from google.genai import types

from core.config import VISION_MODEL
from core.api import _get_next_api_key, _pil_to_part

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = PROJECT_ROOT / "db" / "strategy-cut-builder" / "duvetica" / "official-site"
OUTPUT_DIR = INPUT_DIR / "_classified"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CLASSIFY_PROMPT = """You are analyzing a fashion brand (DUVETICA) image. Classify it into one of these categories:

1. "product" - Clean product shot: single garment on white/neutral background, flat lay, detail crop, fabric close-up, or garment-only image WITHOUT a human model
2. "marketing" - Lifestyle/campaign shot: model wearing the clothes, editorial photography, on-model shot, campaign visual

Also extract attributes.

For ALL images:
- garment_type: what type of clothing (e.g., "quilted down jacket", "zip-up hoodie", "tailored shorts", "knit polo")
- color_description: describe the colors you see
- target_category: classify into one of: "woven_jacket" (WJ), "setup" (zip-up + shorts), "down", "knit_polo", "pants", "other"
- fabric: 1-5 (1=natural premium linen/cotton, 2=natural+synthetic mix, 3=mid synthetic, 4=technical/nylon, 5=heavy technical)
- fit: 1-5 (1=skin-tight, 2=slim, 3=regular, 4=semi-oversized, 5=oversized)
- sheen: 1-5 (1=full matte, 2=soft matte, 3=semi, 4=semi-glossy, 5=high gloss)
- weight: 1-5 (1=ultra-light, 2=light, 3=mid, 4=heavy, 5=very heavy)

For "marketing" images ADDITIONALLY extract:
- pose_stance: one of "stand", "sit", "lean", "walk", "lie_back", "recline", "crouch"
- pose_framing: one of "CU" (close-up), "MCU" (medium close-up), "MS" (medium shot), "MFS" (medium full), "FS" (full shot), "LS" (long shot)
- pose_angle: camera angle description (e.g., "eye level", "slightly low angle", "top view")
- expression_base: one of "dreamy", "serene", "candid", "confident", "cool", "neutral"
- expression_eyes: describe the eyes (e.g., "half-closed, dreamy", "direct gaze, calm")
- expression_mouth: describe the mouth (e.g., "closed, relaxed", "slight smile")
- expression_gaze: where the model looks (e.g., "camera", "left", "down", "distant")
- background_type: describe the background setting
- background_colors: dominant background colors
- background_mood: overall mood (e.g., "mediterranean resort", "studio minimal", "urban casual")
- background_lighting: lighting description (e.g., "natural warm", "studio flat", "golden hour")

Respond ONLY with valid JSON. No markdown, no explanation."""

BATCH_SIZE = 5


def analyze_image(img_path: Path) -> dict:
    """Analyze a single image with VLM."""
    client = genai.Client(api_key=_get_next_api_key())
    pil_img = Image.open(img_path).convert("RGB")

    if pil_img.width > 1024 or pil_img.height > 1024:
        pil_img.thumbnail((1024, 1024), Image.LANCZOS)

    parts = [
        types.Part(text=CLASSIFY_PROMPT),
        _pil_to_part(pil_img),
    ]

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=VISION_MODEL,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_modalities=["TEXT"],
                ),
            )
            text = response.text.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            result = json.loads(text)
            result["file"] = img_path.name
            result["path"] = str(img_path)
            return result
        except json.JSONDecodeError:
            if attempt < 2:
                time.sleep(2)
                continue
            return {
                "file": img_path.name,
                "path": str(img_path),
                "error": "JSON parse failed",
                "raw": text[:200],
            }
        except Exception as e:
            if attempt < 2:
                time.sleep((attempt + 1) * 3)
                continue
            return {"file": img_path.name, "path": str(img_path), "error": str(e)}


def collect_images() -> list[Path]:
    """Collect all downloaded images."""
    images = []
    for gender_dir in ["women", "men"]:
        gender_path = INPUT_DIR / gender_dir
        if not gender_path.exists():
            continue
        for product_dir in sorted(gender_path.iterdir()):
            if not product_dir.is_dir():
                continue
            for img_file in sorted(product_dir.glob("*.jpg")) + sorted(
                product_dir.glob("*.png")
            ):
                images.append(img_file)
    return images


def main():
    images = collect_images()
    print(f"{'=' * 60}")
    print(f"DUVETICA DNA Extractor")
    print(f"Images: {len(images)}")
    print(f"{'=' * 60}")

    results = []
    total = len(images)

    with ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
        futures = {executor.submit(analyze_image, img): img for img in images}
        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            results.append(result)
            img_type = result.get("classification", result.get("type", "?"))
            target = result.get("target_category", "?")
            print(f"  [{i}/{total}] {result['file']}: {img_type} / {target}")

    product_results = [
        r
        for r in results
        if r.get("classification") == "product" or r.get("type") == "product"
    ]
    marketing_results = [
        r
        for r in results
        if r.get("classification") == "marketing" or r.get("type") == "marketing"
    ]
    errors = [r for r in results if "error" in r]

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total": len(results),
        "product_count": len(product_results),
        "marketing_count": len(marketing_results),
        "error_count": len(errors),
        "target_categories": {},
        "product_results": product_results,
        "marketing_results": marketing_results,
        "errors": errors,
    }

    for r in results:
        cat = r.get("target_category", "unknown")
        report["target_categories"][cat] = report["target_categories"].get(cat, 0) + 1

    report_path = OUTPUT_DIR / "dna_extraction_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"DONE")
    print(f"  Product: {len(product_results)}")
    print(f"  Marketing: {len(marketing_results)}")
    print(f"  Errors: {len(errors)}")
    print(
        f"  Categories: {json.dumps(report['target_categories'], ensure_ascii=False)}"
    )
    print(f"  Report: {report_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
