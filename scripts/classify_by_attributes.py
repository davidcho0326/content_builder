# WORKFLOW_BYPASS_OK: strategy-cut-builder 5-attribute classifier (2026-04-30)
"""5속성 정량 분석 기반 트렌드 이미지 분류

Step 1: VLM이 각 이미지의 5속성(소재/핏/광택/두께/라이프) 수치 추출
Step 2: 듀베티카 DNA 가드레일과 비교
Step 3: A/B/C 등급 판정

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/classify_by_attributes.py
"""

import json
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
TREND_DIR = PROJECT_ROOT / "db" / "strategy-cut-builder" / "trend-images"
OUTPUT_DIR = TREND_DIR / "_classified" / "duvetica"

DUVETICA_GUARDRAIL = {
    "fabric": {
        "min": 1,
        "max": 2,
        "desc": "1=natural premium, 2=natural+synthetic mix",
    },
    "fit": {"min": 3, "max": 4, "desc": "3=regular, 4=semi-over"},
    "sheen": {"min": 1, "max": 3, "desc": "1=full matte, 3=semi-matte"},
    "weight": {"min": 1, "max": 2, "desc": "1=ultra-light, 2=light"},
    "lifestyle": {"min": 1, "max": 1, "desc": "1=premium leisure/resort ONLY"},
}

EXTRACT_PROMPT = """Analyze this fashion garment image and extract 5 attributes as numeric scores (1-5 scale).

ATTRIBUTE DEFINITIONS (score by what you SEE in the photo):

1. FABRIC (1-5):
   1 = Fabric grain visible, natural wrinkles, drapes gently (silk, cashmere, linen)
   2 = Subtle fabric grain, minimal wrinkles, smooth with slight natural texture (cotton blend, light knit)
   3 = Uniform smooth surface, almost no wrinkles, sits close to body (stretch jersey, double knit)
   4 = Perfectly smooth, slight synthetic sheen, looks stretchy and elastic (tech fabric)
   5 = Coated smooth surface, visible light reflection, looks crisp and technical (gore-tex, coated nylon)

2. FIT - analyze the TOP garment (1-5):
   1 = Fabric pressed flat against skin, body contour visible (skin-tight)
   2 = Close to body but not pressed, slight room (slim)
   3 = Fabric hangs naturally, body shape somewhat visible (regular)
   4 = Fabric hangs away from body, body shape partially hidden (semi-oversized)
   5 = Tent-like width, fabric extends far beyond body (very oversized)

   Also note:
   - TOP LENGTH: Where does the hem end? (ribcage / navel / waist / hip bone / mid-hip / below hip / mid-thigh)
   - SLEEVE: Where does the sleeve end? (sleeveless / shoulder / mid-upper-arm / elbow / wrist / over-hand)
   - NECKLINE: (crew / v-neck / high-neck / collar / polo / hood / zip-hood)

3. SHEEN (1-5):
   1 = No light reflection at all, surface looks dry and chalky
   2 = Very subtle soft glow, light is absorbed not reflected
   3 = Slight sheen visible only when fabric moves or catches light at angle
   4 = Visible sheen from front, satin-like smooth reflection
   5 = Mirror-like strong reflection, wet-look or patent shine

4. WEIGHT (1-5):
   1 = Paper-thin, skin almost visible, moves with slightest breeze
   2 = Light, not see-through, floats slightly, folds easily into small creases
   3 = Medium weight, holds its position, only large folds visible
   4 = Heavy, hangs straight down, resists folding
   5 = Very thick rigid, holds shape on its own, does not bend

5. LIFESTYLE (1-5):
   1 = Premium leisure: resort, vacation, Mediterranean, quiet luxury, old money
   2 = Casual commute: daily wear, office-to-street, city walking
   3 = Wellness active: pilates, yoga, running, gym-to-cafe
   4 = Sportive/street: team sports, hip-hop, skateboard, bold graphics
   5 = Outdoor: trail, camping, hiking, technical mountaineering

Respond in this EXACT JSON format (no markdown, no extra text):
{"fabric": 3, "fit": 2, "sheen": 4, "weight": 2, "lifestyle": 3, "top_length": "waist", "sleeve": "wrist", "neckline": "zip-hood", "garment_type": "lightweight down jacket", "color_description": "bright red with black trim", "overall_mood": "sporty athletic"}
"""


