# WORKFLOW_BYPASS_OK: strategy-cut-builder custom prompt pipeline (2026-04-30)
"""Generate Duvetica lifestyle cuts v2 — Gemini + GPT Image 2 dual generation

Mood reference images as PRIMARY input. Product images for garment detail only.

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/generate_duvetica_lifestyle_v2.py
"""

import json
import io
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
from core.model_utils import (
    generate_gpt_image,
    pil_list_to_temp_files,
    cleanup_temp_files,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MOOD_DIR = Path("C:/Users/AC1060/Downloads/듀베티카")
BRAND_DIR = PROJECT_ROOT / "db" / "strategy-cut-builder" / "duvetica" / "official-site"
OUTPUT_BASE = PROJECT_ROOT / "Fnf_studio_outputs" / "strategy-cut-builder" / "duvetica"

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = OUTPUT_BASE / f"{TIMESTAMP}_lifestyle_v2"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MOOD_REFS = {
    "desert_stone": "07b8e43dd59e481bab62ccaa63955581.jpg",
    "villa_sofa": "65fb8912a289a6a2c5f4b033b7845569.jpg",
    "como_boat": "297990159c1d966fd4cb5f3afc95fafe.jpg",
    "garden_sit": "c011a26256e4ba4bdfd753a22c5cf9e2.jpg",
    "poolside": "f8481cefca86b97fe479b6b59cca79ae.jpg",
    "yacht_read": "92e4ebfa6d48da1ee38fc241290bf152.jpg",
    "pool_sit": "14d2a242bfc922645ca8b4c293afc973.jpg",
    "coastal_stone": "f70e6884e65b4146ade5e7235ae489f3.jpg",
    "villa_stairs": "96a55efb4b532d3c69da944f60979e4d.jpg",
    "boat_sun": "cae687f2b0656dc940c8cb7dbc7dd1b2.jpg",
    "street_vespa": "f5d2823e75ca83f7fc6c4b5fb9768aa8.jpg",
}

SCENARIOS = [
    {
        "id": "WJ_01",
        "category": "woven_jacket",
        "mood_ref": "como_boat",
        "product_ref": "women/casalina_BGS/casalina_BGS_01.jpg",
        "scene": "Italian lake wooden boat, cream leather seats, green mountains, overcast light. Model sitting on boat, one hand near chin, sunglasses, relaxed with wine glass nearby",
        "garment": "Duvetica hooded zip-up windbreaker in warm cream, lightweight technical nylon with soft semi-matte sheen, paired with cream wide-leg trousers",
    },
    {
        "id": "WJ_02",
        "category": "woven_jacket",
        "mood_ref": "garden_sit",
        "product_ref": "women/osilo/osilo_05.jpg",
        "scene": "Mediterranean villa garden, stone balustrade, cypress trees, warm afternoon. Model sitting on stone ledge, sunglasses on, chin on hand, striped tote on ground",
        "garment": "Duvetica hooded windbreaker in ivory, relaxed fit open showing simple top, cream wide-leg linen pants, black leather mule sandals",
    },
    {
        "id": "WJ_03",
        "category": "woven_jacket",
        "mood_ref": "desert_stone",
        "product_ref": "women/regia/regia_06.jpg",
        "scene": "Ancient sandstone ruins, blue sky, golden hour. Model leaning on stone wall looking into distance, editorial and effortless",
        "garment": "Duvetica long hooded windbreaker in sand beige, hip-length, soft fluid drape, matched wide-leg trousers, flat leather sandals",
    },
    {
        "id": "WJ_04",
        "category": "woven_jacket",
        "mood_ref": "villa_sofa",
        "product_ref": "women/casalina_BKS/casalina_BKS_05.jpg",
        "scene": "White plaster villa terrace, white outdoor sofa with cushions, turquoise sea through arched opening. Model reclining, serene, gold statement earrings",
        "garment": "Duvetica cropped hooded zip-up in cream ivory, lightweight fluid, worn loosely open, flowing cream satin skirt",
    },
    {
        "id": "WJ_05",
        "category": "woven_jacket",
        "mood_ref": "yacht_read",
        "product_ref": "women/gaeta_light_NYD/gaeta_light_NYD_01.jpg",
        "scene": "Yacht deck golden hour, teak floor, canvas chair, blue sea horizon, warm backlight. Model in deck chair reading, hair tousled by wind, leather sandals",
        "garment": "Duvetica hooded windbreaker in oatmeal beige, light layer over white tee, white linen trousers",
    },
    {
        "id": "WJ_06",
        "category": "woven_jacket",
        "mood_ref": "street_vespa",
        "product_ref": "women/osilo/osilo_05.jpg",
        "scene": "European coastal town, cream buildings, vintage Vespa, strong sun sharp shadows. Model leaning on scooter, wind in hair",
        "garment": "Duvetica hooded windbreaker in bordeaux brown, cropped, over flowing white dress, hair blowing",
    },
    {
        "id": "SETUP_01",
        "category": "setup",
        "mood_ref": "poolside",
        "product_ref": "women/casalina_BKS/casalina_BKS_05.jpg",
        "scene": "Resort poolside, turquoise water with caustics on skin, sandstone deck, direct sun. Model lying by pool, hand near forehead, dreamy half-closed eyes",
        "garment": "Duvetica hooded zip-up top in light blue with matching shorts, lightweight technical, worn open over swimsuit, fabric catching pool light",
    },
    {
        "id": "SETUP_02",
        "category": "setup",
        "mood_ref": "pool_sit",
        "product_ref": "women/bagnone_shorts_NYD/bagnone_shorts_NYD_01.jpg",
        "scene": "Resort pool edge, feet in turquoise water, plants, warm afternoon. Model sitting at pool edge looking over shoulder, candid, curly hair",
        "garment": "Duvetica half-zip hooded top in cream beige with matching mid-thigh shorts, relaxed fit, drawstring waist",
    },
    {
        "id": "SETUP_03",
        "category": "setup",
        "mood_ref": "coastal_stone",
        "product_ref": "women/casalina_BGS/casalina_BGS_01.jpg",
        "scene": "Coastal cliff stone wall, turquoise sea to horizon, golden stone, afternoon light. Model sitting on wall one leg pulled up, looking at sea, contemplative",
        "garment": "Duvetica hooded zip-up in sage green with matching shorts, crochet knit vest layered, leather sandals",
    },
]

PROMPT_TEMPLATE = """Generate a high-end fashion editorial photograph that looks EXACTLY like a real luxury resort campaign shot on medium format film.

MOOD REFERENCE (Image 1) — MOST IMPORTANT:
Copy the EXACT feeling, lighting quality, color grading, warm film tones, and atmosphere.

PRODUCT REFERENCE (Image 2) — garment detail only:
Copy hood shape, zipper details, fabric texture. IGNORE the studio background.

SCENE: {scene}

GARMENT: {garment}

STYLE:
- Color: Kodak Portra 400 warmth, slightly desaturated, soft contrast
- Light: Natural golden hour, soft shadows, skin glowing with warmth
- Composition: Editorial but candid, shallow depth of field
- Skin: Sun-kissed, natural, minimal makeup
- Hair: Natural, wind-tousled
- Expression: Dreamy or serene — NEVER smiling with teeth, relaxed closed mouth
- Logo: minimal or none visible, tone-on-tone if any
- Overall mood: Quiet Luxury — like the feeling of reading a book on a yacht at sunset

NO studio. NO catalog pose. NO artificial light. NO bright saturated colors."""


def load_img(path: Path, max_size: int = 1200) -> Image.Image:
    img = Image.open(path).convert("RGB")
    if img.width > max_size or img.height > max_size:
        img.thumbnail((max_size, max_size), Image.LANCZOS)
    return img


def generate_gemini(scenario: dict) -> dict:
    sid = scenario["id"]
    prompt = PROMPT_TEMPLATE.format(
        scene=scenario["scene"], garment=scenario["garment"]
    )

    mood_img = load_img(MOOD_DIR / MOOD_REFS[scenario["mood_ref"]])
    product_img = load_img(BRAND_DIR / scenario["product_ref"])

    parts = [
        types.Part(text=prompt),
        types.Part(text="[MOOD REFERENCE - copy this feeling and atmosphere]:"),
        _pil_to_part(mood_img),
        types.Part(text="[PRODUCT REFERENCE - garment detail only]:"),
        _pil_to_part(product_img),
    ]

    client = genai.Client(api_key=_get_next_api_key())

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=IMAGE_MODEL,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(
                    temperature=0.9,
                    response_modalities=["IMAGE", "TEXT"],
                    image_config=types.ImageConfig(),
                ),
            )
            for part in response.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    result_img = Image.open(io.BytesIO(part.inline_data.data)).convert(
                        "RGB"
                    )
                    out_path = OUTPUT_DIR / f"{sid}_gemini.png"
                    result_img.save(out_path, "PNG")
                    print(
                        f"  [GEMINI OK] {sid}: {result_img.size[0]}x{result_img.size[1]}"
                    )
                    return {
                        "id": sid,
                        "model": "gemini",
                        "status": "ok",
                        "size": result_img.size,
                    }

            if attempt < 2:
                time.sleep(5)
                continue
            return {"id": sid, "model": "gemini", "status": "no_image"}
        except Exception as e:
            if attempt < 2:
                time.sleep((attempt + 1) * 5)
                continue
            print(f"  [GEMINI FAIL] {sid}: {e}")
            return {"id": sid, "model": "gemini", "status": "error", "error": str(e)}


