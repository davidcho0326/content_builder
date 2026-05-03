# WORKFLOW_BYPASS_OK: strategy-cut-builder prompt-only pipeline (2026-04-30)
"""Generate Duvetica lifestyle cuts with PROMPT ONLY — no reference images

Strategy:
1. VLM analyzes reference images in extreme detail (cinematographer's shot sheet)
2. Converts analysis to "captured moment" prompt (anti-AI technique)
3. Generates with text prompt only — no image input

Key anti-AI techniques:
- Describe a MOMENT being captured, not a posed shot
- Specify film camera + lens + film stock
- Use candid action verbs ("reaching for", "just looked up", "adjusting her sunglasses")
- Add imperfections (wind-blown hair, fabric caught mid-movement)

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/generate_duvetica_prompt_only.py
"""

import json
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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MOOD_DIR = Path(r"C:\Users\AC1060\Downloads") / "듀베티카"
OUTPUT_BASE = PROJECT_ROOT / "Fnf_studio_outputs" / "strategy-cut-builder" / "duvetica"

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = OUTPUT_BASE / f"{TIMESTAMP}_prompt_only"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ANALYSIS_PROMPT = """You are an elite fashion photography director analyzing a reference image for recreation.
Extract EVERY visual detail as a cinematographer's shot sheet. Be obsessively precise.

Return JSON with these fields:

{
  "moment": "describe the EXACT moment captured — what is the person DOING right now? Not posing, but the action/state (e.g., 'she just turned to look over her shoulder at someone calling her name', 'she's mid-exhale, eyes half-closed, savoring the last warmth of sunset on her face')",

  "camera": {
    "estimated_lens": "focal length feel (e.g., '85mm portrait lens', '50mm standard', '35mm wide')",
    "estimated_film": "what film stock this looks like (e.g., 'Kodak Portra 400 — warm skin, soft greens', 'Fuji Pro 400H — cooler, more muted')",
    "aperture_feel": "depth of field (e.g., 'f/2.8 — background softly blurred', 'f/5.6 — everything sharp')",
    "angle": "camera position relative to subject",
    "framing": "what's in frame, what's cropped out"
  },

  "lighting": {
    "source": "where is the light coming from (e.g., 'late afternoon sun from the right, about 30 degrees above horizon')",
    "quality": "hard/soft, direct/diffused",
    "color_temperature": "warm/cool, estimated kelvin feel",
    "shadows": "describe shadow character (e.g., 'soft shadows under chin and jawline, warm fill light from stone wall reflection')",
    "highlights": "where does light catch (e.g., 'rim light on hair and shoulder, specular highlights on sunglasses')"
  },

  "color_grading": {
    "overall_tone": "warm/cool/neutral, desaturated/vivid",
    "skin_tone": "how skin looks (e.g., 'golden-warm, slightly tanned, natural')",
    "shadow_color": "color of shadows (e.g., 'slightly blue-green in shadows')",
    "highlight_color": "color of highlights (e.g., 'warm cream highlights')",
    "saturation": "low/medium/high, which colors are more/less saturated"
  },

  "subject": {
    "body_position": "detailed body description — don't just say 'sitting', describe weight distribution, lean angle, limb positions",
    "hands": "what are the hands doing specifically",
    "face": "expression in detail — eye openness, mouth, tension/relaxation",
    "hair": "style, movement, how light catches it",
    "skin": "visible skin quality, makeup level, texture"
  },

  "clothing": {
    "items": "list each visible garment with precise color, fabric texture, fit",
    "how_worn": "how the clothes sit on the body — tucked, open, draped, caught by wind",
    "fabric_behavior": "how fabric responds to body/movement — draping, wrinkling, tension points",
    "accessories": "every accessory with detail"
  },

  "background": {
    "setting": "precise location description",
    "depth_layers": "foreground / midground / background elements",
    "textures": "dominant textures visible (stone, water, wood, fabric)",
    "colors": "background color palette",
    "atmosphere": "haze, clarity, dust, humidity feel"
  },

  "imperfections": "natural imperfections that make this feel real (flyaway hairs, fabric wrinkle, uneven tan, asymmetric pose, slightly off-center composition)"
}

Be OBSESSIVELY detailed. Every detail matters for recreation."""


