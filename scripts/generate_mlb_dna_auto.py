# WORKFLOW_BYPASS_OK: strategy-cut-builder DNA auto pipeline (2026-04-30)
"""MLB DNA Auto Pipeline — same architecture as Duvetica, different DNA

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/generate_mlb_dna_auto.py
"""

import json
import re
import io
import sys
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
from core.api import _get_next_api_key, _pil_to_part
from core.model_utils import generate_gpt_image

from scripts.strategy_cut_builder.dna_to_prompt import (
    load_dna,
    build_full_editorial_prompt,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MOOD_DIR = Path(r"C:\Users\AC1060\Downloads") / "mlb추구미"
OUTPUT_BASE = PROJECT_ROOT / "Fnf_studio_outputs" / "strategy-cut-builder" / "mlb"

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = OUTPUT_BASE / f"{TIMESTAMP}_dna_auto"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BRAND = "mlb"

REF_FILES = sorted(
    [f.name for f in MOOD_DIR.iterdir() if f.suffix in (".png", ".jpg", ".jpeg")]
)

SCENES = [
    {
        "id": "TEE_01",
        "category": "tee",
        "ref_idx": 0,
        "lens": "50mm f/1.4",
        "aperture": "f/2 -- street background softly blurred",
        "film": "Kodak Portra 400 -- warm skin, urban tones",
        "framing": "Upper body shot, cap brim creating shadow on face, right third of frame",
        "lighting": "Late afternoon sun from the left, warm side-lighting, concrete wall bounce fill",
    },
    {
        "id": "TEE_02",
        "category": "tee",
        "ref_idx": 1,
        "lens": "35mm f/1.8",
        "aperture": "f/2.8 -- cafe signage slightly blurred behind",
        "film": "Kodak Gold 200 -- warm yellows, punchy contrast",
        "framing": "Medium shot, model standing outside cafe, phone-snap composition",
        "lighting": "Bright overcast midday, even soft light, cafe neon adding warm accent",
    },
    {
        "id": "TEE_03",
        "category": "tee",
        "ref_idx": 3,
        "lens": "85mm f/1.8",
        "aperture": "f/2 -- background abstract blur",
        "film": "Fuji Superia 400 -- slightly cool, strong contrast",
        "framing": "Close-up portrait, cap at slight angle, face filling frame, low angle",
        "lighting": "Indoor cafe window light from the right, moody shadows on one side of face",
    },
    {
        "id": "SET_01",
        "category": "set",
        "ref_idx": 2,
        "lens": "50mm f/1.4",
        "aperture": "f/2.8 -- shallow depth",
        "film": "Kodak Portra 800 -- grainy warm tones, urban feel",
        "framing": "Full body shot, model posing with attitude, centered composition",
        "lighting": "Warm afternoon light, hard shadows from nearby buildings",
    },
    {
        "id": "SET_02",
        "category": "set",
        "ref_idx": 5,
        "lens": "35mm f/2",
        "aperture": "f/4 -- parking lot environment visible",
        "film": "Kodak Portra 400 -- warm skin, muted concrete",
        "framing": "Full body shot, model near a car, casual stance, off-center",
        "lighting": "Overcast light with warm reflection from car body, soft even shadows",
    },
    {
        "id": "WB_01",
        "category": "windbreaker",
        "ref_idx": 6,
        "lens": "85mm f/1.8",
        "aperture": "f/2.8 -- blurred urban background",
        "film": "Kodak Portra 400 -- warm golden skin tones",
        "framing": "Medium full shot, model walking casually, 3/4 angle",
        "lighting": "Golden hour side-lighting, long warm shadows on pavement",
    },
    {
        "id": "WB_02",
        "category": "windbreaker",
        "ref_idx": 8,
        "lens": "50mm f/1.4",
        "aperture": "f/2 -- street details soft",
        "film": "Kodak Gold 200 -- punchy, warm, nostalgic",
        "framing": "Full body shot, model leaning against wall, cool stance",
        "lighting": "Bright midday sun, sharp shadows, warm concrete reflections",
    },
    {
        "id": "PANTS_01",
        "category": "pants",
        "ref_idx": 10,
        "lens": "50mm f/1.4",
        "aperture": "f/2.8 -- staircase blurred",
        "film": "Kodak Portra 400 -- warm tones, soft grain",
        "framing": "Full body, model sitting on concrete stairs, legs stretched showing pants",
        "lighting": "Afternoon sunlight from above-right, interesting shadow patterns from stairs",
    },
    {
        "id": "JACKET_01",
        "category": "jacket",
        "ref_idx": 14,
        "lens": "85mm f/1.8",
        "aperture": "f/2 -- night-time bokeh",
        "film": "Kodak Portra 800 -- grainy, warm under artificial light",
        "framing": "Medium shot, model under street light, varsity jacket prominent",
        "lighting": "Mixed warm streetlight and cool neon, urban night atmosphere",
    },
]

MOMENTS = {
    "TEE_01": "she just tilted her cap down with one hand while glancing at her phone in the other, caught mid-scroll outside a Korean street shop",
    "TEE_02": "she's walking out of a cafe holding an iced drink, pushing the door open with her hip, sunlight catching her cropped tee",
    "TEE_03": "she looked up from adjusting her cap, one hand still on the brim, direct cool stare at the camera through cafe window reflection",
    "SET_01": "she paused mid-stride to check her reflection in a shop window, one hand on her hip, the other holding a mini bag, attitude in every line of her body",
    "SET_02": "she's leaning against a car hood scrolling her phone, one leg crossed over the other, completely unbothered, her matching set catching the light",
    "WB_01": "the wind just caught her windbreaker as she turned the corner, one hand reaching up to hold her cap, her hair swinging behind her",
    "WB_02": "she's waiting for someone outside a convenience store, weight on one leg, arms crossed loosely over her windbreaker, looking down the street",
    "PANTS_01": "she just sat down on warm concrete stairs to rest, one hand behind her for support, legs stretched out showing her cargo pants, looking up at something above",
    "JACKET_01": "she stepped out of a late-night restaurant into the cool air, pulling her varsity jacket collar up, the neon sign behind casting colors on the fabric",
}


def analyze_ref(ref_path: Path) -> dict:
    client = genai.Client(api_key=_get_next_api_key())
    img = Image.open(ref_path).convert("RGB")
    img.thumbnail((1024, 1024), Image.LANCZOS)
    prompt = """Analyze this street fashion photograph. Extract:
{"color_grading": "describe color grading", "lighting_quality": "describe light", "atmosphere": "one sentence mood", "key_texture": "dominant textures"}
Respond ONLY with valid JSON."""
    response = client.models.generate_content(
        model=VISION_MODEL,
        contents=[
            types.Content(
                role="user", parts=[types.Part(text=prompt), _pil_to_part(img)]
            )
        ],
        config=types.GenerateContentConfig(
            temperature=0.1, response_modalities=["TEXT"]
        ),
    )
    text = response.text.strip().replace("```json", "").replace("```", "").strip()
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return json.loads(text)


def generate_gemini(prompt: str, sid: str) -> dict:
    client = genai.Client(api_key=_get_next_api_key())
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=IMAGE_MODEL,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
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


def generate_gpt(prompt: str, sid: str) -> dict:
    try:
        result = generate_gpt_image(
            prompt=prompt, aspect_ratio="3:4", resolution="2K", quality="high"
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
    sys.stdout.reconfigure(encoding="utf-8")
    dna = load_dna(BRAND)

    print(f"{'=' * 60}")
    print(f"MLB DNA Auto Pipeline")
    print(f"Scenes: {len(SCENES)} x 2 models = {len(SCENES)*2} images")
    print(f"Ref images: {len(REF_FILES)} from {MOOD_DIR}")
    print(f"{'=' * 60}")

    # Phase 1: VLM analyze refs
    print("\n[PHASE 1] VLM ref analysis...")
    ref_analyses = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        scene_refs = {
            s["id"]: REF_FILES[min(s["ref_idx"], len(REF_FILES) - 1)] for s in SCENES
        }
        futures = {
            ex.submit(analyze_ref, MOOD_DIR / ref): sid
            for sid, ref in scene_refs.items()
        }
        for f in as_completed(futures):
            sid = futures[f]
            try:
                ref_analyses[sid] = f.result()
                print(f"  [{sid}] OK")
            except Exception as e:
                print(f"  [{sid}] FAIL: {e}")
                ref_analyses[sid] = {}

    # Phase 2: Build prompts
    print("\n[PHASE 2] Building DNA-auto prompts...")
    prompts = {}
    for scene in SCENES:
        sid = scene["id"]
        ref_extra = ref_analyses.get(sid, {})

        base_prompt = build_full_editorial_prompt(
            dna,
            scene["category"],
            moment=MOMENTS[sid],
            lens=scene["lens"],
            aperture=scene["aperture"],
            film=scene["film"],
            framing=scene["framing"],
            lighting_desc=scene["lighting"],
        )

        color_grading = ref_extra.get(
            "color_grading", "warm urban tones, slightly overexposed highlights"
        )
        atmosphere = ref_extra.get("atmosphere", "cool street energy")

        enriched = (
            base_prompt
            + f"\n\nCOLOR GRADING REFERENCE: {color_grading}.\nATMOSPHERE: {atmosphere}."
        )
        enriched = enriched.replace("Vogue Italia", "W Korea / Dazed Korea")
        prompts[sid] = enriched

        with open(OUTPUT_DIR / f"{sid}_prompt.txt", "w", encoding="utf-8") as f:
            f.write(enriched)

    # Save refs
    for scene in SCENES:
        ref_file = REF_FILES[min(scene["ref_idx"], len(REF_FILES) - 1)]
        ref = Image.open(MOOD_DIR / ref_file).convert("RGB")
        ref.save(OUTPUT_DIR / f"{scene['id']}_00_reference.jpg", "JPEG", quality=95)

    # Phase 3: Generate
    print(f"\n[PHASE 3] Generating {len(prompts)*2} images...")
    results = []
    tasks = [(m, sid, p) for sid, p in prompts.items() for m in ("gemini", "gpt")]

    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {
            ex.submit(generate_gemini if m == "gemini" else generate_gpt, p, sid): (
                m,
                sid,
            )
            for m, sid, p in tasks
        }
        for f in as_completed(futures):
            results.append(f.result())

    gem_ok = sum(1 for r in results if r["model"] == "gemini" and r["status"] == "ok")
    gpt_ok = sum(1 for r in results if r["model"] == "gpt" and r["status"] == "ok")

    with open(OUTPUT_DIR / "config.json", "w", encoding="utf-8") as f:
        json.dump(
            {"brand": BRAND, "gemini": gem_ok, "gpt": gpt_ok, "results": results},
            f,
            indent=2,
        )

    print(f"\n{'=' * 60}")
    print(f"DONE - Gemini: {gem_ok}/{len(SCENES)}, GPT: {gpt_ok}/{len(SCENES)}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
