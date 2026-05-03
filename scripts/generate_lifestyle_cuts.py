# WORKFLOW_BYPASS_OK: strategy-cut-builder lifestyle generation (2026-04-30)
"""라이프스타일 전략 기반 이미지 생성 — Gemini + GPT 병렬

Discovery 4필러(6시나리오) + MLB 3Phase(6시나리오) = 12시나리오 x 2모델 = 24장

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/generate_lifestyle_cuts.py
"""

import sys
import io
import json
import time
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

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
from core.options import get_cost, get_gpt_cost

from scripts.strategy_cut_builder.lifestyle_scenarios import (
    DISCOVERY_SCENARIOS,
    MLB_SCENARIOS,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_DIR = PROJECT_ROOT / "db" / "strategy-cut-builder"
OUTPUT_BASE = PROJECT_ROOT / "Fnf_studio_outputs" / "strategy-cut-builder"


def load_ref_images(brand: str, max_count: int = 3) -> list:
    ref_dir = DB_DIR / brand / "instagram"
    files = sorted(ref_dir.glob("*.jpg"))[:max_count]
    return [Image.open(p).convert("RGB") for p in files]


def gen_gemini(prompt, ref_imgs, scenario_id):
    client = genai.Client(api_key=_get_next_api_key())
    parts = [types.Part(text=prompt)]
    for i, ref in enumerate(ref_imgs):
        parts.append(
            types.Part(
                text=f"[BRAND REFERENCE {i+1}] — Match this brand's visual identity:"
            )
        )
        parts.append(_pil_to_part(ref))

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=IMAGE_MODEL,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    response_modalities=["IMAGE", "TEXT"],
                    image_config=types.ImageConfig(
                        aspect_ratio="9:16", image_size="2K"
                    ),
                ),
            )
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    from io import BytesIO

                    return {
                        "image": Image.open(BytesIO(part.inline_data.data)),
                        "model": "gemini",
                        "id": scenario_id,
                    }
            raise RuntimeError("No image")
        except Exception as e:
            if attempt < 2:
                time.sleep((attempt + 1) * 5)
            else:
                return {
                    "image": None,
                    "model": "gemini",
                    "id": scenario_id,
                    "error": str(e)[:150],
                }


def gen_gpt(prompt, ref_imgs, scenario_id):
    temp_files = pil_list_to_temp_files(ref_imgs[:2])
    try:
        img = generate_gpt_image(
            prompt=prompt,
            reference_images=[Path(f) for f in temp_files],
            aspect_ratio="9:16",
            resolution="2K",
            quality="high",
        )
        return {"image": img, "model": "gpt", "id": scenario_id}
    except Exception as e:
        return {"image": None, "model": "gpt", "id": scenario_id, "error": str(e)[:150]}
    finally:
        cleanup_temp_files(temp_files)


def save(result, out_dir):
    if not result.get("image"):
        return None
    sid = result["id"]
    model = result["model"]
    fpath = out_dir / f"{sid}_{model}.png"
    result["image"].save(str(fpath), "PNG")

    meta = {"id": sid, "model": model, "timestamp": datetime.now().isoformat()}
    with open(out_dir / f"{sid}_{model}_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return fpath


def main():
    print("=" * 60)
    print("Lifestyle Strategy Cut Generation")
    print("Discovery 6 scenarios + MLB 6 scenarios")
    print("x 2 models (Gemini + GPT) = 24 images")
    print("=" * 60)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dx_dir = OUTPUT_BASE / "discovery" / f"{ts}_lifestyle"
    mlb_dir = OUTPUT_BASE / "mlb" / f"{ts}_lifestyle"
    dx_dir.mkdir(parents=True, exist_ok=True)
    mlb_dir.mkdir(parents=True, exist_ok=True)

    dx_refs = load_ref_images("discovery", 3)
    mlb_refs = load_ref_images("mlb", 3)
    print(f"Refs loaded: Discovery {len(dx_refs)}, MLB {len(mlb_refs)}")

    all_tasks = []
    for s in DISCOVERY_SCENARIOS:
        all_tasks.append(("discovery", s["id"], s["prompt"], dx_refs, dx_dir))
    for s in MLB_SCENARIOS:
        all_tasks.append(("mlb", s["id"], s["prompt"], mlb_refs, mlb_dir))

    print(f"\n{len(all_tasks)} scenarios x 2 models = {len(all_tasks)*2} images\n")

    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {}
        for brand, sid, prompt, refs, out_dir in all_tasks:
            fg = executor.submit(gen_gemini, prompt, refs, sid)
            futures[fg] = (brand, sid, "gemini", out_dir)

            fp = executor.submit(gen_gpt, prompt, refs, sid)
            futures[fp] = (brand, sid, "gpt", out_dir)

        for future in as_completed(futures):
            brand, sid, model, out_dir = futures[future]
            try:
                result = future.result()
                if result.get("image"):
                    saved = save(result, out_dir)
                    print(f"  OK [{brand}] {sid}_{model} -> {saved.name}")
                else:
                    print(
                        f"  FAIL [{brand}] {sid}_{model}: {result.get('error','?')[:80]}"
                    )
                results.append(result)
            except Exception as e:
                print(f"  ERR [{brand}] {sid}_{model}: {e}")

    gem_ok = [r for r in results if r.get("image") and r["model"] == "gemini"]
    gpt_ok = [r for r in results if r.get("image") and r["model"] == "gpt"]
    gem_cost = get_cost("2K", len(gem_ok))
    gpt_cost = get_gpt_cost("high", len(gpt_ok))

    print(f"\n{'='*60}")
    print(f"DONE: {len(gem_ok)+len(gpt_ok)}/{len(all_tasks)*2} images")
    print(f"  Gemini: {len(gem_ok)} (W{gem_cost:,})")
    print(f"  GPT:    {len(gpt_ok)} (W{gpt_cost:,})")
    print(f"  Total:  W{gem_cost+gpt_cost:,}")
    print(f"\nDiscovery: {dx_dir}")
    print(f"MLB:       {mlb_dir}")
    print(f"{'='*60}")

    # Print scenario summary
    print("\n--- Discovery Lifestyle Scenarios ---")
    for s in DISCOVERY_SCENARIOS:
        print(f"  {s['id']}: {s['title']} ({s['pillar']}) {' '.join(s['hashtags'])}")
    print("\n--- MLB Lifestyle Scenarios ---")
    for s in MLB_SCENARIOS:
        print(f"  {s['id']}: {s['title']} ({s['phase']}) [{s['mood']}]")


if __name__ == "__main__":
    main()
