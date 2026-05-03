# WORKFLOW_BYPASS_OK: strategy-cut-builder custom prompt pipeline (2026-04-30)
"""Discovery + MLB 전략실컷 테스트 — Gemini + GPT Image 2 동시 생성

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/generate_discovery_mlb_test.py
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
from core.options import get_cost

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STRATEGY_DIR = PROJECT_ROOT / ".claude" / "projects" / "strategy-cut-builder"
DB_DIR = PROJECT_ROOT / "db" / "strategy-cut-builder"
OUTPUT_BASE = PROJECT_ROOT / "Fnf_studio_outputs" / "strategy-cut-builder"

from scripts.strategy_cut_builder.attribute_to_prompt_multi import (
    load_json,
    build_celeb_prompt,
    build_influencer_prompt,
)

BRANDS = {
    "discovery": {
        "products": [
            {"file": "discovery-windbreaker-attributes.json", "name": "windbreaker"},
            {"file": "discovery-crop-down-attributes.json", "name": "crop_down"},
        ],
        "dna_file": "discovery.json",
        "ref_dir": DB_DIR / "discovery" / "instagram",
        "max_refs": 3,
    },
    "mlb": {
        "products": [
            {"file": "mlb-crop-tee-cap-attributes.json", "name": "crop_tee_cap"},
            {"file": "mlb-varsity-jacket-attributes.json", "name": "varsity_jacket"},
        ],
        "dna_file": "mlb.json",
        "ref_dir": DB_DIR / "mlb" / "instagram",
        "max_refs": 3,
    },
}


def load_images(directory: Path, max_count: int = 3) -> list:
    files = []
    for ext in ("*.jpg", "*.jpeg", "*.png"):
        files.extend(sorted(directory.glob(ext)))
    return [Image.open(p).convert("RGB") for p in files[:max_count]]


def generate_gemini(prompt, ref_imgs, aspect_ratio, task_id):
    client = genai.Client(api_key=_get_next_api_key())

    parts = [types.Part(text=prompt)]
    for i, ref in enumerate(ref_imgs):
        parts.append(
            types.Part(
                text=f"[MOOD REFERENCE {i+1}] — Match this brand mood and style:"
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
                        aspect_ratio=aspect_ratio,
                        image_size="2K",
                    ),
                ),
            )
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    from io import BytesIO

                    img = Image.open(BytesIO(part.inline_data.data))
                    return {
                        "image": img,
                        "model": "gemini",
                        "task_id": task_id,
                        "prompt": prompt,
                    }
            raise RuntimeError("No image in response")
        except Exception as e:
            if attempt < 2:
                time.sleep((attempt + 1) * 5)
            else:
                return {
                    "image": None,
                    "model": "gemini",
                    "task_id": task_id,
                    "error": str(e)[:200],
                    "prompt": prompt,
                }


def save_result(result, session_dir):
    if result["image"] is None:
        return None
    task_id = result["task_id"]
    model = result["model"]
    img_path = session_dir / f"{task_id}_{model}.png"
    meta_path = session_dir / f"{task_id}_{model}_meta.json"

    result["image"].save(str(img_path), "PNG")
    meta = {
        "model": model,
        "task_id": task_id,
        "prompt": result["prompt"],
        "timestamp": datetime.now().isoformat(),
        "resolution": "2K",
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return img_path


def run_brand(brand_name, brand_cfg):
    dna = load_json(str(STRATEGY_DIR / "brand-dna" / brand_cfg["dna_file"]))
    ref_imgs = load_images(brand_cfg["ref_dir"], brand_cfg["max_refs"])
    print(f"[{brand_name}] ref images: {len(ref_imgs)}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = OUTPUT_BASE / brand_name / f"{timestamp}_test"
    session_dir.mkdir(parents=True, exist_ok=True)

    tasks = []
    for prod_info in brand_cfg["products"]:
        attrs = load_json(str(STRATEGY_DIR / "products" / prod_info["file"]))
        prod_name = prod_info["name"]

        for i in range(3):
            prompt = build_celeb_prompt(attrs, dna, brand_name, variation=i)
            task_id = f"{prod_name}_celeb_{i+1:02d}"
            tasks.append((task_id, prompt, "3:4"))

        for i in range(3):
            prompt = build_influencer_prompt(attrs, dna, brand_name, variation=i)
            task_id = f"{prod_name}_infl_{i+1:02d}"
            tasks.append((task_id, prompt, "9:16"))

    print(f"[{brand_name}] {len(tasks)} prompts x Gemini = {len(tasks)} images")

    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {}
        for task_id, prompt, ratio in tasks:
            f = executor.submit(generate_gemini, prompt, ref_imgs, ratio, task_id)
            futures[f] = task_id

        for future in as_completed(futures):
            tid = futures[future]
            try:
                result = future.result()
                if result["image"]:
                    saved = save_result(result, session_dir)
                    print(f"  [{brand_name}] OK: {tid} -> {saved.name}")
                else:
                    err_short = result.get("error", "unknown")[:80]
                    print(f"  [{brand_name}] FAIL: {tid} - {err_short}")
                results.append(result)
            except Exception as e:
                print(f"  [{brand_name}] ERROR: {tid} - {e}")

    success = [r for r in results if r.get("image")]
    cost = get_cost("2K", len(success))

    print(
        f"\n[{brand_name}] Done: {len(success)}/{len(tasks)} images (cost: W{cost:,})"
    )
    print(f"[{brand_name}] Saved to: {session_dir}")
    return len(success), cost, session_dir


def main():
    print("=" * 60)
    print("Strategy Cut Builder — Discovery + MLB Test Generation")
    print("=" * 60)

    total_success = 0
    total_cost = 0

    for brand_name, brand_cfg in BRANDS.items():
        success, cost, session_dir = run_brand(brand_name, brand_cfg)
        total_success += success
        total_cost += cost

    print(f"\n{'=' * 60}")
    print(f"TOTAL: {total_success} images / W{total_cost:,}")
    print(f"{'=' * 60}")

    print("\n--- Output Context ---")
    print(
        f"Input: Discovery refs {BRANDS['discovery']['max_refs']}장 + MLB refs {BRANDS['mlb']['max_refs']}장"
    )
    print(f"Products: DX windbreaker + crop_down / MLB crop_tee_cap + varsity_jacket")
    print(f"Prompts: 4 products x 6 variations(celeb3+infl3) = 24 total")
    print(f"Output: {OUTPUT_BASE}/")


if __name__ == "__main__":
    main()
