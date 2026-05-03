# WORKFLOW_BYPASS_OK: strategy-cut-builder custom prompt pipeline (2026-04-30)
"""Generate Duvetica lifestyle cuts — trend silhouette x Duvetica DNA transformation

Takes competitor trend images (silhouette reference) + Duvetica official product images (brand reference)
and generates Quiet Luxury Mediterranean resort lifestyle cuts.

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/generate_duvetica_lifestyle.py
"""

import json
import time
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv

load_dotenv()

from PIL import Image
from google import genai
from google.genai import types

from core.config import IMAGE_MODEL
from core.api import _get_next_api_key, _pil_to_part

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TREND_DIR = PROJECT_ROOT / "db" / "strategy-cut-builder" / "trend-images"
BRAND_DIR = PROJECT_ROOT / "db" / "strategy-cut-builder" / "duvetica" / "official-site"
OUTPUT_BASE = PROJECT_ROOT / "Fnf_studio_outputs" / "strategy-cut-builder" / "duvetica"

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = OUTPUT_BASE / f"{TIMESTAMP}_lifestyle_cuts"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SCENARIOS = [
    {
        "id": "WJ_01",
        "category": "woven_jacket",
        "trend_image": "moncler-jackets/moncler_jacket_13.jpg",
        "trend_desc": "hooded windbreaker, pale beige, relaxed premium casual",
        "brand_refs": [
            "women/casalina_BGS/casalina_BGS_01.jpg",
            "women/osilo/osilo_05.jpg",
        ],
    },
    {
        "id": "WJ_02",
        "category": "woven_jacket",
        "trend_image": "moncler-jackets/moncler_jacket_01.jpg",
        "trend_desc": "cropped utility jacket, beige, resort leisure",
        "brand_refs": [
            "women/casalina_BGS/casalina_BGS_01.jpg",
            "women/regia/regia_06.jpg",
        ],
    },
    {
        "id": "WJ_03",
        "category": "woven_jacket",
        "trend_image": "moncler-jackets/moncler_jacket_04.jpg",
        "trend_desc": "utility hooded jacket, beige with yellow layers, sophisticated utilitarian",
        "brand_refs": [
            "women/osilo/osilo_05.jpg",
            "women/gaeta_light_NYD/gaeta_light_NYD_01.jpg",
        ],
    },
    {
        "id": "WJ_04",
        "category": "woven_jacket",
        "trend_image": "moncler-jackets/moncler_jacket_27.jpg",
        "trend_desc": "lightweight technical jacket, pale blue-grey, sophisticated outdoor",
        "brand_refs": [
            "women/casalina_BKS/casalina_BKS_05.jpg",
            "women/regia/regia_06.jpg",
        ],
    },
    {
        "id": "WJ_05",
        "category": "woven_jacket",
        "trend_image": "prada/prada_13.jpg",
        "trend_desc": "harrington jacket, cream with dark brown leather collar, vintage luxury",
        "brand_refs": [
            "women/osilo/osilo_05.jpg",
            "women/casalina_BGS/casalina_BGS_01.jpg",
        ],
    },
    {
        "id": "WJ_06",
        "category": "woven_jacket",
        "trend_image": "prada/prada_14.jpg",
        "trend_desc": "cropped utility jacket, beige, minimalist luxury utility",
        "brand_refs": [
            "women/casalina_BGS/casalina_BGS_01.jpg",
            "women/gaeta_light_NYD/gaeta_light_NYD_01.jpg",
        ],
    },
    {
        "id": "SETUP_01",
        "category": "setup",
        "trend_image": "moncler/moncler_05.jpg",
        "trend_desc": "gingham tie-neck romper, brown and white, preppy sophisticated",
        "brand_refs": [
            "women/casalina_BKS/casalina_BKS_05.jpg",
            "women/bagnone_shorts_NYD/bagnone_shorts_NYD_01.jpg",
        ],
    },
    {
        "id": "SETUP_02",
        "category": "setup",
        "trend_image": "moncler/moncler_29.jpg",
        "trend_desc": "eyelet drawstring shorts, crisp white, relaxed resort luxury",
        "brand_refs": [
            "women/bagnone_shorts_PKS/bagnone_shorts_PKS_01.jpg",
            "women/casalina_BKS/casalina_BKS_05.jpg",
        ],
    },
    {
        "id": "SETUP_03",
        "category": "setup",
        "trend_image": "moncler/moncler_07.jpg",
        "trend_desc": "fleece zip-up hoodie, cream beige with gold-tone hardware, cozy premium",
        "brand_refs": [
            "women/casalina_BGS/casalina_BGS_01.jpg",
            "women/osilo/osilo_05.jpg",
        ],
    },
]

