# WORKFLOW_BYPASS_OK: strategy-cut-builder custom prompt pipeline (2026-04-30)
"""Try ALL approaches to recreate Duvetica reference images with Duvetica products

Approach A: Outfit swap (core/outfit_swap pipeline)
Approach B: Gemini reference-heavy reproduction
Approach C: GPT Image 2 edit mode

3 reference images x 3 approaches = 9 images

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/generate_duvetica_all_approaches.py
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
from core.outfit_swap.analyzer import analyze_source_for_swap, analyze_outfit_items
from core.outfit_swap.prompt_builder import build_outfit_swap_prompt

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MOOD_DIR = Path("C:/Users/AC1060/Downloads/듀베티카")
BRAND_DIR = PROJECT_ROOT / "db" / "strategy-cut-builder" / "duvetica" / "official-site"
OUTPUT_BASE = PROJECT_ROOT / "Fnf_studio_outputs" / "strategy-cut-builder" / "duvetica"

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = OUTPUT_BASE / f"{TIMESTAMP}_all_approaches"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TESTS = [
    {
        "id": "BOAT",
        "ref_file": "297990159c1d966fd4cb5f3afc95fafe.jpg",
        "ref_desc": "Como lake boat, cream knit + wide pants, sunglasses, wine",
        "product_ref": "women/casalina_BGS/casalina_BGS_01.jpg",
        "product_desc": "Duvetica casalina hooded zip-up windbreaker, beige sand",
    },
    {
        "id": "GARDEN",
        "ref_file": "c011a26256e4ba4bdfd753a22c5cf9e2.jpg",
        "ref_desc": "Tuscany garden stone ledge, white linen set, sunglasses, tote bag",
        "product_ref": "women/osilo/osilo_05.jpg",
        "product_desc": "Duvetica osilo anorak windbreaker, dark brown",
    },
    {
        "id": "YACHT",
        "ref_file": "92e4ebfa6d48da1ee38fc241290bf152.jpg",
        "ref_desc": "Yacht deck golden hour, reading book, linen shirt + white pants, leather sandals",
        "product_ref": "women/casalina_BKS/casalina_BKS_05.jpg",
        "product_desc": "Duvetica casalina hooded windbreaker, black",
    },
]


def load_img(path: Path, max_size: int = 1200) -> Image.Image:
    img = Image.open(path).convert("RGB")
    if img.width > max_size or img.height > max_size:
        img.thumbnail((max_size, max_size), Image.LANCZOS)
    return img


def approach_a_outfit_swap(test: dict) -> dict:
    """A: Core outfit swap pipeline — preserves source pose/face/background exactly."""
    sid = f"{test['id']}_A_swap"
    ref_path = str(MOOD_DIR / test["ref_file"])
    product_path = str(BRAND_DIR / test["product_ref"])

    try:
        client = genai.Client(api_key=_get_next_api_key())
        source_analysis = analyze_source_for_swap(ref_path, client)
        outfit_analysis = analyze_outfit_items([product_path], client)
        prompt = build_outfit_swap_prompt(
            source_analysis, outfit_analyses=outfit_analysis
        )

        ref_img = load_img(Path(ref_path))
        product_img = load_img(Path(product_path))
        parts = [
            types.Part(text=prompt),
            types.Part(
                text="[SOURCE IMAGE - keep this person, pose, background, and mood EXACTLY]:"
            ),
            _pil_to_part(ref_img),
            types.Part(
                text="[OUTFIT IMAGE - dress the person in EXACTLY this outfit]:"
            ),
            _pil_to_part(product_img),
        ]

        response = client.models.generate_content(
            model=IMAGE_MODEL,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                temperature=0.7,
                response_modalities=["IMAGE", "TEXT"],
                image_config=types.ImageConfig(),
            ),
        )

        for part in response.candidates[0].content.parts:
            if hasattr(part, "inline_data") and part.inline_data:
                result_img = Image.open(io.BytesIO(part.inline_data.data)).convert(
                    "RGB"
                )
                out_path = OUTPUT_DIR / f"{sid}.png"
                result_img.save(out_path, "PNG")

                with open(OUTPUT_DIR / f"{sid}_prompt.txt", "w", encoding="utf-8") as f:
                    f.write(f"APPROACH A: Outfit Swap (core pipeline)\n")
                    f.write(f"Source: {test['ref_file']}\n")
                    f.write(f"Outfit: {test['product_ref']}\n\n")
                    f.write(prompt[:2000])

                print(
                    f"  [A-SWAP OK] {test['id']}: {result_img.size[0]}x{result_img.size[1]}"
                )
                return {"id": sid, "status": "ok", "size": result_img.size}

        return {"id": sid, "status": "no_image"}
    except Exception as e:
        print(f"  [A-SWAP FAIL] {test['id']}: {e}")
        return {"id": sid, "status": "error", "error": str(e)}


def approach_b_gemini_reproduce(test: dict) -> dict:
    """B: Gemini with reference as primary input — reproduce but change clothes."""
    sid = f"{test['id']}_B_gemini"
    ref_img = load_img(MOOD_DIR / test["ref_file"])
    product_img = load_img(Path(BRAND_DIR / test["product_ref"]))

    prompt = f"""Reproduce this photograph EXACTLY — same person, same pose, same background, same lighting, same camera angle, same color grading, same mood.

The ONLY change: replace the clothing with the garment shown in Image 2 ({test['product_desc']}).

