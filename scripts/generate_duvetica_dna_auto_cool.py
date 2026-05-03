# WORKFLOW_BYPASS_OK: strategy-cut-builder DNA auto pipeline — cool tone variant (2026-04-30)
"""Same as generate_duvetica_dna_auto.py but with neutral/cool color grading.

Changes from original:
- Film stocks → Fuji Pro 400H / Kodak Portra 160 (cooler, less golden)
- POST-PRODUCTION → "Clean, neutral, high-end editorial" instead of "Warm, timeless"
- Color grading override → strips warm/golden from VLM analysis, adds neutral directives

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/generate_duvetica_dna_auto_cool.py
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
    get_model_prompt,
    build_garment_prompt,
    get_setting_prompt,
    get_mood_prompt,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MOOD_DIR = Path(r"C:\Users\AC1060\Downloads") / "듀베티카"
OUTPUT_BASE = PROJECT_ROOT / "Fnf_studio_outputs" / "strategy-cut-builder" / "duvetica"

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = OUTPUT_BASE / f"{TIMESTAMP}_dna_auto_cool"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BRAND = "duvetica"

COOL_EDITORIAL_TEMPLATE = """A high-end fashion editorial photograph for Vogue Italia / {brand} campaign, 3:4 portrait orientation.

THIS IS A LUXURY FASHION EDITORIAL. Art-directed by a top creative director, shot by a world-class fashion photographer.

THE MODEL: {model_desc}

THE MOMENT: {moment}

SHE IS WEARING: {garment_desc}

PHOTOGRAPHY:
- Camera: Hasselblad 500CM, {lens}, {aperture}
- Film: {film} — visible fine grain, organic tonal transitions
- {framing}. 3:4 portrait aspect ratio.
- {lighting_desc}

COMPOSITION: Editorial art direction — intentional use of negative space, strong leading lines, subject placed using rule of thirds. Published campaign quality.

SETTING: {setting_desc}

{mood_desc}

POST-PRODUCTION: Analog film grain visible throughout. Rich tonal depth in shadows. Creamy highlight rolloff. Professional fashion retouching — skin flawless but visible texture and pores. Clean, contemporary, high-end editorial. Neutral white balance — avoid yellow or amber cast.

NATURAL DETAILS: wind-displaced strands of hair, fabric caught mid-movement, asymmetric pose, natural skin texture visible.