SCENES = [
    {
        "id": "BOAT",
        "ref": "297990159c1d966fd4cb5f3afc95fafe.jpg",
        "duvetica_garment": "a Duvetica hooded zip-up windbreaker in warm cream beige, lightweight technical nylon with a soft semi-matte sheen that catches light subtly, tone-on-tone zipper, small embossed logo on chest, paired with matching cream wide-leg trousers in the same fabric family",
    },
    {
        "id": "GARDEN",
        "ref": "c011a26256e4ba4bdfd753a22c5cf9e2.jpg",
        "duvetica_garment": "a Duvetica hooded windbreaker in ivory white, relaxed semi-oversized fit, lightweight technical nylon, hood down, sleeves slightly pushed up revealing slim wrists, open front showing a simple ribbed tank underneath, paired with cream linen wide-leg trousers and black leather mule sandals",
    },
    {
        "id": "YACHT",
        "ref": "92e4ebfa6d48da1ee38fc241290bf152.jpg",
        "duvetica_garment": "a Duvetica hooded windbreaker in oatmeal beige, worn as a light casual layer with sleeves rolled once, over a plain white crew-neck t-shirt, paired with white linen drawstring trousers and tan leather flat sandals",
    },
    {
        "id": "VILLA",
        "ref": "65fb8912a289a6a2c5f4b033b7845569.jpg",
        "duvetica_garment": "a Duvetica cropped hooded zip-up jacket in pale cream ivory, lightweight with fluid drape, worn loosely open revealing a simple cream silk camisole underneath, paired with a flowing cream midi skirt, gold statement earrings",
    },
    {
        "id": "POOL",
        "ref": "f8481cefca86b97fe479b6b59cca79ae.jpg",
        "duvetica_garment": "a Duvetica half-zip hooded pullover in soft sky blue, lightweight breathable technical fabric, worn casually over a swimsuit, sleeves pushed to elbows, paired with matching sky blue drawstring shorts that hit mid-thigh",
    },
    {
        "id": "STONE",
        "ref": "f70e6884e65b4146ade5e7235ae489f3.jpg",
        "duvetica_garment": "a Duvetica hooded zip-up windbreaker in sage green, relaxed fit, over a cream striped crochet knit vest and simple white tee, paired with sage green matching shorts, tan leather flat sandals",
    },
]


def analyze_reference(ref_path: Path) -> dict:
    client = genai.Client(api_key=_get_next_api_key())
    img = Image.open(ref_path).convert("RGB")
    img.thumbnail((1200, 1200), Image.LANCZOS)

    parts = [types.Part(text=ANALYSIS_PROMPT), _pil_to_part(img)]
    response = client.models.generate_content(
        model=VISION_MODEL,
        contents=[types.Content(role="user", parts=parts)],
        config=types.GenerateContentConfig(
            temperature=0.1, response_modalities=["TEXT"]
        ),
    )
    text = response.text.strip().replace("```json", "").replace("```", "").strip()
    import re

    text = re.sub(r",\s*([}\]])", r"\1", text)
    return json.loads(text)


def build_prompt_from_analysis(analysis: dict, duvetica_garment: str) -> str:
    m = analysis
    cam = m["camera"]
    light = m["lighting"]
    color = m["color_grading"]
    subj = m["subject"]
    bg = m["background"]

    prompt = f"""A high-end fashion editorial photograph for Vogue Italia / Massimo Dutti campaign, 3:4 portrait orientation.

THIS IS A LUXURY FASHION EDITORIAL — not a casual snapshot. The image must look like it was art-directed by a top creative director and shot by a world-class fashion photographer.

THE MODEL: A professional high-fashion model in her mid-20s. Sharp angular jawline, high cheekbones, long elegant neck, defined collarbones. Slim editorial proportions. Sun-kissed skin with professional but natural-looking makeup. Hair styled but moved by real wind. She has the effortless confidence of someone who belongs in this world.

THE MOMENT: {m['moment']}

SHE IS WEARING: {duvetica_garment}. The fabric drapes with weight and movement — you can see the quality of the material. Subtle sheen catches light on the surface. Real wrinkles at natural bend points. The garment looks expensive and tactile.

PHOTOGRAPHY:
- Camera: Hasselblad 500CM, {cam['estimated_lens']}, {cam['aperture_feel']}
- Film: {cam['estimated_film']} — visible fine grain, organic tonal transitions
- {cam['framing']}. 3:4 portrait aspect ratio.
- {light['source']}. {light['quality']}. {light['color_temperature']}.
- {light['shadows']}. {light['highlights']}.
- Color grading: {color['overall_tone']}. {color['skin_tone']}. {color['shadow_color']}. {color['highlight_color']}.

COMPOSITION: Editorial art direction — intentional use of negative space, strong leading lines, subject placed using rule of thirds. The image has the considered composition of a published campaign, not a test shot.

SETTING: {bg['setting']}. {bg['depth_layers']}. Textures: {bg['textures']}. Colors: {bg['colors']}. {bg['atmosphere']}.

BODY LANGUAGE: {subj['body_position']}. Hands: {subj['hands']}. Face: {subj['face']}. Hair: {subj['hair']}.

POST-PRODUCTION: Analog film grain visible throughout. Rich tonal depth in shadows. Creamy highlight rolloff. Slight warm color cast. Professional fashion retouching — skin is flawless but has visible texture and pores. The overall look is warm, timeless, and unmistakably high-end editorial.

NATURAL DETAILS: {m.get('imperfections', 'wind-displaced strands of hair, fabric caught mid-movement, one shoulder slightly higher than the other')}."""

    return prompt


