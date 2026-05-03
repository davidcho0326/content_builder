# WORKFLOW_BYPASS_OK: strategy-cut-builder dual template pipeline (2026-04-30)
"""MLB dual generation — Campaign (editorial) + Influencer (snap) for each scene

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/generate_mlb_dual.py
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
    build_full_influencer_prompt,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MOOD_DIR = Path(r"C:\Users\AC1060\Downloads") / "mlb추구미"
OUTPUT_BASE = PROJECT_ROOT / "Fnf_studio_outputs" / "strategy-cut-builder" / "mlb"

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = OUTPUT_BASE / f"{TIMESTAMP}_dual"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BRAND = "mlb"
REF_FILES = sorted([f.name for f in MOOD_DIR.iterdir() if f.suffix in (".png", ".jpg")])

SCENES = [
    {
        "id": "TEE_01",
        "category": "tee",
        "ref_idx": 0,
        "campaign": {
            "moment": "she just stepped out of a matte-black SUV on a Seoul rooftop parking lot at sunset, one hand adjusting her MLB cap, the city skyline glowing amber behind her",
            "lens": "85mm f/1.8",
            "aperture": "f/2 -- cityscape blurred into bokeh",
            "film": "Kodak Portra 400 -- warm golden skin, cool blue sky",
            "framing": "Full body shot, model centered, low angle looking up slightly",
            "lighting": "Golden hour backlight from behind, warm rim on hair and shoulders, fill from car body reflection",
        },
        "influencer": {
            "moment": "she's checking her phone outside a Korean street cafe, leaning against the glass door, one hand holding an iced americano, the other adjusting her cap brim",
            "framing": "Upper body, slightly tilted phone angle",
            "lighting": "Bright afternoon, cafe neon warm accent, natural daylight",
        },
    },
    {
        "id": "SET_01",
        "category": "set",
        "ref_idx": 2,
        "campaign": {
            "moment": "she froze mid-stride on a concrete overpass, the wind catching her matching set, hair streaming behind her, one hand holding her cap, downtown traffic blurred below",
            "lens": "50mm f/1.4",
            "aperture": "f/2.8 -- urban background soft",
            "film": "Kodak Portra 800 -- grainy warm, urban energy",
            "framing": "Full body, dynamic walking pose, 3/4 angle, wind motion",
            "lighting": "Harsh midday sun, strong contrast, sharp shadows on concrete, reflected fill from white building",
        },
        "influencer": {
            "moment": "she's sitting on the hood of a white car in a parking lot, legs dangling, scrolling her phone with one hand, completely unbothered, her matching set catching the flat white light",
            "framing": "Medium full shot, casual sit, friend-took-this angle",
            "lighting": "Overcast bright, flat even light, parking lot white bounce",
        },
    },
    {
        "id": "WB_01",
        "category": "windbreaker",
        "ref_idx": 6,
        "campaign": {
            "moment": "she turned a corner in a Seoul alley as wind blasted through, her windbreaker billowing open, one hand reaching for the zipper, eyes squinting against the gust, graffiti wall behind her",
            "lens": "35mm f/2",
            "aperture": "f/4 -- alley environment visible and sharp",
            "film": "Kodak Gold 200 -- punchy saturated, warm concrete",
            "framing": "Full body, action shot mid-stride, environmental wide",
            "lighting": "Strong directional afternoon sun cutting through alley, deep shadow on one side, warm light stripe on model",
        },
        "influencer": {
            "moment": "she's standing outside a convenience store at night, one hand in her windbreaker pocket, the other holding a snack, fluorescent store light mixing with warm streetlight on her face",
            "framing": "Medium shot, casual standing, slightly below eye level",
            "lighting": "Mixed warm streetlight + cool fluorescent, night urban glow",
        },
    },
    {
        "id": "JACKET_01",
        "category": "jacket",
        "ref_idx": 14,
        "campaign": {
            "moment": "she just caught a basketball mid-air on an empty outdoor court at dusk, her varsity jacket sleeve stretched, sweat glistening, the court lights just flickering on behind her",
            "lens": "70mm f/2",
            "aperture": "f/2.8 -- court lights creating bokeh circles",
            "film": "Kodak Portra 800 -- warm skin under mixed light, visible grain",
            "framing": "Medium full shot, athletic action, dynamic pose",
            "lighting": "Blue-hour sky with warm court lights just turning on, mixed color temperature, dramatic",
        },
        "influencer": {
            "moment": "she's walking out of a late-night restaurant pulling her varsity jacket collar up against the cool air, neon sign reflecting on the jacket fabric, friend behind her laughing out of frame",
            "framing": "Upper body, slightly blurred background, candid snap",
            "lighting": "Warm restaurant interior spilling out + cool night air + colored neon",
        },
    },
    {
        "id": "PANTS_01",
        "category": "pants",
        "ref_idx": 10,
        "campaign": {
            "moment": "she dropped into a low squat on a skatepark ramp to tie her sneaker, cargo pants pooling around her ankles, looking up at the camera with zero effort cool, late afternoon light raking across the concrete",
            "lens": "35mm f/2",
            "aperture": "f/4 -- skatepark environment sharp",
            "film": "Kodak Ektar 100 -- vivid, sharp, punchy contrast",
            "framing": "Full body, low squat pose, slightly low angle",
            "lighting": "Low afternoon sun, extreme warm side-light, long shadows",
        },
        "influencer": {
            "moment": "she's sitting on concrete stairs outside a building, legs stretched showing her cargo pants, one hand behind her, looking at her phone screen, completely casual",
            "framing": "Full body sitting, stairs visible, friend POV from above",
            "lighting": "Bright daylight, concrete bounce light, even exposure",
        },
    },
]

MOMENTS_MAP = {s["id"]: s for s in SCENES}


def analyze_ref(ref_path: Path) -> dict:
    client = genai.Client(api_key=_get_next_api_key())
    img = Image.open(ref_path).convert("RGB")
    img.thumbnail((1024, 1024), Image.LANCZOS)
    prompt = '{"color_grading":"","lighting_quality":"","atmosphere":"","key_texture":""} Fill these from the image. JSON only.'
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


def gen_gemini(prompt: str, sid: str) -> dict:
    client = genai.Client(api_key=_get_next_api_key())
    for attempt in range(3):
        try:
            r = client.models.generate_content(
                model=IMAGE_MODEL,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=types.GenerateContentConfig(
                    temperature=1.0,
                    response_modalities=["IMAGE", "TEXT"],
                    image_config=types.ImageConfig(aspect_ratio="3:4"),
                ),
            )
            for p in r.candidates[0].content.parts:
                if hasattr(p, "inline_data") and p.inline_data:
                    img = Image.open(io.BytesIO(p.inline_data.data)).convert("RGB")
                    img.save(OUTPUT_DIR / f"{sid}_gemini.png", "PNG")
                    print(f"  [GEMINI OK] {sid}: {img.size[0]}x{img.size[1]}")
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
            return {"id": sid, "model": "gemini", "status": "error"}


def gen_gpt(prompt: str, sid: str) -> dict:
    try:
        img = generate_gpt_image(
            prompt=prompt, aspect_ratio="3:4", resolution="2K", quality="high"
        )
        if img:
            img.save(OUTPUT_DIR / f"{sid}_gpt.png", "PNG")
            print(f"  [GPT OK] {sid}: {img.size[0]}x{img.size[1]}")
            return {"id": sid, "model": "gpt", "status": "ok"}
        return {"id": sid, "model": "gpt", "status": "no_image"}
    except Exception as e:
        print(f"  [GPT FAIL] {sid}: {e}")
        return {"id": sid, "model": "gpt", "status": "error"}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    dna = load_dna(BRAND)

    print(f"{'=' * 60}")
    print(f"MLB Dual Pipeline (Campaign + Influencer)")
    print(f"Scenes: {len(SCENES)} x 2 types x 2 models = {len(SCENES)*4} images")
    print(f"{'=' * 60}")

    # Phase 1: VLM
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
            except:
                ref_analyses[sid] = {}
                print(f"  [{sid}] FAIL")

    # Phase 2: Build prompts (campaign + influencer for each scene)
    print("\n[PHASE 2] Building dual prompts...")
    prompts = {}
    for scene in SCENES:
        sid = scene["id"]
        ref_extra = ref_analyses.get(sid, {})
        cg = ref_extra.get("color_grading", "warm urban tones")
        atm = ref_extra.get("atmosphere", "cool street energy")
        enrich = f"\n\nCOLOR GRADING: {cg}.\nATMOSPHERE: {atm}."

        # Campaign prompt
        c = scene["campaign"]
        camp_prompt = build_full_editorial_prompt(
            dna,
            scene["category"],
            moment=c["moment"],
            lens=c["lens"],
            aperture=c["aperture"],
            film=c["film"],
            framing=c["framing"],
            lighting_desc=c["lighting"],
        )
        camp_prompt = (
            camp_prompt.replace("Vogue Italia", "W Korea / Dazed Korea") + enrich
        )
        prompts[f"{sid}_CAMP"] = camp_prompt

        # Influencer prompt
        inf = scene["influencer"]
        inf_prompt = (
            build_full_influencer_prompt(
                dna,
                scene["category"],
                moment=inf["moment"],
                framing=inf["framing"],
                lighting_desc=inf["lighting"],
            )
            + enrich
        )
        prompts[f"{sid}_INFL"] = inf_prompt

        for key, prompt in [(f"{sid}_CAMP", camp_prompt), (f"{sid}_INFL", inf_prompt)]:
            with open(OUTPUT_DIR / f"{key}_prompt.txt", "w", encoding="utf-8") as f:
                f.write(prompt)

    # Save refs
    for scene in SCENES:
        ref_file = REF_FILES[min(scene["ref_idx"], len(REF_FILES) - 1)]
        Image.open(MOOD_DIR / ref_file).convert("RGB").save(
            OUTPUT_DIR / f"{scene['id']}_00_reference.jpg", "JPEG", quality=95
        )

    # Phase 3: Generate all
    total = len(prompts) * 2
    print(f"\n[PHASE 3] Generating {total} images...")
    results = []
    tasks = [(m, sid, p) for sid, p in prompts.items() for m in ("gemini", "gpt")]

    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {
            ex.submit(gen_gemini if m == "gemini" else gen_gpt, p, sid): (m, sid)
            for m, sid, p in tasks
        }
        for f in as_completed(futures):
            results.append(f.result())

    gem_ok = sum(1 for r in results if r["model"] == "gemini" and r["status"] == "ok")
    gpt_ok = sum(1 for r in results if r["model"] == "gpt" and r["status"] == "ok")
    camp_ok = sum(1 for r in results if "_CAMP" in r["id"] and r["status"] == "ok")
    infl_ok = sum(1 for r in results if "_INFL" in r["id"] and r["status"] == "ok")

    with open(OUTPUT_DIR / "config.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "brand": BRAND,
                "gemini": gem_ok,
                "gpt": gpt_ok,
                "campaign": camp_ok,
                "influencer": infl_ok,
                "results": results,
            },
            f,
            indent=2,
        )

    print(f"\n{'=' * 60}")
    print(f"DONE")
    print(
        f"  Campaign: {camp_ok}/{len(SCENES)*2} | Influencer: {infl_ok}/{len(SCENES)*2}"
    )
    print(f"  Gemini: {gem_ok} | GPT: {gpt_ok}")
    print(f"  Output: {OUTPUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
