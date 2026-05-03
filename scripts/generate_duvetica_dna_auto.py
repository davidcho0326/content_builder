# WORKFLOW_BYPASS_OK: strategy-cut-builder DNA auto pipeline (2026-04-30)
"""Final pipeline: VLM analyze ref → DNA auto-blend → prompt-only generation

DNA JSON drives EVERYTHING — swap the JSON to switch brands.

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/generate_duvetica_dna_auto.py
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
from core.api import _get_next_api_key, _pil_to_part
from core.model_utils import generate_gpt_image

from scripts.strategy_cut_builder.dna_to_prompt import (
    load_dna,
    build_full_editorial_prompt,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MOOD_DIR = Path(r"C:\Users\AC1060\Downloads") / "듀베티카"
OUTPUT_BASE = PROJECT_ROOT / "Fnf_studio_outputs" / "strategy-cut-builder" / "duvetica"

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = OUTPUT_BASE / f"{TIMESTAMP}_dna_auto"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BRAND = "duvetica"

SCENES = [
    {
        "id": "WJ_01",
        "category": "woven_jacket",
        "ref": "297990159c1d966fd4cb5f3afc95fafe.jpg",
        "lens": "85mm f/1.8",
        "aperture": "f/2.8 — background lake and mountains softly blurred",
        "film": "Kodak Portra 400 — warm golden skin, muted greens",
        "framing": "Medium shot from waist up, model in center-right third",
        "lighting": "Overcast afternoon, soft diffused light from above, subtle warm fill from wooden boat surfaces",
    },
    {
        "id": "WJ_02",
        "category": "woven_jacket",
        "ref": "c011a26256e4ba4bdfd753a22c5cf9e2.jpg",
        "lens": "50mm f/1.4",
        "aperture": "f/4 — garden background in gentle blur",
        "film": "Kodak Portra 160 — refined skin, warm stone tones",
        "framing": "Full body shot, model sitting on stone with legs visible, right third of frame",
        "lighting": "Late afternoon warm sun from behind-left, rim lighting on hair, soft shadows from cypress trees",
    },
    {
        "id": "WJ_03",
        "category": "woven_jacket",
        "ref": "92e4ebfa6d48da1ee38fc241290bf152.jpg",
        "lens": "85mm f/1.8",
        "aperture": "f/2.8 — sea horizon softly blurred",
        "film": "Kodak Portra 400 — golden backlight warmth, soft contrast",
        "framing": "Medium full shot, model sitting in deck chair, slightly low angle",
        "lighting": "Golden hour backlight from behind, warm rim light on hair and shoulder edges, fill light from teak deck reflection",
    },
    {
        "id": "WJ_04",
        "category": "woven_jacket",
        "ref": "65fb8912a289a6a2c5f4b033b7845569.jpg",
        "lens": "70mm f/2",
        "aperture": "f/2.8 — white walls and sea blurred",
        "film": "Fuji Pro 400H — slightly cooler whites, creamy skin tones",
        "framing": "Medium close-up, model reclining, head and torso filling frame",
        "lighting": "Soft afternoon light through villa arches, indirect warm light bouncing from white plaster walls",
    },
    {
        "id": "WJ_05",
        "category": "woven_jacket",
        "ref": "07b8e43dd59e481bab62ccaa63955581.jpg",
        "lens": "35mm f/2",
        "aperture": "f/5.6 — ancient ruins sharp in background",
        "film": "Kodak Ektar 100 — vivid blue sky, warm stone, fine grain",
        "framing": "Full body shot, model leaning on ancient stone, low angle looking up slightly",
        "lighting": "Late afternoon golden directional sun from the right, strong warm light on stone, defined shadows",
    },
    {
        "id": "WJ_06",
        "category": "woven_jacket",
        "ref": "f5d2823e75ca83f7fc6c4b5fb9768aa8.jpg",
        "lens": "50mm f/1.4",
        "aperture": "f/2.8 — street and buildings softly blurred",
        "film": "Kodak Portra 800 — slightly grainier, warm street tones",
        "framing": "Medium full shot, model standing near a vintage Vespa, wind catching her outfit",
        "lighting": "Strong midday Mediterranean sun from above-left, sharp shadows on pavement, bright reflected fill from cream buildings",
    },
    {
        "id": "SETUP_01",
        "category": "setup",
        "ref": "14d2a242bfc922645ca8b4c293afc973.jpg",
        "lens": "85mm f/1.8",
        "aperture": "f/2.8 — pool water blurred into abstract turquoise",
        "film": "Kodak Portra 400 — warm skin against cool water tones",
        "framing": "Medium shot from behind-side, model looking over shoulder toward camera, pool visible",
        "lighting": "Bright afternoon sun, turquoise water caustics reflecting on skin, warm direct light",
    },
    {
        "id": "SETUP_02",
        "category": "setup",
        "ref": "f70e6884e65b4146ade5e7235ae489f3.jpg",
        "lens": "70mm f/2",
        "aperture": "f/4 — sea and rocks in gentle blur",
        "film": "Kodak Portra 160 — refined coastal tones, subtle grain",
        "framing": "Full body, model sitting on coastal stone wall with one knee drawn up, sea behind",
        "lighting": "Afternoon coastal light, slightly hazy, warm light on stone, cool blue reflected from sea",
    },
    {
        "id": "SETUP_03",
        "category": "setup",
        "ref": "f8481cefca86b97fe479b6b59cca79ae.jpg",
        "lens": "50mm f/1.4",
        "aperture": "f/2.8 — pool edge and tiles softly blurred",
        "film": "Kodak Portra 400 — warm golden skin, turquoise accent",
        "framing": "Close-up from above (slightly high angle), model lying at pool edge, face and upper body",
        "lighting": "Direct overhead sun, strong highlights on skin and fabric, turquoise water reflection creating caustic patterns",
    },
]

MOMENTS = {
    "WJ_01": "she just turned her head from gazing at the lake mountains, one hand still resting near her chin where she was thinking, sunglasses slightly tilted on her face",
    "WJ_02": "she paused mid-conversation to watch a butterfly cross the garden, her chin still resting on her palm, the trace of a thought visible in her half-focused eyes",
    "WJ_03": "she lowered her book for a moment to feel the sea breeze on her face, eyes half-closed, the last page still held between her fingers",
    "WJ_04": "she exhaled slowly into the warm villa air, eyes drifting closed, the weight of nothing pressing on her — just the sea, the light, and the afternoon",
    "WJ_05": "she was adjusting her stance against the ancient warm stone when the photographer caught her unaware, her weight shifting to one hip, one hand trailing along the rough surface",
    "WJ_06": "the wind caught her jacket and hair at the same moment she turned to look down the empty street, one hand reaching up instinctively to hold her collar",
    "SETUP_01": "she glanced back over her shoulder at the sound of splashing water, her body still turned toward the pool, curls falling across one eye",
    "SETUP_02": "she was watching a distant sailboat when the shutter clicked, one leg pulled up on the warm stone, her arms loosely wrapped around her knee",
    "SETUP_03": "she closed her eyes against the poolside sun, one hand drifting up near her temple, the water light making moving patterns on her face and clothes",
}


def analyze_ref(ref_path: Path) -> dict:
    """VLM analyze reference for camera/lighting details."""
    client = genai.Client(api_key=_get_next_api_key())
    img = Image.open(ref_path).convert("RGB")
    img.thumbnail((1024, 1024), Image.LANCZOS)

    prompt = """Analyze this fashion photograph. Extract:
{
  "color_grading": "describe the color grading in detail (warmth, saturation, contrast, film look)",
  "lighting_quality": "describe the light — direction, hardness, color, special qualities",
  "atmosphere": "one sentence describing the emotional atmosphere",
  "key_texture": "what textures are most prominent in the image"
}
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
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    dna = load_dna(BRAND)
    print(f"{'=' * 60}")
    print(f"{dna['brand']} DNA Auto Pipeline")
    print(f"Season: {dna['season']}")
    print(f"Scenes: {len(SCENES)} x 2 models = {len(SCENES)*2} images")
    print(f"{'=' * 60}")

    # Phase 1: Quick VLM analysis of refs for color grading enrichment
    print("\n[PHASE 1] VLM ref analysis for color grading...")
    ref_analyses = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(analyze_ref, MOOD_DIR / s["ref"]): s["id"] for s in SCENES}
        for f in as_completed(futures):
            sid = futures[f]
            try:
                ref_analyses[sid] = f.result()
                print(f"  [{sid}] OK")
            except Exception as e:
                print(f"  [{sid}] FAIL: {e}")
                ref_analyses[sid] = {}

    # Phase 2: Build DNA-driven prompts
    print("\n[PHASE 2] Building DNA-auto prompts...")
    prompts = {}
    for scene in SCENES:
        sid = scene["id"]
        ref_extra = ref_analyses.get(sid, {})
        color_grading = ref_extra.get("color_grading", "warm Kodak Portra film tones")
        atmosphere = ref_extra.get("atmosphere", "quiet luxury")

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

        enriched = (
            base_prompt
            + f"\n\nCOLOR GRADING REFERENCE: {color_grading}.\nATMOSPHERE: {atmosphere}."
        )
        prompts[sid] = enriched

        with open(OUTPUT_DIR / f"{sid}_prompt.txt", "w", encoding="utf-8") as f:
            f.write(enriched)
        print(f"  [{sid}] {len(enriched)} chars")

    # Save references
    for scene in SCENES:
        ref = Image.open(MOOD_DIR / scene["ref"]).convert("RGB")
        ref.save(OUTPUT_DIR / f"{scene['id']}_00_reference.jpg", "JPEG", quality=95)

    # Phase 3: Generate
    print(f"\n[PHASE 3] Generating {len(prompts)*2} images...")
    results = []
    tasks = []
    for sid, prompt in prompts.items():
        tasks.append(("gemini", sid, prompt))
        tasks.append(("gpt", sid, prompt))

    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {}
        for model, sid, prompt in tasks:
            fn = generate_gemini if model == "gemini" else generate_gpt
            futures[ex.submit(fn, prompt, sid)] = (model, sid)
        for f in as_completed(futures):
            results.append(f.result())

    gem_ok = sum(1 for r in results if r["model"] == "gemini" and r["status"] == "ok")
    gpt_ok = sum(1 for r in results if r["model"] == "gpt" and r["status"] == "ok")

    with open(OUTPUT_DIR / "config.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "brand": BRAND,
                "strategy": "DNA-auto (VLM enrich + DNA blend + prompt-only)",
                "gemini": gem_ok,
                "gpt": gpt_ok,
                "results": results,
            },
            f,
            indent=2,
        )

    print(f"\n{'=' * 60}")
    print(f"DONE — Gemini: {gem_ok}/{len(SCENES)}, GPT: {gpt_ok}/{len(SCENES)}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