def generate_gpt(scenario: dict) -> dict:
    sid = scenario["id"]
    prompt = PROMPT_TEMPLATE.format(
        scene=scenario["scene"], garment=scenario["garment"]
    )

    mood_path = MOOD_DIR / MOOD_REFS[scenario["mood_ref"]]
    product_path = BRAND_DIR / scenario["product_ref"]

    mood_img = load_img(mood_path)
    product_img = load_img(product_path, max_size=1024)

    temp_files = pil_list_to_temp_files([mood_img, product_img])

    try:
        gpt_prompt = (
            "[Image 1 is the MOOD REFERENCE - copy this exact feeling, lighting, atmosphere. "
            "Image 2 is the PRODUCT REFERENCE - copy garment details only, ignore background.]\n\n"
            + prompt
        )

        result_img = generate_gpt_image(
            prompt=gpt_prompt,
            reference_images=[Path(t) for t in temp_files],
            aspect_ratio="3:4",
            resolution="2K",
            quality="high",
        )

        if result_img:
            out_path = OUTPUT_DIR / f"{sid}_gpt.png"
            result_img.save(out_path, "PNG")
            print(f"  [GPT OK] {sid}: {result_img.size[0]}x{result_img.size[1]}")
            return {"id": sid, "model": "gpt", "status": "ok", "size": result_img.size}
        else:
            print(f"  [GPT FAIL] {sid}: no image returned")
            return {"id": sid, "model": "gpt", "status": "no_image"}

    except Exception as e:
        print(f"  [GPT FAIL] {sid}: {e}")
        return {"id": sid, "model": "gpt", "status": "error", "error": str(e)}
    finally:
        cleanup_temp_files(temp_files)


