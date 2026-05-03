# WORKFLOW_BYPASS_OK: strategy-cut-builder 50장 일관성/실패율 대량 테스트 (2026-04-30)
"""Duvetica WJ 카테고리 50장 대량 생성 테스트

목적: 일관성 및 실패율 측정
방법: build_full_editorial_prompt() + DNA weighted random + 다양한 카메라/씬 조합
모델: Gemini only (비용 절감)

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/bulk_test_duvetica.py
"""

import io
import json
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv(override=True)

from PIL import Image
from google import genai
from google.genai import types

from core.config import IMAGE_MODEL, VISION_MODEL
from core.api import _get_next_api_key, _pil_to_part

from scripts.strategy_cut_builder.dna_to_prompt import (
    load_dna,
    build_full_editorial_prompt,
)

# ============================================================
# 설정
# ============================================================
TOTAL_IMAGES = 50
MAX_WORKERS = 5
BRAND = "duvetica"
CATEGORY = "woven_jacket"  # WJ 카테고리 고정
ASPECT_RATIO = "3:4"
TEMPERATURE = 1.0

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MOOD_DIR = Path(r"C:\Users\AC1060\Downloads") / "듀베티카"
OUTPUT_BASE = PROJECT_ROOT / "Fnf_studio_outputs" / "strategy-cut-builder" / "duvetica"

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = OUTPUT_BASE / f"{TIMESTAMP}_bulk_test"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# 씬/카메라 다양성 풀 (10가지 씬 x 다양한 카메라 설정)
# ============================================================

MOMENTS_POOL = [
    # 씬 1: 보트 위 호수
    "she just turned her head from gazing at the lake, the water still reflecting in her eyes, one hand resting lightly on the wooden railing",
    # 씬 2: 정원 석조
    "she paused mid-step to watch a butterfly settle on the stone wall beside her, one shoulder slightly raised, a quiet half-smile at the corner of her mouth",
    # 씬 3: 테라스 오버룩
    "the wind from the terrace railing caught her jacket open for a moment — she reached up instinctively to hold it, looking toward the sea",
    # 씬 4: 빌라 아치웨이
    "she exhaled slowly in the warm shadow of the villa arch, eyes drifting toward the afternoon light beyond, the weight of nothing pressing on her",
    # 씬 5: 유적지 돌
    "she was tracing the carved surface of an ancient stone when she looked up, weight shifted to one hip, the late afternoon casting long shadows behind her",
    # 씬 6: 빈티지 베스파 거리
    "the wind caught her jacket and hair at the same moment she turned to look down the empty Mediterranean street, one hand lifting to hold her collar",
    # 씬 7: 수영장 엣지
    "she glanced back over her shoulder at the sound of water, body still angled toward the pool, the turquoise light making shifting patterns on her face",
    # 씬 8: 해안 돌담
    "she was watching a distant sailboat when the moment arrived — one knee drawn up on the warm stone, arms loosely wrapped, gaze on the horizon",
    # 씬 9: 옥상 선셋
    "just as the sun dipped behind the roofline she looked directly at the camera — surprised but at ease, the warm afterglow lighting her from one side",
    # 씬 10: 카페 테라스 골목
    "she set down her espresso and looked out toward the cobblestone alley, one elbow on the marble table, the golden hour stretching long across the pavement",
]

LENS_POOL = [
    "85mm f/1.8",
    "50mm f/1.4",
    "70mm f/2",
    "35mm f/2",
    "85mm f/2",
    "105mm f/2.8",
    "50mm f/2",
    "70-200mm at 85mm f/2.8",
]

APERTURE_POOL = [
    "f/2.8 — background softly blurred",
    "f/2 — subject razor-sharp, background dissolves into color",
    "f/4 — gentle background separation, some environment visible",
    "f/2.8 — sea horizon melting into soft bokeh",
    "f/2 — stone wall soft behind, model crisp",
    "f/5.6 — ancient ruins sharp in background for context",
    "f/2.8 — pool water blurred into abstract turquoise",
    "f/3.5 — architectural details partially visible",
]

