# WORKFLOW_BYPASS_OK: strategy-cut-builder reference-guided generation (2026-04-30)
"""Reference-guided generation: feed reference image + DNA prompt to model.

Instead of prompt-only, the reference image is passed directly to the model
so it can match pose/composition, while the text prompt controls garment/brand/styling.

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/generate_duvetica_dna_ref_guided.py
"""

import json
import re
import io
import time
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv

load_dotenv(override=True)

from PIL import Image
from google import genai
from google.genai import types

from core.config import IMAGE_MODEL, VISION_MODEL
from core.api import _get_next_api_key, _pil_to_part, image_to_part
from core.model_utils import generate_gpt_image

from scripts.strategy_cut_builder.dna_to_prompt import (
    load_dna,
    get_model_prompt,
    build_garment_prompt,
    get_setting_prompt,
    get_mood_prompt,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MOOD_DIR = Path(r"C:\Users\AC1060\Downloads") / "듀베티카"
OUTPUT_BASE = PROJECT_ROOT / "Fnf_studio_outputs" / "strategy-cut-builder" / "duvetica"

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = OUTPUT_BASE / f"{TIMESTAMP}_dna_ref_guided"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BRAND = "duvetica"

REF_GUIDED_TEMPLATE = """You are given a REFERENCE photograph. Generate a NEW high-end fashion editorial image that closely matches the REFERENCE in:
- POSE and BODY POSITION (replicate the exact pose, limb positions, head angle)
- COMPOSITION and FRAMING (same camera angle, distance, crop, rule-of-thirds placement)
- LIGHTING DIRECTION and QUALITY (same light source direction and mood)

But CHANGE the following based on the brand brief below:

THE MODEL: {model_desc}

SHE IS WEARING: {garment_desc}

SETTING: {setting_desc}

{mood_desc}

PHOTOGRAPHY:
- Camera: Hasselblad 500CM, {lens}, {aperture}
- Film: {film} — visible fine grain, organic tonal transitions
- 3:4 portrait aspect ratio.

POST-PRODUCTION: Analog film grain visible throughout. Rich tonal depth in shadows. Creamy highlight rolloff. Professional fashion retouching — skin flawless but visible texture and pores. Clean, contemporary, high-end editorial. Neutral white balance.

NATURAL DETAILS: wind-displaced strands of hair, fabric caught mid-movement, natural skin texture visible.

COLOR DIRECTION: Neutral-to-cool color temperature. Skin tones natural and true-to-life. Whites and highlights clean and crisp. Shadows lean slightly cool (blue-grey).

CRITICAL: Match the reference photograph's POSE, COMPOSITION, and CAMERA ANGLE as closely as possible. The model should be in the same position and the framing should be nearly identical. Only the garment, styling, and minor setting details should differ."""

SCENES = [
    {
        "id": "WJ_01",
        "category": "woven_jacket",
        "ref": "297990159c1d966fd4cb5f3afc95fafe.jpg",
        "lens": "85mm f/1.8",
        "aperture": "f/2.8 — background softly blurred",
        "film": "Fuji Pro 400H — natural skin tones, clean highlights",
    },
    {
        "id": "WJ_02",
        "category": "woven_jacket",
        "ref": "c011a26256e4ba4bdfd753a22c5cf9e2.jpg",
        "lens": "50mm f/1.4",
        "aperture": "f/4 — background in gentle blur",
        "film": "Kodak Portra 160 — refined skin, neutral tones",
    },
    {
        "id": "WJ_03",
        "category": "woven_jacket",
        "ref": "92e4ebfa6d48da1ee38fc241290bf152.jpg",
        "lens": "85mm f/1.8",
        "aperture": "f/2.8 — sea horizon softly blurred",
        "film": "Fuji Pro 400H — clean contrast, neutral skin",
    },
    {
        "id": "WJ_04",
        "category": "woven_jacket",
        "ref": "65fb8912a289a6a2c5f4b033b7845569.jpg",
        "lens": "70mm f/2",
        "aperture": "f/2.8 — white walls and sea blurred",
        "film": "Fuji Pro 400H — cool clean whites, natural skin",
    },
    {
        "id": "WJ_05",
        "category": "woven_jacket",
        "ref": "07b8e43dd59e481bab62ccaa63955581.jpg",
        "lens": "35mm f/2",
        "aperture": "f/5.6 — ruins sharp in background",
        "film": "Kodak Ektar 100 — vivid blue sky, neutral stone, fine grain",
    },
    {
        "id": "WJ_06",
        "category": "woven_jacket",
        "ref": "f5d2823e75ca83f7fc6c4b5fb9768aa8.jpg",
        "lens": "50mm f/1.4",
        "aperture": "f/2.8 — street softly blurred",
        "film": "Kodak Portra 160 — clean tones, fine grain",
    },
    {
        "id": "SETUP_01",
        "category": "setup",
        "ref": "14d2a242bfc922645ca8b4c293afc973.jpg",
        "lens": "85mm f/1.8",
        "aperture": "f/2.8 — pool water blurred",
        "film": "Fuji Pro 400H — natural skin, cool water tones",
    },
    {
        "id": "SETUP_02",
        "category": "setup",
        "ref": "f70e6884e65b4146ade5e7235ae489f3.jpg",
        "lens": "70mm f/2",
        "aperture": "f/4 — sea in gentle blur",
        "film": "Kodak Portra 160 — refined coastal tones",
    },
    {
        "id": "SETUP_03",
        "category": "setup",
        "ref": "f8481cefca86b97fe479b6b59cca79ae.jpg",
        "lens": "50mm f/1.4",
        "aperture": "f/2.8 — pool edge softly blurred",
        "film": "Fuji Pro 400H — natural skin, turquoise accent",
    },
]


def build_ref_guided_prompt(dna: dict, scene: dict) -> str:
    return REF_GUIDED_TEMPLATE.format(
        model_desc=get_model_prompt(dna),
        garment_desc=build_garment_prompt(dna, scene["category"]),
        setting_desc=get_setting_prompt(dna),
        mood_desc=get_mood_prompt(dna),
        lens=scene["lens"],
        aperture=scene["aperture"],
        film=scene["film"],
    )


def generate_gemini_with_ref(prompt: str, ref_path: Path, sid: str) -> dict:
    client = genai.Client(api_key=_get_next_api_key())
    ref_img = Image.open(ref_path).convert("RGB")
    ref_img.thumbnail((1536, 1536), Image.LANCZOS)

    parts = [
        types.Part(
            text="[REFERENCE IMAGE — match this pose, composition, and framing]"
        ),
        _pil_to_part(ref_img),
        types.Part(text=prompt),
    ]

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=IMAGE_MODEL,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(
                    temperature=1.0,
                    response_modalities=["IMAGE", "TEXT"],
                    image_config=types.ImageConfig(aspect_ratio="3:4"),
                ),
            )
            for part in response.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    result = Image.open(io.BytesIO(part.inline_data.data)).convert(
                        "RGB"
                    )
                    result.save(OUTPUT_DIR / f"{sid}_gemini.png", "PNG")
                    print(f"  [GEMINI OK] {sid}: {result.size[0]}x{result.size[1]}")
                    return {"id": sid, "model": "gemini", "status": "ok"}
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