COLOR DIRECTION: Neutral-to-cool color temperature. Skin tones should be natural and true-to-life without golden or amber warmth. Whites and highlights should read clean and crisp, not creamy or yellowed. Shadows lean slightly cool (blue-grey) rather than warm (brown-amber)."""

SCENES = [
    {
        "id": "WJ_01",
        "category": "woven_jacket",
        "ref": "297990159c1d966fd4cb5f3afc95fafe.jpg",
        "lens": "85mm f/1.8",
        "aperture": "f/2.8 — background lake and mountains softly blurred",
        "film": "Fuji Pro 400H — natural skin tones, clean greens, slightly cool highlights",
        "framing": "Medium shot from waist up, model in center-right third",
        "lighting": "Overcast afternoon, soft diffused light from above, even natural fill",
    },
    {
        "id": "WJ_02",
        "category": "woven_jacket",
        "ref": "c011a26256e4ba4bdfd753a22c5cf9e2.jpg",
        "lens": "50mm f/1.4",
        "aperture": "f/4 — garden background in gentle blur",
        "film": "Kodak Portra 160 — refined skin, clean neutral stone tones",
        "framing": "Full body shot, model sitting on stone with legs visible, right third of frame",
        "lighting": "Late afternoon soft sun from behind-left, rim lighting on hair, gentle shadows from cypress trees",
    },
    {
        "id": "WJ_03",
        "category": "woven_jacket",
        "ref": "92e4ebfa6d48da1ee38fc241290bf152.jpg",
        "lens": "85mm f/1.8",
        "aperture": "f/2.8 — sea horizon softly blurred",
        "film": "Fuji Pro 400H — clean backlight, natural contrast, neutral skin",
        "framing": "Medium full shot, model sitting in deck chair, slightly low angle",
        "lighting": "Afternoon backlight from behind, soft rim light on hair and shoulder edges, fill light from teak deck reflection",
    },
    {
        "id": "WJ_04",
        "category": "woven_jacket",
        "ref": "65fb8912a289a6a2c5f4b033b7845569.jpg",
        "lens": "70mm f/2",
        "aperture": "f/2.8 — white walls and sea blurred",
        "film": "Fuji Pro 400H — cool clean whites, natural creamy skin tones",
        "framing": "Medium close-up, model reclining, head and torso filling frame",
        "lighting": "Soft afternoon light through villa arches, indirect clean light bouncing from white plaster walls",
    },
    {
        "id": "WJ_05",
        "category": "woven_jacket",
        "ref": "07b8e43dd59e481bab62ccaa63955581.jpg",
        "lens": "35mm f/2",
        "aperture": "f/5.6 — ancient ruins sharp in background",
        "film": "Kodak Ektar 100 — vivid blue sky, neutral stone tones, fine grain",
        "framing": "Full body shot, model leaning on ancient stone, low angle looking up slightly",
        "lighting": "Late afternoon directional sun from the right, clean light on stone, defined shadows",
    },
    {
        "id": "WJ_06",
        "category": "woven_jacket",
        "ref": "f5d2823e75ca83f7fc6c4b5fb9768aa8.jpg",
        "lens": "50mm f/1.4",
        "aperture": "f/2.8 — street and buildings softly blurred",
        "film": "Kodak Portra 160 — clean tones, neutral street palette, fine grain",
        "framing": "Medium full shot, model standing near a vintage Vespa, wind catching her outfit",
        "lighting": "Bright midday Mediterranean sun from above-left, sharp shadows on pavement, bright reflected fill from cream buildings",
    },
    {
        "id": "SETUP_01",
        "category": "setup",
        "ref": "14d2a242bfc922645ca8b4c293afc973.jpg",
        "lens": "85mm f/1.8",
        "aperture": "f/2.8 — pool water blurred into abstract turquoise",
        "film": "Fuji Pro 400H — natural skin against cool water tones, clean highlights",
        "framing": "Medium shot from behind-side, model looking over shoulder toward camera, pool visible",
        "lighting": "Bright afternoon sun, turquoise water caustics reflecting on skin, clean direct light",
    },
    {
        "id": "SETUP_02",
        "category": "setup",
        "ref": "f70e6884e65b4146ade5e7235ae489f3.jpg",
        "lens": "70mm f/2",
        "aperture": "f/4 — sea and rocks in gentle blur",
        "film": "Kodak Portra 160 — refined coastal tones, neutral palette, subtle grain",
        "framing": "Full body, model sitting on coastal stone wall with one knee drawn up, sea behind",
        "lighting": "Afternoon coastal light, slightly hazy, even light on stone, cool blue reflected from sea",
    },
    {
        "id": "SETUP_03",
        "category": "setup",
        "ref": "f8481cefca86b97fe479b6b59cca79ae.jpg",
        "lens": "50mm f/1.4",
        "aperture": "f/2.8 — pool edge and tiles softly blurred",
        "film": "Fuji Pro 400H — natural skin, turquoise accent, clean whites",
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


def neutralize_color_grading(cg: str) -> str:
    """Strip warm/golden bias from VLM color grading and add neutral direction."""
    replacements = {
        "warm": "neutral",
        "golden": "natural",
        "golden-hour": "soft afternoon",
        "amber": "neutral",
        "yellow": "clean",
        "nostalgic": "contemporary",
        "vintage": "classic",
    }
    result = cg
    for old, new in replacements.items():
        result = re.sub(rf"\b{old}\b", new, result, flags=re.IGNORECASE)
    if "neutral" not in result.lower() and "cool" not in result.lower():
        result += ", with neutral-to-cool white balance"
    return result


def build_cool_prompt(
    dna: dict,
    category: str,
    moment: str,
    lens: str,
    aperture: str,
    film: str,
    framing: str,
    lighting_desc: str,
) -> str:
    return COOL_EDITORIAL_TEMPLATE.format(
        brand=dna["brand"],
        model_desc=get_model_prompt(dna),
        moment=moment,
        garment_desc=build_garment_prompt(dna, category),
        lens=lens,
        aperture=aperture,
        film=film,
        framing=framing,
        lighting_desc=lighting_desc,
        setting_desc=get_setting_prompt(dna),
        mood_desc=get_mood_prompt(dna),
    )


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
    print(f"{dna['brand']} DNA Auto Pipeline (COOL TONE)")
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

    # Phase 2: Build DNA-driven prompts (cool-shifted)
    print("\n[PHASE 2] Building DNA-auto prompts (COOL TONE)...")
    prompts = {}
    for scene in SCENES:
        sid = scene["id"]
        ref_extra = ref_analyses.get(sid, {})
        raw_cg = ref_extra.get("color_grading", "neutral film tones")
        color_grading = neutralize_color_grading(raw_cg)
        atmosphere = ref_extra.get("atmosphere", "quiet luxury")

        base_prompt = build_cool_prompt(
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
            + f"\n\nVLM COLOR REFERENCE (neutralized): {color_grading}.\nATMOSPHERE: {atmosphere}."
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
    print(f"\n[PHASE 3] Generating {len(prompts)*2} images (COOL TONE)...")
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
                "strategy": "DNA-auto COOL TONE (VLM enrich + DNA blend + neutral color)",
                "tone": "neutral-to-cool (warm/golden stripped from all prompts)",
                "gemini": gem_ok,
                "gpt": gpt_ok,
                "results": results,
            },
            f,
            indent=2,
        )

    print(f"\n{'=' * 60}")
    print(f"DONE (COOL) -- Gemini: {gem_ok}/{len(SCENES)}, GPT: {gpt_ok}/{len(SCENES)}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