FILM_POOL = [
    "Kodak Portra 400 — warm golden skin tones, soft greens, rich shadows",
    "Kodak Portra 160 — refined subtle grain, warm neutral skin, elevated tones",
    "Fuji Pro 400H — slightly cooler whites, creamy skin, delicate grain",
    "Kodak Ektar 100 — vivid blues, warm stone, fine almost invisible grain",
    "Kodak Portra 800 — grainier texture, warm street tones, moody depth",
    "Fuji Velvia 50 — saturated blues and greens, rich warm shadows",
]

FRAMING_POOL = [
    "Full body shot, model placed in right third of frame, leading lines from architecture toward subject",
    "Medium shot from waist up, model centered with environment breathing around her",
    "Full body, model sitting on stone with legs visible, left third of frame",
    "Medium close-up, face and torso filling upper frame, environment hinting below",
    "Full body, model leaning on stone, low angle looking up slightly",
    "Medium full shot, model standing near architecture, wind catching outfit",
    "Three-quarter shot, model at slight angle to camera, asymmetric composition",
    "Full body, model walking away then turning back, caught mid-movement",
]

LIGHTING_POOL = [
    "Late afternoon golden hour from the right — warm, directional, long shadows",
    "Overcast Mediterranean afternoon — soft diffused light, even exposure, subtle warmth",
    "Golden hour backlight from behind — warm rim light on hair edges, fill from water reflection",
    "Strong midday sun from above-left — sharp shadows, bright fill from white walls",
    "Soft indirect afternoon bounced from white plaster — gentle, flattering, no harsh shadows",
    "Blue-hour dusk — warm artificial light from restaurant mixing with cool sky",
    "Coastal afternoon haze — slightly diffused warm light, faint ocean blue reflections",
    "Dappled light through cypress trees — alternating warm patches and cool leaf shadow",
]


# ============================================================
# 레퍼런스 이미지 목록 (MOOD_DIR 내 jpg 파일)
# ============================================================
def get_ref_images() -> list:
    """MOOD_DIR의 jpg 파일 목록 반환."""
    if not MOOD_DIR.exists():
        return []
    return sorted(MOOD_DIR.glob("*.jpg"))


# ============================================================
# VLM 레퍼런스 분석 (색감 enrich용)
# ============================================================
def analyze_ref(ref_path: Path) -> dict:
    """VLM으로 레퍼런스 이미지의 color grading 추출."""
    try:
        client = genai.Client(api_key=_get_next_api_key())
        img = Image.open(ref_path).convert("RGB")
        img.thumbnail((1024, 1024), Image.LANCZOS)

        prompt = """Analyze this fashion photograph for image generation reference. Extract:
{
  "color_grading": "describe color grading in detail (warmth, saturation, contrast, film look, tonal quality)",
  "lighting_quality": "describe the light — direction, hardness, color, special qualities",
  "atmosphere": "one evocative sentence describing the emotional atmosphere",
  "key_texture": "what textures are most visually prominent"
}
Respond ONLY with valid JSON, no markdown."""

        response = client.models.generate_content(
            model=VISION_MODEL,
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part(text=prompt), _pil_to_part(img)],
                )
            ],
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_modalities=["TEXT"],
            ),
        )
        text = response.text.strip().replace("```json", "").replace("```", "").strip()
        text = re.sub(r",\s*([}\]])", r"\1", text)
        return json.loads(text)
    except Exception as e:
        print(f"  [VLM WARN] {ref_path.name}: {e}")
        return {}


