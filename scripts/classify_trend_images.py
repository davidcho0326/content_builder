# WORKFLOW_BYPASS_OK: strategy-cut-builder trend classifier (2026-04-30)
"""경쟁사 트렌드 이미지를 듀베티카 DNA 기준으로 3등급 분류

등급:
  A - 바로 사용 가능 (듀베티카 리조트 럭셔리 무드 부합)
  B - 수정 후 사용 가능 (실루엣/구조는 OK, 컬러/광택/무드 변환 필요)
  C - 사용 불가 (스포티/스트릿/기능성 과다, 듀베티카 DNA와 불일치)

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/classify_trend_images.py
"""

import json
import os
import shutil
import time
from datetime import datetime
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
STRATEGY_DIR = PROJECT_ROOT / ".claude" / "projects" / "strategy-cut-builder"
TREND_DIR = PROJECT_ROOT / "db" / "strategy-cut-builder" / "trend-images"
OUTPUT_DIR = TREND_DIR / "_classified" / "duvetica"

DUVETICA_DNA_PROMPT = """You are a fashion classification agent for DUVETICA brand.

DUVETICA DNA:
- Positioning: "Old Money Sportive" - Premium Leisure, Quiet Luxury
- Season: Summer Resort
- Lifestyle: Mediterranean villa, resort pool, European coastal cafe, beach club
- Silhouette: Relaxed oversized, soft unstructured, fluid drape
- Fabric: Linen, cotton, silk, satin, boucle, lightweight knit
- Sheen: Matte to slight sheen (level 1-3 out of 5). NO high gloss, NO technical sheen
- Weight: Lightweight to light (level 1-2 out of 5). NO heavy, NO puffy
- Color: Earthy neutrals (ivory, cream, beige, sand, sage, olive), NO neon, NO bright sporty colors
- Mood: Effortless elegance, understated, NOT sporty, NOT athletic, NOT streetwear

CLASSIFICATION RULES:
- Grade A (USE AS-IS): Image already fits Duvetica resort luxury mood. Relaxed silhouette, neutral/earthy colors, lightweight fabric, matte finish, resort/leisure setting. Could be a Duvetica campaign image with minimal changes.
- Grade B (MODIFY): Good silhouette/structure but needs color, sheen, or mood adjustment. Example: nice jacket shape but too sporty in color, or good fabric but too glossy. The FORM is usable, the SURFACE needs Duvetica treatment.
- Grade C (REJECT): Fundamentally incompatible. Too sporty, too technical, too streetwear, too heavy/puffy, bright/neon colors, athletic performance wear, heavy logos, ski/snow gear, etc.

For each image, respond in this EXACT JSON format:
{"grade": "A", "reason": "one sentence why", "keep_from_original": "what to keep", "change_for_duvetica": "what to change", "suggested_duvetica_color": "IVL/CRS/SAGE/etc"}

If grade C: {"grade": "C", "reason": "one sentence why", "incompatible_elements": "list what makes it incompatible"}
"""


def classify_single_image(image_path: Path, brand: str) -> dict:
    """VLM으로 단일 이미지 분류"""
    client = genai.Client(api_key=_get_next_api_key())
    img = Image.open(image_path).convert("RGB")

    max_dim = 1024
    if max(img.size) > max_dim:
        ratio = max_dim / max(img.size)
        img = img.resize(
            (int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS
        )

    parts = [
        types.Part(text=DUVETICA_DNA_PROMPT),
        types.Part(
            text=f"[IMAGE FROM {brand.upper()}] Classify this image for Duvetica compatibility:"
        ),
        _pil_to_part(img),
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
            text = response.candidates[0].content.parts[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            result = json.loads(text)
            result["file"] = image_path.name
            result["brand"] = brand
            result["path"] = str(image_path)
            return result

        except json.JSONDecodeError:
            result = {
                "grade": "B",
                "reason": f"JSON parse failed, raw: {text[:200]}",
                "file": image_path.name,
                "brand": brand,
                "path": str(image_path),
            }
            return result
        except Exception as e:
            if attempt < 2:
                time.sleep((attempt + 1) * 5)
            else:
                return {
                    "grade": "ERROR",
                    "reason": str(e)[:200],
                    "file": image_path.name,
                    "brand": brand,
                    "path": str(image_path),
                }


def main():
    brands = {
        "moncler": TREND_DIR / "moncler",
        "moncler-jackets": TREND_DIR / "moncler-jackets",
        "prada": TREND_DIR / "prada",
    }

    all_images = []
    for brand, folder in brands.items():
        if folder.exists():
            for ext in ("*.jpg", "*.jpeg", "*.png"):
                for f in sorted(folder.glob(ext)):
                    all_images.append((f, brand))

    print(f"Total images to classify: {len(all_images)}")

    for grade_dir in ["A_use_as_is", "B_modify", "C_reject"]:
        (OUTPUT_DIR / grade_dir).mkdir(parents=True, exist_ok=True)

    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(classify_single_image, img_path, brand): (img_path, brand)
            for img_path, brand in all_images
        }

        for future in as_completed(futures):
            img_path, brand = futures[future]
            try:
                result = future.result()
                results.append(result)
                grade = result.get("grade", "ERROR")
                print(
                    f"  [{grade}] {brand}/{result['file']} - {result.get('reason', '')[:80]}"
                )

                if grade == "A":
                    dest = OUTPUT_DIR / "A_use_as_is" / f"{brand}_{result['file']}"
                elif grade == "B":
                    dest = OUTPUT_DIR / "B_modify" / f"{brand}_{result['file']}"
                elif grade == "C":
                    dest = OUTPUT_DIR / "C_reject" / f"{brand}_{result['file']}"
                else:
                    dest = OUTPUT_DIR / "C_reject" / f"{brand}_{result['file']}"

                shutil.copy2(str(img_path), str(dest))

            except Exception as e:
                print(f"  [ERROR] {brand}/{img_path.name} - {e}")

    a_count = len([r for r in results if r.get("grade") == "A"])
    b_count = len([r for r in results if r.get("grade") == "B"])
    c_count = len([r for r in results if r.get("grade") == "C"])

    print(f"\n{'='*60}")
    print(f"Classification complete: {len(results)} images")
    print(f"  A (use as-is):  {a_count}")
    print(f"  B (modify):     {b_count}")
    print(f"  C (reject):     {c_count}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"{'='*60}")

    report_path = OUTPUT_DIR / "classification_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": datetime.now().isoformat(),
                "brand_filter": "duvetica",
                "total": len(results),
                "grade_A": a_count,
                "grade_B": b_count,
                "grade_C": c_count,
                "results": results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
