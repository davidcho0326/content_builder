"""
브랜드 DNA 추출 — Gemini VLM 이미지 분석
듀베티카 _dna/full_dna_report.json 구조 동일 적용
Discovery + MLB 이미지 병렬 분석
"""

import sys, io, os, json, time, base64

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
load_dotenv(project_root / ".env")

from google import genai
from google.genai import types

ANALYSIS_PROMPT = """Analyze this fashion brand image. Return a JSON object with exactly these fields:

{
  "image_type": "marketing" | "product" | "graphic",
  "garment_type": "specific garment name (e.g. windbreaker, crop top, cargo pants)",
  "target_category": pick ONE from: ["windbreaker", "hoodie_sweatshirt", "tee", "jacket", "pants", "shorts", "skirt", "leggings", "vest", "dress", "set", "accessories", "other"],
  "gender": "male" | "female" | "unisex",
  "color_primary": "main color name",
  "color_secondary": "secondary color name or none",
  "fabric_level": 1-5 (1=ultra smooth, 5=heavy texture),
  "fit_level": 1-5 (1=skin tight, 3=regular, 5=very oversized),
  "sheen_level": 1-5 (1=matte, 3=semi glossy, 5=high gloss),
  "weight_level": 1-5 (1=ultra light, 3=medium, 5=heavy),
  "pose_stance": "stand" | "sit" | "lean" | "walk" | "run" | "squat" | "n/a",
  "pose_framing": "FS" | "MFS" | "MS" | "MCU" | "CU" | "n/a",
  "pose_camera_angle": "eye level" | "low angle" | "high angle" | "n/a",
  "expression_base": "confident" | "cool" | "serene" | "energetic" | "neutral" | "playful" | "fierce" | "n/a",
  "expression_gaze": "camera" | "away" | "down" | "n/a",
  "background_type": "short description of background",
  "background_mood": "outdoor adventure" | "urban street" | "studio neutral" | "lifestyle" | "sporty" | "luxury" | "n/a",
  "background_lighting": "golden hour" | "natural warm" | "cool moody" | "studio soft" | "harsh daylight" | "n/a",
  "background_location_vibe": "outdoor nature" | "urban city" | "studio" | "indoor" | "beach" | "mountain" | "n/a",
  "styling_accessories": "list visible accessories (hat, sunglasses, bag, etc.)",
  "logo_visibility": "prominent" | "subtle" | "none",
  "overall_mood": "1-2 word mood summary"
}

Return ONLY the JSON, no markdown, no explanation."""


from core.api import _get_next_api_key


def analyze_image(img_path, brand):
    try:
        key = _get_next_api_key()
        client = genai.Client(api_key=key)

        with open(img_path, "rb") as f:
            img_data = f.read()

        ext = img_path.suffix.lower()
        mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"

        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=img_data, mime_type=mime),
                        types.Part.from_text(text=ANALYSIS_PROMPT),
                    ],
                )
            ],
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )

        result = json.loads(response.text)
        result["file"] = img_path.name
        result["source"] = (
            "instagram" if "instagram" in str(img_path) else "official-site"
        )
        return result

    except Exception as e:
        return {
            "file": img_path.name,
            "error": str(e),
            "source": "instagram" if "instagram" in str(img_path) else "official-site",
        }


def collect_images(brand_dir):
    images = []
    for subdir in [
        "instagram",
        "official-site/women",
        "official-site/men",
        "official-site/karina_summer",
    ]:
        d = brand_dir / subdir
        if d.exists():
            for f in sorted(d.glob("*.jpg")):
                images.append(f)
            for f in sorted(d.glob("*.png")):
                images.append(f)
            for f in sorted(d.glob("*.webp")):
                images.append(f)
    return images


def aggregate_results(results):
    stats = {
        "total": len(results),
        "marketing_count": 0,
        "product_count": 0,
        "graphic_count": 0,
        "error_count": 0,
        "categories": {},
        "genders": {},
        "pose_stances": {},
        "expression_bases": {},
        "background_moods": {},
        "background_locations": {},
        "color_primaries": {},
        "logo_visibility": {},
        "overall_moods": {},
    }

    for r in results:
        if "error" in r:
            stats["error_count"] += 1
            continue

        it = r.get("image_type", "")
        if it == "marketing":
            stats["marketing_count"] += 1
        elif it == "product":
            stats["product_count"] += 1
        elif it == "graphic":
            stats["graphic_count"] += 1

        for field, key in [
            ("target_category", "categories"),
            ("gender", "genders"),
            ("pose_stance", "pose_stances"),
            ("expression_base", "expression_bases"),
            ("background_mood", "background_moods"),
            ("background_location_vibe", "background_locations"),
            ("color_primary", "color_primaries"),
            ("logo_visibility", "logo_visibility"),
            ("overall_mood", "overall_moods"),
        ]:
            val = r.get(field, "n/a")
            if isinstance(val, str):
                val = val.lower().strip()
            stats[key][val] = stats[key].get(val, 0) + 1

    return stats


def run_brand(brand_name, brand_dir):
    images = collect_images(brand_dir)
    print(f"[{brand_name}] {len(images)} images to analyze")

    if not images:
        print(f"[{brand_name}] No images found!")
        return

    results = []
    success = 0
    errors = 0

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(analyze_image, img, brand_name): img for img in images
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            if "error" in result:
                errors += 1
            else:
                success += 1
            total = success + errors
            if total % 20 == 0:
                print(
                    f"[{brand_name}] {total}/{len(images)} ({success} ok, {errors} err)"
                )

    print(f"[{brand_name}] Analysis done: {success} ok / {errors} errors")

    stats = aggregate_results(results)
    stats["marketing_results"] = [
        r for r in results if r.get("image_type") == "marketing"
    ]
    stats["product_results"] = [r for r in results if r.get("image_type") == "product"]

    dna_dir = brand_dir / "_dna"
    dna_dir.mkdir(exist_ok=True)

    with open(dna_dir / "full_dna_report.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    with open(dna_dir / "all_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"[{brand_name}] Saved to {dna_dir}/")
    print(f"  Categories: {json.dumps(stats['categories'], ensure_ascii=False)}")
    print(f"  BG Moods: {json.dumps(stats['background_moods'], ensure_ascii=False)}")
    print(
        f"  Colors: {json.dumps(dict(sorted(stats['color_primaries'].items(), key=lambda x: -x[1])[:10]), ensure_ascii=False)}"
    )

    return stats


def main():
    base = Path("db/strategy-cut-builder")

    print("=" * 60)
    print("Brand DNA Extraction — Gemini VLM Analysis")
    print("=" * 60)

    with ThreadPoolExecutor(max_workers=2) as executor:
        f_dx = executor.submit(run_brand, "Discovery", base / "discovery")
        f_mlb = executor.submit(run_brand, "MLB", base / "mlb")
        dx_stats = f_dx.result()
        mlb_stats = f_mlb.result()

    print("\n=== COMPLETE ===")


if __name__ == "__main__":
    main()