# ============================================================
# 단일 이미지 생성
# ============================================================
def generate_one(task_id: int, prompt: str, sid: str) -> dict:
    """Gemini로 이미지 1장 생성. 3회 재시도."""
    client = genai.Client(api_key=_get_next_api_key())
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=IMAGE_MODEL,
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part(text=prompt)],
                    )
                ],
                config=types.GenerateContentConfig(
                    temperature=TEMPERATURE,
                    response_modalities=["IMAGE", "TEXT"],
                    image_config=types.ImageConfig(aspect_ratio=ASPECT_RATIO),
                ),
            )
            for part in response.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    img = Image.open(io.BytesIO(part.inline_data.data)).convert("RGB")
                    out_path = OUTPUT_DIR / f"{sid}_gemini.png"
                    img.save(out_path, "PNG")
                    print(f"  [OK] #{task_id:02d} {sid}: {img.size[0]}x{img.size[1]}")
                    return {
                        "task_id": task_id,
                        "sid": sid,
                        "model": "gemini",
                        "status": "ok",
                        "size": f"{img.size[0]}x{img.size[1]}",
                    }
            # 이미지 파트 없음
            if attempt < 2:
                time.sleep(5)
                continue
            print(f"  [NO_IMG] #{task_id:02d} {sid}: no image in response")
            return {
                "task_id": task_id,
                "sid": sid,
                "model": "gemini",
                "status": "no_image",
            }
        except Exception as e:
            if attempt < 2:
                time.sleep((attempt + 1) * 5)
                continue
            print(f"  [FAIL] #{task_id:02d} {sid}: {e}")
            return {
                "task_id": task_id,
                "sid": sid,
                "model": "gemini",
                "status": "error",
                "error": str(e),
            }