def generate_gemini_prompt_only(prompt: str, sid: str) -> dict:
    client = genai.Client(api_key=_get_next_api_key())
    parts = [types.Part(text=prompt)]

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


def generate_gpt_prompt_only(prompt: str, sid: str) -> dict:
    try:
        result = generate_gpt_image(
            prompt=prompt,
            reference_images=None,
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
    print(f"{'=' * 60}")
    print(f"DUVETICA Prompt-Only Generation")
    print(f"Strategy: VLM analyze ref -> director's brief -> generate")
    print(f"Scenes: {len(SCENES)} x 2 models = {len(SCENES)*2} images")
    print(f"{'=' * 60}")

    all_prompts = {}
    results = []

    # Phase 1: Analyze all references
    print("\n[PHASE 1] VLM Analysis...")
    analyses = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {
            ex.submit(analyze_reference, MOOD_DIR / s["ref"]): s["id"] for s in SCENES
        }
        for f in as_completed(futures):
            sid = futures[f]
            try:
                analyses[sid] = f.result()
                print(f"  [{sid}] Analysis OK")
            except Exception as e:
                print(f"  [{sid}] Analysis FAIL: {e}")
                analyses[sid] = None

    # Phase 2: Build prompts
    print("\n[PHASE 2] Building director's briefs...")
    for scene in SCENES:
        sid = scene["id"]
        if analyses.get(sid):
            prompt = build_prompt_from_analysis(
                analyses[sid], scene["duvetica_garment"]
            )
            all_prompts[sid] = prompt
            with open(OUTPUT_DIR / f"{sid}_prompt.txt", "w", encoding="utf-8") as f:
                f.write(f"=== {sid} Director's Brief ===\n\n")
                f.write(prompt)
            print(f"  [{sid}] Prompt: {len(prompt)} chars")

    # Phase 3: Generate (Gemini + GPT in parallel)
    print(f"\n[PHASE 3] Generating {len(all_prompts)*2} images...")

    tasks = []
    for sid, prompt in all_prompts.items():
        tasks.append(("gemini", sid, prompt))
        tasks.append(("gpt", sid, prompt))

    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {}
        for model, sid, prompt in tasks:
            if model == "gemini":
                futures[ex.submit(generate_gemini_prompt_only, prompt, sid)] = (
                    model,
                    sid,
                )
            else:
                futures[ex.submit(generate_gpt_prompt_only, prompt, sid)] = (model, sid)

        for f in as_completed(futures):
            results.append(f.result())

    # Save reference images for comparison
    for scene in SCENES:
        ref = Image.open(MOOD_DIR / scene["ref"]).convert("RGB")
        ref.save(OUTPUT_DIR / f"{scene['id']}_00_reference.jpg", "JPEG", quality=95)

    gem_ok = sum(1 for r in results if r["model"] == "gemini" and r["status"] == "ok")
    gpt_ok = sum(1 for r in results if r["model"] == "gpt" and r["status"] == "ok")

    with open(OUTPUT_DIR / "config.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "strategy": "prompt-only (VLM analysis -> director brief -> generate)",
                "anti_ai_techniques": [
                    "captured moment",
                    "film camera specs",
                    "natural imperfections",
                    "candid action verbs",
                ],
                "gemini": gem_ok,
                "gpt": gpt_ok,
                "results": results,
            },
            f,
            indent=2,
        )

    print(f"\n{'=' * 60}")
    print(f"DONE")
    print(f"  Gemini: {gem_ok}/{len(all_prompts)}")
    print(f"  GPT: {gpt_ok}/{len(all_prompts)}")
    print(f"  Output: {OUTPUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
