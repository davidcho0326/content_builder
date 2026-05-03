# WORKFLOW_BYPASS_OK: strategy-cut-builder tuned generation (2026-04-30)
"""MLB feminine + Discovery — VLM-analyze actual reference images → tuned prompts

Key difference from previous: VLM analyzes EACH reference image to build
brand-specific "director's brief" instead of using generic templates.

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/generate_mlb_dx_tuned.py
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
from scripts.strategy_cut_builder.dna_to_prompt import load_dna, build_garment_prompt

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_BASE = PROJECT_ROOT / "Fnf_studio_outputs" / "strategy-cut-builder"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

MLB_MOOD = Path(r"C:\Users\AC1060\Downloads") / "mlb추구미페미닌"
DX_MOOD = Path(r"C:\Users\AC1060\Downloads") / "디스커버리 추구미"

VLM_PROMPT = """You are analyzing a Korean fashion influencer photo to create a generation prompt.
Extract EVERY visual detail as a cinematographer's shot sheet.

Return JSON:
{
  "moment": "describe the EXACT natural action/moment captured (NOT a pose, but what she's DOING)",
  "model_vibe": "describe this specific person's look — age, hair, face shape, body type, makeup, energy",
  "clothing_style": "describe every garment in detail — type, color, fit, length, fabric texture, how it's worn",
  "accessories": "every accessory visible — bags, hats, jewelry, socks, shoes with detail",
  "setting": "precise location description with textures and colors",
  "camera_feel": "what camera this looks like it was shot on, angle, framing, depth of field",
  "lighting": "light source, quality, color temperature, shadows",
  "color_grading": "overall color palette, filter feel, contrast, saturation",
  "unique_styling": "what makes this outfit/look DISTINCTIVE — the specific styling trick that stands out",
  "atmosphere": "one sentence emotional mood"
}
JSON only. Be obsessively specific."""

MLB_PROMPT_TEMPLATE = """A candid Korean fashion influencer Instagram photo, 3:4 portrait orientation.

THIS MUST LOOK LIKE A REAL KOREAN GEN-Z INFLUENCER'S INSTAGRAM POST — not a fashion campaign, not a studio shot.

THE GIRL: {model_vibe}. She looks like a K-pop girl group member on her day off — stunningly beautiful with a tiny small face, sharp V-line jaw, big double-eyelid eyes, flawless dewy glass skin, long silky straight black hair. Ultra slim with impossibly long legs. The kind of face that stops you scrolling on Instagram. She looks like she walked out of an AESPA or IVE music video but dressed in casual street fashion.

THE MOMENT: {moment}

SHE IS WEARING: {garment_desc}
HER STYLING: {unique_styling}
ACCESSORIES: {accessories}

CAMERA: {camera_feel}. This looks like it was taken on an iPhone by a friend, or a carefully staged "candid" that took 3 tries to get right. Slightly warm Instagram filter. NOT professional photography.

SETTING: {setting}

LIGHTING: {lighting}

COLOR: {color_grading}

THE VIBE: {atmosphere}. This photo would get 15K likes on Instagram. It looks REAL — real location, real girl, real moment. Not AI-generated, not stock photo, not catalog.

CRITICAL: She should look Korean, early 20s, with the specific Y2K/coquette/feminine Korean street style that's trending now. Long straight dark hair or styled with clips/ties. Dewy skin, subtle lip tint, natural brows. The clothes should look like something you'd actually see on Seongsu-dong or Gangnam streets."""

DX_PROMPT_TEMPLATE = """A candid wellness/active lifestyle influencer photo, 3:4 portrait orientation.

THIS MUST LOOK LIKE A REAL KOREAN FITNESS INFLUENCER'S INSTAGRAM — not a Nike ad, not a stock photo.

THE GIRL: {model_vibe}. Stunningly beautiful Korean girl with an athletic but slim build — tiny face, sharp jawline, toned but feminine body, sun-kissed glowing skin. She's the kind of gorgeous Korean fitness influencer who makes running look glamorous — naturally pretty even while sweating, the aspirational "hot wellness girl" who has 300K followers.

THE MOMENT: {moment}

SHE IS WEARING: {garment_desc}
HER STYLING: {unique_styling}
ACCESSORIES: {accessories}

CAMERA: {camera_feel}. iPhone quality, slightly action-blurred or post-workout candid. Could be a selfie, a friend's snap, or a set-up-but-natural outdoor shot.

SETTING: {setting}

LIGHTING: {lighting}

COLOR: {color_grading}

THE VIBE: {atmosphere}. This photo makes you want to go for a run. It looks REAL — sweaty but stylish, athletic but pretty, effort but ease. The kind of photo a Korean wellness influencer posts with a running emoji caption.

