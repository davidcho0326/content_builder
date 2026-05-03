# WORKFLOW_BYPASS_OK: strategy-cut-builder DNA extraction (2026-04-30)
"""Extract marketing DNA from Duvetica Instagram images — pose, expression, background

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/extract_instagram_dna.py
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
INSTA_DIR = PROJECT_ROOT / "db" / "strategy-cut-builder" / "duvetica" / "instagram"
SITE_DIR = PROJECT_ROOT / "db" / "strategy-cut-builder" / "duvetica" / "official-site"
OUTPUT_DIR = PROJECT_ROOT / "db" / "strategy-cut-builder" / "duvetica" / "_dna"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MARKETING_PROMPT = """Analyze this DUVETICA fashion image and extract DNA attributes. This is a marketing/campaign image.

Extract ALL of the following as JSON:

{
  "image_type": "marketing" or "product" or "graphic" (text/logo only, no model),
  "garment_type": "what clothing items are visible (e.g. quilted jacket, zip-up hoodie, shorts set, knit polo, wide pants)",
  "target_category": one of "woven_jacket", "setup", "down", "knit_polo", "pants", "other",
  "color_primary": "main garment color",
  "color_secondary": "secondary garment color if any",
  "fabric": 1-5 (1=natural linen/cotton, 2=natural+synthetic, 3=mid, 4=technical, 5=heavy tech),
  "fit": 1-5 (1=skin-tight, 2=slim, 3=regular, 4=semi-oversized, 5=oversized),
  "sheen": 1-5 (1=full matte, 2=soft matte, 3=semi, 4=semi-glossy, 5=high gloss),
  "weight": 1-5 (1=ultra-light, 2=light, 3=mid, 4=heavy, 5=very heavy),

  "pose_stance": one of "stand", "sit", "lean", "walk", "lie_back", "recline", "crouch", "n/a",
  "pose_framing": one of "CU", "MCU", "MS", "MFS", "FS", "LS", "n/a",
  "pose_camera_angle": "eye level / slightly low / slightly high / top view / n/a",
  "pose_body_direction": "facing camera / 3/4 left / 3/4 right / profile left / profile right / back / n/a",
  "pose_arms": "brief description of arm position",
  "pose_legs": "brief description of leg position",

  "expression_base": one of "dreamy", "serene", "candid", "confident", "cool", "neutral", "n/a",
  "expression_eyes": "describe the eyes",
  "expression_mouth": "describe the mouth",
  "expression_gaze": "where the model looks: camera / left / right / down / up / distant / n/a",

  "background_type": "describe the setting (e.g. studio white, outdoor garden, resort pool)",
  "background_colors": "dominant background colors",
  "background_mood": "overall mood (e.g. quiet luxury, casual editorial, resort leisure)",
  "background_lighting": "natural warm / studio flat / golden hour / overcast soft / n/a",
  "background_location_vibe": "Mediterranean / Korean studio / European street / garden / indoor / n/a"
}

If this is a "graphic" image (logo, text-only, no model), fill pose/expression/background with "n/a".
Respond ONLY with valid JSON. No markdown."""


def analyze_image(img_path: Path) -> dict:
    client = genai.Client(api_key=_get_next_api_key())
    pil_img = Image.open(img_path).convert("RGB")
    if pil_img.width > 1024 or pil_img.height > 1024:
        pil_img.thumbnail((1024, 1024), Image.LANCZOS)

    parts = [types.Part(text=MARKETING_PROMPT), _pil_to_part(pil_img)]

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=VISION_MODEL,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(
                    temperature=0.1, response_modalities=["TEXT"]
                ),
            )
            text = (
                response.text.strip().replace("```json", "").replace("```", "").strip()
            )
            result = json.loads(text)
            result["file"] = img_path.name
            result["source"] = (
                "instagram" if "instagram" in str(img_path) else "official"
            )
            return result
        except json.JSONDecodeError:
            if attempt < 2:
                time.sleep(2)
                continue
            return {"file": img_path.name, "error": "JSON parse", "raw": text[:200]}
        except Exception as e:
            if attempt < 2:
                time.sleep((attempt + 1) * 3)
                continue
            return {"file": img_path.name, "error": str(e)}


def collect_all_images() -> list[Path]:
    images = []
    for f in sorted(INSTA_DIR.glob("*.jpg")):
        images.append(f)
    for gender in ["women", "men"]:
        gdir = SITE_DIR / gender
        if not gdir.exists():
            continue
        for pdir in sorted(gdir.iterdir()):
            if not pdir.is_dir():
                continue
            for f in sorted(pdir.glob("*.jpg")) + sorted(pdir.glob("*.png")):
                images.append(f)
    return images


def main():
    images = collect_all_images()
    print(f"{'=' * 60}")
    print(f"DUVETICA Full DNA Extraction")
    print(f"Total images: {len(images)}")
    print(f"{'=' * 60}")

    results = []
    total = len(images)

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(analyze_image, img): img for img in images}
        for i, future in enumerate(as_completed(futures), 1):
            r = future.result()
            results.append(r)
            cat = r.get("target_category", "?")
            itype = r.get("image_type", "?")
            print(f"  [{i}/{total}] {r['file']}: {itype} / {cat}")

    marketing = [r for r in results if r.get("image_type") == "marketing"]
    product = [r for r in results if r.get("image_type") == "product"]
    graphic = [r for r in results if r.get("image_type") == "graphic"]
    errors = [r for r in results if "error" in r]

    categories = {}
    for r in results:
        c = r.get("target_category", "unknown")
        categories[c] = categories.get(c, 0) + 1

    pose_stances = {}
    expr_bases = {}
    bg_vibes = {}
    for r in marketing:
        s = r.get("pose_stance", "n/a")
        pose_stances[s] = pose_stances.get(s, 0) + 1
        e = r.get("expression_base", "n/a")
        expr_bases[e] = expr_bases.get(e, 0) + 1
        b = r.get("background_location_vibe", "n/a")
        bg_vibes[b] = bg_vibes.get(b, 0) + 1

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total": len(results),
        "marketing_count": len(marketing),
        "product_count": len(product),
        "graphic_count": len(graphic),
        "error_count": len(errors),
        "categories": categories,
        "pose_stances": pose_stances,
        "expression_bases": expr_bases,
        "background_vibes": bg_vibes,
        "marketing_results": marketing,
        "product_results": product,
        "graphic_results": graphic,
        "errors": errors,
    }

    report_path = OUTPUT_DIR / "full_dna_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"RESULTS")
    print(
        f"  Marketing: {len(marketing)} | Product: {len(product)} | Graphic: {len(graphic)} | Errors: {len(errors)}"
    )
    print(f"  Categories: {json.dumps(categories, ensure_ascii=False)}")
    print(f"  Poses: {json.dumps(pose_stances, ensure_ascii=False)}")
    print(f"  Expressions: {json.dumps(expr_bases, ensure_ascii=False)}")
    print(f"  Backgrounds: {json.dumps(bg_vibes, ensure_ascii=False)}")
    print(f"  Report: {report_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