PROMPT_TEMPLATE = """You are creating a DUVETICA 27SS campaign image.

BRAND DNA:
- Concept: Quiet Luxury — understated elegance, never loud
- Lifestyle: Premium Mediterranean Resort, Luxury Wellness
- Color palette: Ivory (IVL), Cream Stone (CRS), Beige Sand (BGS), Sage, Olive — earthy neutrals 70%, muted key colors 20%, warm accent 10%

CRITICAL VISUAL QUALITIES (what makes DUVETICA premium):
- SHEEN: Soft semi-matte finish. Not full matte (looks cheap), not glossy (looks sporty). Light catches the fabric surface with a subtle, sophisticated sheen — like morning light on linen curtains
- TEXTURE: Lightweight technical nylon that looks DENSE and premium. Fine weave visible up close. Not papery or plasticky
- DRAPE: Soft, fluid movement. The jacket falls naturally without stiff creases
- HARDWARE: Minimal, tone-on-tone zippers and pulls. Gold-tone or matte metal only

SILHOUETTE REFERENCE (Image 1 - TREND):
Keep this silhouette and proportions: {trend_desc}
- Maintain the overall shape, length, and fit from this image
- Change ONLY the surface: fabric texture, color, sheen, and background

BRAND REFERENCES (Images 2-3 - DUVETICA):
Match the fabric quality, color tone, and premium feeling from these actual Duvetica products.

GENERATE:
A single fashion editorial photo of a female model (Asian, 20s, natural beauty) wearing a DUVETICA {category_kr} with:
- The silhouette from Image 1 transformed into Duvetica DNA
- Fabric: lightweight premium technical nylon, soft semi-matte sheen, dense weave
- Color: {color_direction}
- Background: Mediterranean resort — {bg_direction}
- Lighting: warm natural light, soft diffused, golden hour warmth
- Expression: cool and serene — calm direct gaze, closed relaxed mouth, effortless confidence
- Pose: {pose_direction}
- Camera: {camera_direction}

NO bright colors, NO sporty graphics, NO logos visible, NO street/urban vibe.
The image should feel like a page from a luxury resort magazine — quiet, warm, sophisticated."""


def get_color_direction(scenario_id: str) -> str:
    colors = [
        "warm ivory/cream (IVL tone) — the lightest Duvetica neutral",
        "beige sand (BGS) — warm sandy neutral with slight warmth",
        "sage green (SAGE) — muted earthy green, Mediterranean plant tone",
        "cream stone (CRS) with olive accents",
        "oatmeal heather — soft marled neutral",
        "bordeaux brown (BRD) — deep warm brown, leather tone",
    ]
    idx = int(scenario_id.split("_")[1]) - 1
    return colors[idx % len(colors)]


def get_bg_direction(scenario_id: str) -> str:
    bgs = [
        "white plaster villa terrace with terracotta tiles, turquoise pool visible in background, bougainvillea flowers",
        "stone-wall Mediterranean garden, cypress trees, warm sandstone path, blue sky",
        "resort poolside deck, teak wood sun loungers, turquoise water reflection on skin",
        "European coastal town street, cream-colored buildings, vintage scooter, warm shadows",
        "yacht deck with cream canvas, teak wood floor, deep blue sea horizon, golden hour light",
        "villa interior courtyard, arched doorways, natural stone floor, diffused sunlight through linen curtains",
    ]
    idx = int(scenario_id.split("_")[1]) - 1
    return bgs[idx % len(bgs)]


def get_pose_direction(category: str) -> str:
    if category == "setup":
        return "standing relaxed, weight on one leg, one hand holding a straw tote bag, body angled 3/4 to camera"
    return "standing with subtle lean, arms relaxed at sides, body facing camera with slight 3/4 angle, confident but effortless"