def extract_attributes(image_path: Path, brand: str) -> dict:
    """VLM으로 5속성 수치 추출"""
    client = genai.Client(api_key=_get_next_api_key())
    img = Image.open(image_path).convert("RGB")

    max_dim = 1024
    if max(img.size) > max_dim:
        ratio = max_dim / max(img.size)
        img = img.resize(
            (int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS
        )

    parts = [
        types.Part(text=EXTRACT_PROMPT),
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

            attrs = json.loads(text)
            attrs["file"] = image_path.name
            attrs["brand"] = brand
            attrs["path"] = str(image_path)
            return attrs

        except Exception as e:
            if attempt < 2:
                time.sleep((attempt + 1) * 5)
            else:
                return {
                    "fabric": -1,
                    "fit": -1,
                    "sheen": -1,
                    "weight": -1,
                    "lifestyle": -1,
                    "error": str(e)[:200],
                    "file": image_path.name,
                    "brand": brand,
                    "path": str(image_path),
                }


def classify_by_guardrail(attrs: dict) -> dict:
    """5속성 수치를 듀베티카 가드레일과 비교하여 A/B/C 판정"""
    if attrs.get("error") or attrs.get("fabric", -1) < 0:
        attrs["grade"] = "ERROR"
        attrs["verdict"] = "VLM extraction failed"
        return attrs

    within = []
    outside = []
    far_outside = []

    for attr_name, guardrail in DUVETICA_GUARDRAIL.items():
        val = attrs.get(attr_name, 3)
        gmin = guardrail["min"]
        gmax = guardrail["max"]

        if gmin <= val <= gmax:
            within.append(attr_name)
        elif abs(val - gmin) <= 1 or abs(val - gmax) <= 1:
            outside.append((attr_name, val, f"guardrail {gmin}-{gmax}"))
        else:
            far_outside.append((attr_name, val, f"guardrail {gmin}-{gmax}"))

    if len(far_outside) >= 2:
        attrs["grade"] = "C"
        attrs["verdict"] = (
            f"REJECT: {len(far_outside)} attributes far outside guardrail"
        )
    elif len(far_outside) == 1 and far_outside[0][0] == "lifestyle":
        attrs["grade"] = "C"
        attrs["verdict"] = (
            f"REJECT: lifestyle {far_outside[0][1]} incompatible (must be 1)"
        )
    elif len(far_outside) == 1:
        attrs["grade"] = "B"
        attrs["verdict"] = (
            f"MODIFY: {far_outside[0][0]}={far_outside[0][1]} needs conversion"
        )
    elif len(outside) >= 3:
        attrs["grade"] = "B"
        attrs["verdict"] = f"MODIFY: {len(outside)} attributes slightly outside"
    elif len(outside) > 0:
        attrs["grade"] = "B"
        attrs["verdict"] = f"MODIFY: {', '.join(a[0] for a in outside)} need adjustment"
    else:
        attrs["grade"] = "A"
        attrs["verdict"] = "USE AS-IS: all 5 attributes within Duvetica guardrail"

    attrs["within_guardrail"] = within
    attrs["outside_guardrail"] = [(a, v, g) for a, v, g in outside]
    attrs["far_outside_guardrail"] = [(a, v, g) for a, v, g in far_outside]

    color_desc = attrs.get("color_description", "")
    duvetica_colors = [
        "ivory",
        "cream",
        "beige",
        "sand",
        "white",
        "sage",
        "olive",
        "oatmeal",
        "camel",
        "stone",
        "navy",
    ]
    color_match = any(c in color_desc.lower() for c in duvetica_colors)

    if not color_match and attrs["grade"] == "A":
        attrs["grade"] = "B"
        attrs["verdict"] += (
            f" but color '{color_desc}' needs Duvetica palette conversion"
        )
    elif not color_match and attrs["grade"] == "B":
        attrs["verdict"] += f" + color '{color_desc}' needs conversion"

    return attrs


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

    print(f"[START] {len(all_images)} images to classify by 5-attribute system")
    print(
        f"Duvetica guardrail: fabric 1-2, fit 3-4, sheen 1-3, weight 1-2, lifestyle 1"
    )
    print()

    for grade_dir in ["A_use_as_is", "B_modify", "C_reject"]:
        (OUTPUT_DIR / grade_dir).mkdir(parents=True, exist_ok=True)

    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(extract_attributes, img_path, brand): (img_path, brand)
            for img_path, brand in all_images
        }

        for future in as_completed(futures):
            img_path, brand = futures[future]
            try:
                attrs = future.result()
                classified = classify_by_guardrail(attrs)
                results.append(classified)

                grade = classified["grade"]
                f = classified["file"]
                fab = classified.get("fabric", "?")
                fit = classified.get("fit", "?")
                she = classified.get("sheen", "?")
                wei = classified.get("weight", "?")
                lif = classified.get("lifestyle", "?")
                verdict = classified.get("verdict", "")[:60]

                print(
                    f"  [{grade}] {brand}/{f}  fab={fab} fit={fit} she={she} wei={wei} lif={lif}  {verdict}"
                )

                if grade == "A":
                    dest = OUTPUT_DIR / "A_use_as_is" / f"{brand}_{classified['file']}"
                elif grade == "B":
                    dest = OUTPUT_DIR / "B_modify" / f"{brand}_{classified['file']}"
                else:
                    dest = OUTPUT_DIR / "C_reject" / f"{brand}_{classified['file']}"

                shutil.copy2(str(img_path), str(dest))

            except Exception as e:
                print(f"  [ERROR] {brand}/{img_path.name} - {e}")

    a_list = [r for r in results if r.get("grade") == "A"]
    b_list = [r for r in results if r.get("grade") == "B"]
    c_list = [r for r in results if r.get("grade") == "C"]

    print(f"\n{'='*60}")
    print(f"5-ATTRIBUTE CLASSIFICATION COMPLETE")
    print(f"  A (use as-is):  {len(a_list)}")
    print(f"  B (modify):     {len(b_list)}")
    print(f"  C (reject):     {len(c_list)}")
    print(f"  Total:          {len(results)}")
    print(f"{'='*60}")

    if a_list:
        print(f"\n--- Grade A (ready for Duvetica) ---")
        for r in a_list:
            print(
                f"  {r['brand']}/{r['file']} - {r.get('garment_type', '?')} - {r.get('color_description', '?')}"
            )

    if b_list:
        print(f"\n--- Grade B (modify these) ---")
        for r in b_list:
            outside = r.get("outside_guardrail", []) + r.get(
                "far_outside_guardrail", []
            )
            changes = ", ".join(f"{a}={v}(need {g})" for a, v, g in outside)
            print(f"  {r['brand']}/{r['file']} - change: {changes}")

    report_path = OUTPUT_DIR / "classification_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": datetime.now().isoformat(),
                "method": "5-attribute quantitative analysis",
                "guardrail": DUVETICA_GUARDRAIL,
                "total": len(results),
                "grade_A": len(a_list),
                "grade_B": len(b_list),
                "grade_C": len(c_list),
                "results": results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"\nReport: {report_path}")
    print(f"Folders: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