Keep EVERYTHING else identical:
- Same face, hair, skin tone, expression
- Same background, architecture, landscape, props
- Same camera position, framing, depth of field
- Same lighting direction, warmth, shadows
- Same film-like color grading (warm Kodak Portra tones)
- Same accessories (sunglasses, bags, jewelry) if appropriate

The result should be indistinguishable from the original photo except for the clothing.
Do NOT change the background. Do NOT change the pose. Do NOT change the mood."""

    try:
        client = genai.Client(api_key=_get_next_api_key())
        parts = [
            types.Part(text=prompt),
            types.Part(
                text="[ORIGINAL PHOTO - reproduce this EXACTLY, only change clothes]:"
            ),
            _pil_to_part(ref_img),
            types.Part(text="[NEW CLOTHING - dress the model in this]:"),
            _pil_to_part(product_img),
        ]

        response = client.models.generate_content(
            model=IMAGE_MODEL,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                temperature=0.5,
                response_modalities=["IMAGE", "TEXT"],
                image_config=types.ImageConfig(),
            ),
        )

        for part in response.candidates[0].content.parts:
            if hasattr(part, "inline_data") and part.inline_data:
                result_img = Image.open(io.BytesIO(part.inline_data.data)).convert(
                    "RGB"
                )
                out_path = OUTPUT_DIR / f"{sid}.png"
                result_img.save(out_path, "PNG")
                print(
                    f"  [B-GEMINI OK] {test['id']}: {result_img.size[0]}x{result_img.size[1]}"
                )
                return {"id": sid, "status": "ok", "size": result_img.size}

        return {"id": sid, "status": "no_image"}
    except Exception as e:
        print(f"  [B-GEMINI FAIL] {test['id']}: {e}")
        return {"id": sid, "status": "error", "error": str(e)}


def approach_c_gpt_edit(test: dict) -> dict:
    """C: GPT Image 2 edit mode — edit reference image to change clothes only."""
    sid = f"{test['id']}_C_gpt"

    ref_img = load_img(MOOD_DIR / test["ref_file"], max_size=1024)
    product_img = load_img(Path(BRAND_DIR / test["product_ref"]), max_size=1024)

    temp_files = pil_list_to_temp_files([ref_img, product_img])

    prompt = (
        f"Image 1 is the original photograph. Image 2 shows a {test['product_desc']}. "
        f"Edit Image 1 to replace ONLY the clothing with the garment from Image 2. "
        f"Keep EVERYTHING else exactly the same: same person, same face, same pose, same expression, "
        f"same background, same lighting, same camera angle, same color grading, same props. "
        f"The garment should fit naturally on the person's body with correct draping and shadows. "
        f"The result should look like a real photograph, not AI-generated."
    )

    try:
        result_img = generate_gpt_image(
            prompt=prompt,
            reference_images=[Path(t) for t in temp_files],
            aspect_ratio="3:4",
            resolution="2K",
            quality="high",
        )

        if result_img:
            out_path = OUTPUT_DIR / f"{sid}.png"
            result_img.save(out_path, "PNG")
            print(
                f"  [C-GPT OK] {test['id']}: {result_img.size[0]}x{result_img.size[1]}"
            )
            return {"id": sid, "status": "ok", "size": result_img.size}
        else:
            print(f"  [C-GPT FAIL] {test['id']}: no image")
            return {"id": sid, "status": "no_image"}
    except Exception as e:
        print(f"  [C-GPT FAIL] {test['id']}: {e}")
        return {"id": sid, "status": "error", "error": str(e)}
    finally:
        cleanup_temp_files(temp_files)


def main():
    print(f"{'=' * 60}")
    print(f"DUVETICA All Approaches Test")
    print(f"References: {len(TESTS)}")
    print(f"Approaches: A(outfit swap) + B(gemini reproduce) + C(gpt edit)")
    print(f"Total: {len(TESTS) * 3} images")
    print(f"{'=' * 60}")

    for t in TESTS:
        ref_img = load_img(MOOD_DIR / t["ref_file"])
        prod_img = load_img(Path(BRAND_DIR / t["product_ref"]))
        ref_img.save(OUTPUT_DIR / f"{t['id']}_00_reference.jpg", "JPEG", quality=95)
        prod_img.save(OUTPUT_DIR / f"{t['id']}_00_product.jpg", "JPEG", quality=95)

    results = []
    tasks = []
    for t in TESTS:
        tasks.append(("A", t, approach_a_outfit_swap))
        tasks.append(("B", t, approach_b_gemini_reproduce))
        tasks.append(("C", t, approach_c_gpt_edit))

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(fn, t): (approach, t["id"]) for approach, t, fn in tasks
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)

    a_ok = sum(1 for r in results if "_A_" in r["id"] and r["status"] == "ok")
    b_ok = sum(1 for r in results if "_B_" in r["id"] and r["status"] == "ok")
    c_ok = sum(1 for r in results if "_C_" in r["id"] and r["status"] == "ok")

    with open(OUTPUT_DIR / "config.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": TIMESTAMP,
                "A_swap": a_ok,
                "B_gemini": b_ok,
                "C_gpt": c_ok,
                "results": results,
            },
            f,
            indent=2,
        )

    print(f"\n{'=' * 60}")
    print(f"DONE")
    print(f"  A (outfit swap): {a_ok}/{len(TESTS)}")
    print(f"  B (gemini reproduce): {b_ok}/{len(TESTS)}")
    print(f"  C (gpt edit): {c_ok}/{len(TESTS)}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