CRITICAL: She should look Korean, mid-20s, with a ponytail or messy bun, minimal makeup but dewy/glowy, athletic build but slim. The clothes should be functional activewear but look fashionable — not gym-bro, more like the girl who makes Salomon trail shoes and black running shorts look editorial."""


def analyze_ref(ref_path: Path) -> dict:
    client = genai.Client(api_key=_get_next_api_key())
    img = Image.open(ref_path).convert("RGB")
    img.thumbnail((1024, 1024), Image.LANCZOS)
    response = client.models.generate_content(
        model=VISION_MODEL,
        contents=[
            types.Content(
                role="user", parts=[types.Part(text=VLM_PROMPT), _pil_to_part(img)]
            )
        ],
        config=types.GenerateContentConfig(
            temperature=0.1, response_modalities=["TEXT"]
        ),
    )
    text = response.text.strip().replace("```json", "").replace("```", "").strip()
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return json.loads(text)


def build_mlb_prompt(analysis: dict, dna: dict, category: str) -> str:
    garment = build_garment_prompt(dna, category)
    return MLB_PROMPT_TEMPLATE.format(
        model_vibe=analysis.get("model_vibe", "Korean girl, early 20s, Y2K style"),
        moment=analysis["moment"],
        garment_desc=garment,
        unique_styling=analysis.get(
            "unique_styling", "cropped proportions with oversized bottom"
        ),
        accessories=analysis.get("accessories", "mini crossbody bag, baseball cap"),
        camera_feel=analysis.get(
            "camera_feel", "iPhone 15 Pro, eye level, casual framing"
        ),
        setting=analysis.get("setting", "Korean street cafe"),
        lighting=analysis.get("lighting", "natural daylight, warm"),
        color_grading=analysis.get(
            "color_grading", "warm, slightly overexposed, Instagram filter"
        ),
        atmosphere=analysis.get("atmosphere", "cool girl energy"),
    )


def build_dx_prompt(analysis: dict, dna: dict, category: str) -> str:
    garment = build_garment_prompt(dna, category)
    return DX_PROMPT_TEMPLATE.format(
        model_vibe=analysis.get("model_vibe", "Korean athletic girl, mid-20s, runner"),
        moment=analysis["moment"],
        garment_desc=garment,
        unique_styling=analysis.get(
            "unique_styling", "functional activewear styled fashionably"
        ),
        accessories=analysis.get(
            "accessories", "sports sunglasses, wireless earbuds, running watch"
        ),
        camera_feel=analysis.get("camera_feel", "iPhone, action angle"),
        setting=analysis.get("setting", "Seoul running trail"),
        lighting=analysis.get("lighting", "bright natural outdoor"),
        color_grading=analysis.get("color_grading", "bright, clean, high contrast"),
        atmosphere=analysis.get("atmosphere", "healthy active energy"),
    )


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
                    print(f"  [GEMINI OK] {sid}")
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
            print(f"  [GPT OK] {sid}")
            return {"id": sid, "model": "gpt", "status": "ok"}
        return {"id": sid, "model": "gpt", "status": "no_image"}
    except Exception as e:
        print(f"  [GPT FAIL] {sid}: {e}")
        return {"id": sid, "model": "gpt", "status": "error"}


def run_brand(brand_key, mood_dir, out_dir, refs_to_use, categories, prompt_builder):
    dna = load_dna(brand_key)
    out_dir.mkdir(parents=True, exist_ok=True)
    all_refs = sorted(
        [f for f in mood_dir.iterdir() if f.suffix in (".png", ".jpg", ".jpeg")]
    )

    print(f"\n{'='*50}")
    print(f"  {brand_key.upper()} — analyzing {len(refs_to_use)} refs")
    print(f"{'='*50}")

    # VLM analyze each reference
    analyses = {}
    for idx in refs_to_use:
        ref_file = all_refs[min(idx, len(all_refs) - 1)]
        sid = f"{brand_key.upper()}_{idx:02d}"
        try:
            analyses[sid] = analyze_ref(ref_file)
            analyses[sid]["_ref_file"] = ref_file.name
            analyses[sid]["_category"] = categories[
                refs_to_use.index(idx) % len(categories)
            ]
            Image.open(ref_file).convert("RGB").save(
                out_dir / f"{sid}_00_ref.jpg", "JPEG", quality=95
            )
            print(f"  [{sid}] Analyzed: {analyses[sid].get('atmosphere','?')[:40]}")
        except Exception as e:
            print(f"  [{sid}] FAIL: {e}")

    # Build prompts + generate
    prompts = {}
    for sid, a in analyses.items():
        cat = a["_category"]
        prompt = prompt_builder(a, dna, cat)
        prompts[sid] = prompt
        with open(out_dir / f"{sid}_prompt.txt", "w", encoding="utf-8") as f:
            f.write(prompt)

    print(f"\n  Generating {len(prompts)*2} images...")
    results = []
    tasks = [(m, sid, p) for sid, p in prompts.items() for m in ("gemini", "gpt")]

    with ThreadPoolExecutor(max_workers=5) as ex:
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

    return brand_key, gem, gpt


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"{'='*60}")
    print(f"MLB + Discovery TUNED Generation")
    print(f"VLM analyzes actual reference images -> brand-specific prompts")
    print(f"{'='*60}")

    mlb_out = OUTPUT_BASE / "mlb" / f"{TIMESTAMP}_tuned"
    dx_out = OUTPUT_BASE / "discovery" / f"{TIMESTAMP}_tuned"

    with ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(
            run_brand,
            "mlb",
            MLB_MOOD,
            mlb_out,
            [0, 1, 2, 4, 6, 8, 10, 12],
            ["tee", "tee", "set", "tee", "windbreaker", "tee", "set", "set"],
            build_mlb_prompt,
        )
        f2 = ex.submit(
            run_brand,
            "discovery",
            DX_MOOD,
            dx_out,
            [0, 1, 3, 5, 8, 10, 14],
            [
                "windbreaker",
                "windbreaker",
                "tee",
                "windbreaker",
                "sweatshirt_hoodie",
                "technical_vest",
                "windbreaker",
            ],
            build_dx_prompt,
        )

        for f in as_completed([f1, f2]):
            brand, gem, gpt = f.result()
            print(f"\n  {brand.upper()} DONE: Gemini {gem} | GPT {gpt}")

    print(f"\n{'='*60}")
    print(f"ALL DONE")
    print(f"  MLB: {mlb_out}")
    print(f"  Discovery: {dx_out}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
