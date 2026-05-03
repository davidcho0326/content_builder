# WORKFLOW_BYPASS_OK: strategy-cut-builder parallel multi-brand (2026-04-30)
"""MLB feminine + Discovery parallel generation

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/generate_mlb_discovery_parallel.py
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
OUTPUT_BASE = PROJECT_ROOT / "Fnf_studio_outputs" / "strategy-cut-builder"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

MLB_MOOD = Path(r"C:\Users\AC1060\Downloads") / "mlb추구미페미닌"
DX_MOOD = Path(r"C:\Users\AC1060\Downloads") / "디스커버리 추구미"

MLB_REFS = sorted(
    [f.name for f in MLB_MOOD.iterdir() if f.suffix in (".png", ".jpg", ".jpeg")]
)
DX_REFS = sorted(
    [f.name for f in DX_MOOD.iterdir() if f.suffix in (".png", ".jpg", ".jpeg")]
)

BRANDS = {
    "mlb": {
        "mood_dir": MLB_MOOD,
        "refs": MLB_REFS,
        "output_dir": OUTPUT_BASE / "mlb" / f"{TIMESTAMP}_feminine",
        "scenes": [
            {
                "id": "FEM_01",
                "category": "tee",
                "ref_idx": 0,
                "moment": "she's leaning against a cafe doorway scrolling her phone, one leg crossed behind the other, her cropped MLB tee riding up just slightly, a mini crossbody bag dangling from her shoulder",
                "framing": "Full body, leaning pose, cafe entrance visible",
                "lighting": "Overcast soft, warm cafe interior glow spilling out",
            },
            {
                "id": "FEM_02",
                "category": "tee",
                "ref_idx": 2,
                "moment": "she just stepped off a crosswalk holding an iced coffee, wind catching her oversized graphic tee over a bubble mini skirt, bucket hat tilted, looking down at her phone mid-stride",
                "framing": "Full body walking, street with cars behind",
                "lighting": "Bright midday, flat even, urban bounce light",
            },
            {
                "id": "FEM_03",
                "category": "set",
                "ref_idx": 4,
                "moment": "she stopped mid-walk to take a selfie in a shop window reflection, one hand holding her phone up, the other adjusting her matching crop top, her pleated mini skirt caught in a slight breeze",
                "framing": "Full body, reflection visible in glass",
                "lighting": "Afternoon light, glass reflection creating double exposure feel",
            },
            {
                "id": "FEM_04",
                "category": "tee",
                "ref_idx": 8,
                "moment": "she's sitting on a concrete bench outside a bakery, legs crossed showing white crew socks and mary jane shoes, holding a pastry bag, looking up at someone off-camera with a half-smile",
                "framing": "Medium full, sitting casual, bakery signage behind",
                "lighting": "Warm afternoon, brick wall warm bounce, soft shadows",
            },
            {
                "id": "FEM_05",
                "category": "set",
                "ref_idx": 12,
                "moment": "she just turned around on a rooftop holding a film camera, her matching tank top and shorts set catching the sunset light, ponytail swinging, city skyline behind her going orange",
                "framing": "Full body, rooftop with skyline, golden backlight",
                "lighting": "Golden hour backlight, warm rim on edges, lens flare",
            },
            {
                "id": "FEM_06",
                "category": "windbreaker",
                "ref_idx": 6,
                "moment": "she's walking through a parking lot with earbuds in, oversized zip-up hoodie half-open over a mini skirt, sneakers on concrete, holding her phone like she's changing a song",
                "framing": "Full body walking, parking lot with cars behind",
                "lighting": "Flat daylight, car paint reflections, urban grey tones",
            },
        ],
    },
    "discovery": {
        "mood_dir": DX_MOOD,
        "refs": DX_REFS,
        "output_dir": OUTPUT_BASE / "discovery" / f"{TIMESTAMP}_active",
        "scenes": [
            {
                "id": "RUN_01",
                "category": "windbreaker",
                "ref_idx": 0,
                "moment": "she just paused her morning run to catch her breath at a Han River overlook, hands on hips, ponytail swaying, the river path stretching behind her into morning haze",
                "framing": "Full body, runner's pause stance, river path behind",
                "lighting": "Early morning golden, low sun angle, misty atmosphere",
            },
            {
                "id": "RUN_02",
                "category": "tee",
                "ref_idx": 3,
                "moment": "she's mid-stride on a forest running trail, ponytail flying, sports sunglasses on, arms pumping, compression socks visible, other runners blurred in the far background",
                "framing": "Full body action, running mid-stride, trail behind",
                "lighting": "Dappled forest light through trees, green ambient",
            },
            {
                "id": "WELL_01",
                "category": "windbreaker",
                "ref_idx": 5,
                "moment": "she just finished a run and stopped at a juice bar patio, unzipping her windbreaker showing a sports bra underneath, one hand holding a green smoothie, headphones around her neck, glowing with sweat",
                "framing": "Upper body, post-workout casual, outdoor patio",
                "lighting": "Bright afternoon, warm skin glow, white umbrella diffusion",
            },
            {
                "id": "WELL_02",
                "category": "sweatshirt_hoodie",
                "ref_idx": 8,
                "moment": "she's stretching against a white ranch fence after a morning workout, one leg up on the rail, oversized hoodie sleeves pushed past her wrists, blue sky and rolling hills behind her",
                "framing": "Full body, stretching pose, ranch landscape wide",
                "lighting": "Clean bright daylight, blue sky, green grass warmth",
            },
            {
                "id": "HIKE_01",
                "category": "technical_vest",
                "ref_idx": 10,
                "moment": "she paused on a mountain trail to take a selfie, one arm extended holding the camera, technical vest over a long-sleeve base layer, mountain ridge visible behind, slightly out of breath with a real smile",
                "framing": "Selfie angle from above, mountain background, close",
                "lighting": "High altitude bright, blue sky, crisp shadows",
            },
            {
                "id": "URBAN_01",
                "category": "windbreaker",
                "ref_idx": 14,
                "moment": "she's walking her small dog on an urban greenway path wearing headphones, windbreaker half-zipped, one hand holding the leash, the other her phone, completely in her own world, morning light on the green path",
                "framing": "Full body walking with dog, greenway path stretching",
                "lighting": "Morning sun low angle, green grass glow, warm backlight",
            },
        ],
    },
}


def analyze_ref(ref_path: Path) -> dict:
    client = genai.Client(api_key=_get_next_api_key())
    img = Image.open(ref_path).convert("RGB")
    img.thumbnail((1024, 1024), Image.LANCZOS)
    prompt = '{"color_grading":"","lighting_quality":"","atmosphere":"","key_texture":""} Fill from image. JSON only.'
    r = client.models.generate_content(
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
    text = r.text.strip().replace("```json", "").replace("```", "").strip()
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return json.loads(text)


def gen_gemini(prompt, sid, out_dir):
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
                    img.save(out_dir / f"{sid}_gemini.png", "PNG")
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


def gen_gpt(prompt, sid, out_dir):
    try:
        img = generate_gpt_image(
            prompt=prompt, aspect_ratio="3:4", resolution="2K", quality="high"
        )
        if img:
            img.save(out_dir / f"{sid}_gpt.png", "PNG")
            print(f"  [GPT OK] {sid}: {img.size[0]}x{img.size[1]}")
            return {"id": sid, "model": "gpt", "status": "ok"}
        return {"id": sid, "model": "gpt", "status": "no_image"}
    except Exception as e:
        print(f"  [GPT FAIL] {sid}: {e}")
        return {"id": sid, "model": "gpt", "status": "error"}


def run_brand(brand_key, brand_cfg):
    dna = load_dna(brand_key)
    out_dir = brand_cfg["output_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    mood_dir = brand_cfg["mood_dir"]
    refs = brand_cfg["refs"]
    scenes = brand_cfg["scenes"]

    print(f"\n{'='*50}")
    print(f"  {brand_key.upper()} — {len(scenes)} scenes x 2 models")
    print(f"{'='*50}")

    # VLM analyze
    ref_analyses = {}
    for s in scenes:
        ref_file = refs[min(s["ref_idx"], len(refs) - 1)]
        try:
            ref_analyses[s["id"]] = analyze_ref(mood_dir / ref_file)
        except:
            ref_analyses[s["id"]] = {}
        Image.open(mood_dir / ref_file).convert("RGB").save(
            out_dir / f"{s['id']}_00_reference.jpg", "JPEG", quality=95
        )

    # Build prompts
    prompts = {}
    for s in scenes:
        ref_extra = ref_analyses.get(s["id"], {})
        cg = ref_extra.get("color_grading", "natural warm tones")
        atm = ref_extra.get("atmosphere", "energetic casual")
        enrich = f"\n\nCOLOR GRADING: {cg}.\nATMOSPHERE: {atm}."

        prompt = (
            build_full_influencer_prompt(
                dna,
                s["category"],
                moment=s["moment"],
                framing=s["framing"],
                lighting_desc=s["lighting"],
            )
            + enrich
        )

        prompts[s["id"]] = prompt
        with open(out_dir / f"{s['id']}_prompt.txt", "w", encoding="utf-8") as f:
            f.write(prompt)

    # Generate
    results = []
    tasks = [(m, sid, p) for sid, p in prompts.items() for m in ("gemini", "gpt")]
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {
            ex.submit(gen_gemini if m == "gemini" else gen_gpt, p, sid, out_dir): sid
            for m, sid, p in tasks
        }
        for f in as_completed(futures):
            results.append(f.result())

    gem = sum(1 for r in results if r["model"] == "gemini" and r["status"] == "ok")
    gpt = sum(1 for r in results if r["model"] == "gpt" and r["status"] == "ok")

    with open(out_dir / "config.json", "w", encoding="utf-8") as f:
        json.dump(
            {"brand": brand_key, "gemini": gem, "gpt": gpt, "results": results},
            f,
            indent=2,
        )

    return brand_key, gem, gpt, out_dir


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"{'='*60}")
    print(f"MULTI-BRAND PARALLEL GENERATION")
    print(f"MLB feminine + Discovery active")
    total = sum(len(b["scenes"]) * 2 for b in BRANDS.values())
    print(f"Total: {total} images")
    print(f"{'='*60}")

    all_results = {}
    with ThreadPoolExecutor(max_workers=2) as ex:
        futures = {ex.submit(run_brand, k, v): k for k, v in BRANDS.items()}
        for f in as_completed(futures):
            brand, gem, gpt, out_dir = f.result()
            all_results[brand] = {"gemini": gem, "gpt": gpt, "output": str(out_dir)}

    print(f"\n{'='*60}")
    print(f"ALL DONE")
    for brand, r in all_results.items():
        print(f"  {brand.upper()}: Gemini {r['gemini']} | GPT {r['gpt']}")
        print(f"    -> {r['output']}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
