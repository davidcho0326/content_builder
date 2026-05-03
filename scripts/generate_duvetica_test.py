# WORKFLOW_BYPASS_OK: strategy-cut-builder custom prompt pipeline (2026-04-30)
"""듀베티카 안드레타 테스트 — Gemini + GPT Image 2 동시 생성

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/generate_duvetica_test.py
"""

import json
import time
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

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
from core.options import get_gpt_size, get_gpt_quality, get_gpt_cost, get_cost

PROJECT_ROOT = Path(__file__).resolve().parents[2]

STRATEGY_DIR = PROJECT_ROOT / ".claude" / "projects" / "strategy-cut-builder"
REF_DIR = PROJECT_ROOT / "db" / "strategy-cut-builder" / "duvetica" / "references"
OUTFIT_DIR = PROJECT_ROOT / "db" / "strategy-cut-builder" / "duvetica" / "andretta"
OUTPUT_BASE = PROJECT_ROOT / "Fnf_studio_outputs" / "strategy-cut-builder" / "duvetica"

from scripts.strategy_cut_builder.attribute_to_prompt import (
    load_json,
    build_celeb_prompt,
    build_influencer_prompt,
)


def load_images(directory: Path, max_count: int = 3) -> list:
    exts = ("*.jpg", "*.jpeg", "*.png")
    files = []
    for ext in exts:
        files.extend(sorted(directory.glob(ext)))
    return [Image.open(p).convert("RGB") for p in files[:max_count]]


def generate_gemini(
    prompt: str, outfit_imgs: list, ref_imgs: list, aspect_ratio: str, idx: int
) -> dict:
    client = genai.Client(api_key=_get_next_api_key())

    parts = [types.Part(text=prompt)]
    for i, ref in enumerate(ref_imgs):
        parts.append(
            types.Part(text=f"[MOOD REFERENCE {i+1}] — Copy this mood and tone:")
        )
        parts.append(_pil_to_part(ref))
    for i, outfit in enumerate(outfit_imgs):
        parts.append(
            types.Part(
                text=f"[PRODUCT REFERENCE {i+1}] — Reproduce this outfit EXACTLY:"
            )
        )
        parts.append(_pil_to_part(outfit))

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
                        "index": idx,
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
                    "index": idx,
                    "error": str(e),
                    "prompt": prompt,
                }


def generate_gpt(
    prompt: str, outfit_imgs: list, ref_imgs: list, aspect_ratio: str, idx: int
) -> dict:
    all_imgs = ref_imgs[:2] + outfit_imgs[:2]
    temp_files = pil_list_to_temp_files(all_imgs)
    try:
        img = generate_gpt_image(
            prompt=prompt,
            reference_images=[Path(f) for f in temp_files],
            aspect_ratio=aspect_ratio,
            resolution="2K",
            quality="high",
        )
        return {"image": img, "model": "gpt", "index": idx, "prompt": prompt}
    except Exception as e:
        return {
            "image": None,
            "model": "gpt",
            "index": idx,
            "error": str(e),
            "prompt": prompt,
        }
    finally:
        cleanup_temp_files(temp_files)


def save_result(result: dict, session_dir: Path, cut_type: str) -> Path:
    if result["image"] is None:
        return None
    model = result["model"]
    idx = result["index"]
    img_path = session_dir / f"{cut_type}_{idx+1:02d}_{model}.png"
    meta_path = session_dir / f"{cut_type}_{idx+1:02d}_{model}_meta.json"

    result["image"].save(str(img_path), "PNG")
    meta = {
        "model": model,
        "index": idx,
        "cut_type": cut_type,
        "prompt": result["prompt"],
        "timestamp": datetime.now().isoformat(),
        "aspect_ratio": "3:4" if cut_type == "celeb" else "9:16",
        "resolution": "2K",
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return img_path


def main():
    attrs = load_json(str(STRATEGY_DIR / "products" / "andretta-attributes.json"))
    dna = load_json(str(STRATEGY_DIR / "brand-dna" / "duvetica.json"))

    ref_imgs = load_images(REF_DIR, max_count=3)
    outfit_imgs = load_images(OUTFIT_DIR, max_count=2)
    print(f"레퍼런스 {len(ref_imgs)}장, 착장 {len(outfit_imgs)}장 로드")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = OUTPUT_BASE / f"{timestamp}_andretta_test"
    session_dir.mkdir(parents=True, exist_ok=True)

    tasks = []

    for i in range(3):
        celeb_prompt = build_celeb_prompt(attrs, dna, variation=i)
        tasks.append(("celeb", celeb_prompt, "3:4", i))

    for i in range(3):
        infl_prompt = build_influencer_prompt(attrs, dna, variation=i)
        tasks.append(("influencer", infl_prompt, "9:16", i))

    print(
        f"\n총 {len(tasks)}개 프롬프트 × 2모델(Gemini+GPT) = {len(tasks)*2}장 생성 시작\n"
    )

    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {}
        for cut_type, prompt, ratio, idx in tasks:
            f_gem = executor.submit(
                generate_gemini, prompt, outfit_imgs, ref_imgs, ratio, idx
            )
            futures[f_gem] = (cut_type, "gemini", idx)

            f_gpt = executor.submit(
                generate_gpt, prompt, outfit_imgs, ref_imgs, ratio, idx
            )
            futures[f_gpt] = (cut_type, "gpt", idx)

        for future in as_completed(futures):
            cut_type, model, idx = futures[future]
            try:
                result = future.result()
                if result["image"]:
                    saved = save_result(result, session_dir, cut_type)
                    print(f"  OK: {cut_type}_{idx+1:02d}_{model} -> {saved.name}")
                else:
                    print(
                        f"  FAIL: {cut_type}_{idx+1:02d}_{model} - {result.get('error', 'unknown')}"
                    )
                results.append(result)
            except Exception as e:
                print(f"  ERROR: {cut_type}_{idx+1:02d}_{model} - {e}")

    success = [r for r in results if r.get("image")]
    gemini_ok = [r for r in success if r["model"] == "gemini"]
    gpt_ok = [r for r in success if r["model"] == "gpt"]

    gemini_cost = get_cost("2K", len(gemini_ok))
    gpt_cost = get_gpt_cost("high", len(gpt_ok))

    print(f"\n{'='*60}")
    print(f"생성 완료: {len(success)}/{len(tasks)*2}장")
    print(f"  Gemini: {len(gemini_ok)}장 (₩{gemini_cost:,})")
    print(f"  GPT:    {len(gpt_ok)}장 (₩{gpt_cost:,})")
    print(f"  총 비용: ₩{gemini_cost + gpt_cost:,}")
    print(f"저장 위치: {session_dir}")
    print(f"{'='*60}")

    for r in success:
        print(f"\n--- {r['model'].upper()} {r['index']+1} ---")
        print(f"인풋: 착장 {len(outfit_imgs)}장 + 레퍼런스 {len(ref_imgs)}장")
        print(f"프롬프트 (앞 300자):\n{r['prompt'][:300]}...")


if __name__ == "__main__":
    main()