# ============================================================
# 메인
# ============================================================
def main():
    dna = load_dna(BRAND)
    ref_images = get_ref_images()

    print("=" * 60)
    print(f"{dna['brand']} WJ Category — 50-Image Bulk Test")
    print(f"Season: {dna['season']}")
    print(f"Target: {TOTAL_IMAGES} images | Workers: {MAX_WORKERS}")
    print(f"Refs available: {len(ref_images)}")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 60)

    # ----------------------------------------------------------
    # Phase 1: VLM 레퍼런스 분석 (최대 10장 병렬)
    # ----------------------------------------------------------
    print("\n[PHASE 1] VLM reference analysis...")
    ref_analyses = {}

    # 최대 10개 레퍼런스 분석
    refs_to_analyze = ref_images[:10] if ref_images else []
    if refs_to_analyze:
        with ThreadPoolExecutor(max_workers=3) as ex:
            futures = {ex.submit(analyze_ref, r): r for r in refs_to_analyze}
            for f in as_completed(futures):
                ref_path = futures[f]
                analysis = f.result()
                if analysis:
                    ref_analyses[ref_path.name] = analysis
                    print(
                        f"  [VLM] {ref_path.name}: {analysis.get('atmosphere', '')[:60]}"
                    )
    else:
        print("  [WARN] MOOD_DIR not found or empty — skipping VLM enrichment")

    # ----------------------------------------------------------
    # Phase 2: 50개 프롬프트 빌드 (randomized)
    # ----------------------------------------------------------
    print("\n[PHASE 2] Building 50 randomized prompts...")
    tasks = []  # list of (task_id, sid, prompt)

    ref_keys = list(ref_analyses.keys())

    for i in range(TOTAL_IMAGES):
        task_id = i + 1
        sid = f"BULK_{task_id:03d}"

        # 카메라 세팅 랜덤
        lens = random.choice(LENS_POOL)
        aperture = random.choice(APERTURE_POOL)
        film = random.choice(FILM_POOL)
        framing = random.choice(FRAMING_POOL)
        lighting_desc = random.choice(LIGHTING_POOL)

        # 씬/모먼트 — 10개 순환 (다양성 보장)
        moment = MOMENTS_POOL[i % len(MOMENTS_POOL)]

        # 기본 에디토리얼 프롬프트 (DNA 기반)
        base_prompt = build_full_editorial_prompt(
            dna,
            CATEGORY,
            moment=moment,
            lens=lens,
            aperture=aperture,
            film=film,
            framing=framing,
            lighting_desc=lighting_desc,
        )

        # 레퍼런스 color grading enrich (있으면)
        if ref_keys:
            ref_key = ref_keys[i % len(ref_keys)]
            ref_data = ref_analyses[ref_key]
            color_grading = ref_data.get(
                "color_grading",
                "warm Kodak Portra film tones, organic grain, rich shadow depth",
            )
            atmosphere = ref_data.get(
                "atmosphere", "quiet luxury, unhurried Mediterranean afternoon"
            )
            enriched_prompt = (
                base_prompt
                + f"\n\nCOLOR GRADING REFERENCE: {color_grading}."
                + f"\nATMOSPHERE: {atmosphere}."
            )
        else:
            enriched_prompt = (
                base_prompt
                + "\n\nCOLOR GRADING REFERENCE: warm Kodak Portra 400 tones, analog film grain, rich warm shadows."
                + "\nATMOSPHERE: quiet luxury, unhurried Mediterranean afternoon light."
            )

        # 프롬프트 파일 저장
        prompt_path = OUTPUT_DIR / f"{sid}_prompt.txt"
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(f"=== BULK TEST #{task_id:03d} ===\n")
            f.write(f"Moment: {moment}\n")
            f.write(f"Lens: {lens} | Aperture: {aperture}\n")
            f.write(f"Film: {film}\n")
            f.write(f"Framing: {framing}\n")
            f.write(f"Lighting: {lighting_desc}\n\n")
            f.write("=== FULL PROMPT ===\n")
            f.write(enriched_prompt)

        tasks.append((task_id, sid, enriched_prompt))

    print(f"  {len(tasks)} prompts built")

    # ----------------------------------------------------------
    # Phase 3: 병렬 생성 (max_workers=5)
    # ----------------------------------------------------------
    print(f"\n[PHASE 3] Generating {TOTAL_IMAGES} images (workers={MAX_WORKERS})...")
    start_time = time.time()
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {
            ex.submit(generate_one, task_id, prompt, sid): (task_id, sid)
            for task_id, sid, prompt in tasks
        }
        for f in as_completed(futures):
            results.append(f.result())

    elapsed = time.time() - start_time

    # ----------------------------------------------------------
    # 결과 집계
    # ----------------------------------------------------------
    ok_count = sum(1 for r in results if r["status"] == "ok")
    no_image_count = sum(1 for r in results if r["status"] == "no_image")
    error_count = sum(1 for r in results if r["status"] == "error")
    fail_count = no_image_count + error_count

    success_rate = ok_count / TOTAL_IMAGES * 100
    fail_rate = fail_count / TOTAL_IMAGES * 100

    # 실패 목록
    failures = [r for r in results if r["status"] != "ok"]

    # config.json 저장
    config = {
        "brand": BRAND,
        "season": dna["season"],
        "category": CATEGORY,
        "strategy": "DNA-auto prompt-only (VLM color enrich + weighted random DNA)",
        "model": IMAGE_MODEL,
        "aspect_ratio": ASPECT_RATIO,
        "temperature": TEMPERATURE,
        "total_target": TOTAL_IMAGES,
        "workers": MAX_WORKERS,
        "refs_analyzed": len(ref_analyses),
        "elapsed_seconds": round(elapsed, 1),
        "success": ok_count,
        "no_image": no_image_count,
        "error": error_count,
        "success_rate_pct": round(success_rate, 1),
        "failure_rate_pct": round(fail_rate, 1),
        "failures": failures,
        "results": sorted(results, key=lambda r: r["task_id"]),
    }

    config_path = OUTPUT_DIR / "config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    # ----------------------------------------------------------
    # 요약 출력
    # ----------------------------------------------------------
    print("\n" + "=" * 60)
    print(f"BULK TEST COMPLETE")
    print(f"  Total target : {TOTAL_IMAGES}")
    print(f"  Success      : {ok_count} ({success_rate:.1f}%)")
    print(f"  No image     : {no_image_count}")
    print(f"  Error        : {error_count}")
    print(f"  Failure rate : {fail_rate:.1f}%")
    print(f"  Elapsed      : {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"  Output dir   : {OUTPUT_DIR}")
    print(f"  Config       : {config_path}")
    if failures:
        print(f"\n  Failed tasks:")
        for r in failures:
            print(
                f"    #{r['task_id']:03d} {r['sid']}: {r['status']} — {r.get('error', '')[:80]}"
            )
    print("=" * 60)


if __name__ == "__main__":
    main()