def generate_gpt_with_ref(prompt: str, ref_path: Path, sid: str) -> dict:
    try:
        result = generate_gpt_image(
            prompt=prompt,
            reference_images=[ref_path],
            aspect_ratio="3:4",
            resolution="2K",
            quality="high",
        )
        if result:
            result.save(OUTPUT_DIR / f"{sid}_gpt.png", "PNG")
            print(f"  [GPT OK] {sid}: {result.size[0]}x{result.size[1]}")
            return {"id": sid, "model": "gpt", "status": "ok"}
        return {"id": sid, "model": "gpt", "status": "no_image"}
    except Exception as e:
        print(f"  [GPT FAIL] {sid}: {e}")
        return {"id": sid, "model": "gpt", "status": "error", "error": str(e)}


def main():
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    dna = load_dna(BRAND)
    print(f"{'=' * 60}")
    print(f"{dna['brand']} DNA Reference-Guided Pipeline")
    print(f"Season: {dna['season']}")
    print(f"Scenes: {len(SCENES)} x 2 models = {len(SCENES)*2} images")
    print(f"Strategy: ref image + DNA prompt (pose/composition guided)")
    print(f"{'=' * 60}")

    # Build prompts
    print("\n[PHASE 1] Building ref-guided prompts...")
    prompts = {}
    for scene in SCENES:
        sid = scene["id"]
        prompt = build_ref_guided_prompt(dna, scene)
        prompts[sid] = prompt
        with open(OUTPUT_DIR / f"{sid}_prompt.txt", "w", encoding="utf-8") as f:
            f.write(prompt)
        print(f"  [{sid}] {len(prompt)} chars")

    # Save references
    for scene in SCENES:
        ref = Image.open(MOOD_DIR / scene["ref"]).convert("RGB")
        ref.save(OUTPUT_DIR / f"{scene['id']}_00_reference.jpg", "JPEG", quality=95)

    # Generate with ref image
    print(f"\n[PHASE 2] Generating {len(prompts)*2} images (ref-guided)...")
    results = []
    tasks = []
    for scene in SCENES:
        sid = scene["id"]
        ref_path = MOOD_DIR / scene["ref"]
        tasks.append(("gemini", sid, prompts[sid], ref_path))
        tasks.append(("gpt", sid, prompts[sid], ref_path))

    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {}
        for model, sid, prompt, ref_path in tasks:
            fn = (
                generate_gemini_with_ref if model == "gemini" else generate_gpt_with_ref
            )
            futures[ex.submit(fn, prompt, ref_path, sid)] = (model, sid)
        for f in as_completed(futures):
            results.append(f.result())

    gem_ok = sum(1 for r in results if r["model"] == "gemini" and r["status"] == "ok")
    gpt_ok = sum(1 for r in results if r["model"] == "gpt" and r["status"] == "ok")

    with open(OUTPUT_DIR / "config.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "brand": BRAND,
                "strategy": "DNA ref-guided (reference image + DNA prompt)",
                "approach": "reference image fed directly to model for pose/composition matching",
                "tone": "neutral-to-cool",
                "gemini": gem_ok,
                "gpt": gpt_ok,
                "results": results,
            },
            f,
            indent=2,
        )

    print(f"\n{'=' * 60}")
    print(
        f"DONE (REF-GUIDED) -- Gemini: {gem_ok}/{len(SCENES)}, GPT: {gpt_ok}/{len(SCENES)}"
    )
    print(f"Output: {OUTPUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