def get_camera_direction(scenario_id: str) -> str:
    cameras = [
        "full body shot (FS), eye level, front angle",
        "medium full shot (MFS), eye level, slight side angle",
        "full body shot (FS), eye level, 3/4 angle",
        "medium shot (MS), eye level, front angle",
        "full body shot (FS), slightly low angle, front",
        "medium full shot (MFS), eye level, front angle",
    ]
    idx = int(scenario_id.split("_")[1]) - 1
    return cameras[idx % len(cameras)]


def load_image(rel_path: str, base_dir: Path) -> Image.Image:
    full_path = base_dir / rel_path
    img = Image.open(full_path).convert("RGB")
    if img.width > 1200 or img.height > 1200:
        img.thumbnail((1200, 1200), Image.LANCZOS)
    return img


def generate_scenario(scenario: dict) -> dict:
    sid = scenario["id"]
    category = scenario["category"]
    category_kr = (
        "woven_jacket (hooded windbreaker)"
        if category == "woven_jacket"
        else "setup (zip-up + matching shorts)"
    )

    prompt = PROMPT_TEMPLATE.format(
        trend_desc=scenario["trend_desc"],
        category_kr=category_kr,
        color_direction=get_color_direction(sid),
        bg_direction=get_bg_direction(sid),
        pose_direction=get_pose_direction(category),
        camera_direction=get_camera_direction(sid),
    )

    trend_img = load_image(scenario["trend_image"], TREND_DIR)
    brand_imgs = [load_image(ref, BRAND_DIR) for ref in scenario["brand_refs"]]

    parts = [types.Part(text=prompt)]
    parts.append(
        types.Part(
            text="[TREND SILHOUETTE REFERENCE - keep this shape, change surface]:"
        )
    )
    parts.append(_pil_to_part(trend_img))
    for i, bimg in enumerate(brand_imgs):
        parts.append(
            types.Part(
                text=f"[DUVETICA BRAND REFERENCE {i+1} - match this fabric quality and color]:"
            )
        )
        parts.append(_pil_to_part(bimg))

    client = genai.Client(api_key=_get_next_api_key())

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=IMAGE_MODEL,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(
                    temperature=0.8,
                    response_modalities=["IMAGE", "TEXT"],
                    image_config=types.ImageConfig(),
                ),
            )

            for part in response.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    import io

                    img_data = part.inline_data.data
                    result_img = Image.open(io.BytesIO(img_data)).convert("RGB")

                    out_path = OUTPUT_DIR / f"{sid}_{category}.png"
                    result_img.save(out_path, "PNG")

                    trend_copy = OUTPUT_DIR / f"{sid}_input_trend.jpg"
                    trend_img.save(trend_copy, "JPEG", quality=90)

                    with open(
                        OUTPUT_DIR / f"{sid}_prompt.txt", "w", encoding="utf-8"
                    ) as f:
                        f.write(f"=== {sid} ({category}) ===\n")
                        f.write(f"Trend: {scenario['trend_image']}\n")
                        f.write(f"Brand refs: {scenario['brand_refs']}\n\n")
                        f.write(prompt)

                    print(
                        f"  [OK] {sid}: {out_path.name} ({result_img.size[0]}x{result_img.size[1]})"
                    )
                    return {
                        "id": sid,
                        "status": "ok",
                        "output": str(out_path),
                        "size": result_img.size,
                    }

            print(f"  [WARN] {sid}: no image in response")
            return {"id": sid, "status": "no_image"}

        except Exception as e:
            if attempt < 2:
                print(f"  [RETRY] {sid}: {e}")
                time.sleep((attempt + 1) * 5)
                continue
            print(f"  [FAIL] {sid}: {e}")
            return {"id": sid, "status": "error", "error": str(e)}


def main():
    print(f"{'=' * 60}")
    print(f"DUVETICA Lifestyle Cut Generator")
    print(f"Scenarios: {len(SCENARIOS)} (WJ: 6, Setup: 3)")
    print(f"Output: {OUTPUT_DIR}")
    print(f"{'=' * 60}")

    results = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(generate_scenario, s): s for s in SCENARIOS}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)

    ok = sum(1 for r in results if r["status"] == "ok")
    fail = sum(1 for r in results if r["status"] != "ok")

    config = {
        "timestamp": TIMESTAMP,
        "scenarios": len(SCENARIOS),
        "success": ok,
        "failed": fail,
        "model": IMAGE_MODEL,
        "results": results,
    }
    with open(OUTPUT_DIR / "config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"DONE - Success: {ok}/{len(SCENARIOS)}, Failed: {fail}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