def main():
    print(f"{'=' * 60}")
    print(f"DUVETICA Lifestyle v2 (Gemini + GPT)")
    print(f"Scenarios: {len(SCENARIOS)} x 2 models = {len(SCENARIOS)*2} images")
    print(f"{'=' * 60}")

    # Save refs and prompts
    for s in SCENARIOS:
        mood_img = load_img(MOOD_DIR / MOOD_REFS[s["mood_ref"]])
        prod_img = load_img(BRAND_DIR / s["product_ref"])
        mood_img.save(OUTPUT_DIR / f"{s['id']}_ref_mood.jpg", "JPEG", quality=90)
        prod_img.save(OUTPUT_DIR / f"{s['id']}_ref_product.jpg", "JPEG", quality=90)
        with open(OUTPUT_DIR / f"{s['id']}_prompt.txt", "w", encoding="utf-8") as f:
            f.write(f"Scene: {s['scene']}\nGarment: {s['garment']}\n\n")
            f.write(PROMPT_TEMPLATE.format(scene=s["scene"], garment=s["garment"]))

    results = []
    tasks = []
    for s in SCENARIOS:
        tasks.append(("gemini", s))
        tasks.append(("gpt", s))

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {}
        for model, s in tasks:
            if model == "gemini":
                futures[executor.submit(generate_gemini, s)] = (model, s["id"])
            else:
                futures[executor.submit(generate_gpt, s)] = (model, s["id"])

        for future in as_completed(futures):
            result = future.result()
            results.append(result)

    gemini_ok = sum(
        1 for r in results if r["model"] == "gemini" and r["status"] == "ok"
    )
    gpt_ok = sum(1 for r in results if r["model"] == "gpt" and r["status"] == "ok")

    with open(OUTPUT_DIR / "config.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": TIMESTAMP,
                "gemini": gemini_ok,
                "gpt": gpt_ok,
                "results": results,
            },
            f,
            indent=2,
        )

    print(f"\n{'=' * 60}")
    print(
        f"DONE - Gemini: {gemini_ok}/{len(SCENARIOS)}, GPT: {gpt_ok}/{len(SCENARIOS)}"
    )
    print(f"Output: {OUTPUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
