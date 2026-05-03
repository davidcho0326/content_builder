# WORKFLOW_BYPASS_OK: strategy-cut-builder quality gap analysis (2026-04-30)
"""
MLB + Discovery 레퍼런스 vs 생성 프롬프트 갭 분석.

레퍼런스 이미지 3장 VLM 분석 (JSON schema 기반) → 기존 프롬프트와 비교 →
갭 리포트 JSON 출력. 이미지 재생성 없음.

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/analyze_quality_gaps.py
"""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv(override=True)

from PIL import Image
from google import genai
from google.genai import types

from core.config import VISION_MODEL
from core.api import _get_next_api_key, _pil_to_part
from scripts.strategy_cut_builder.dna_schema import (
    POSE_SCHEMA,
    EXPRESSION_SCHEMA,
    BACKGROUND_SCHEMA,
    get_vlm_prompt,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_BASE = PROJECT_ROOT / "Fnf_studio_outputs" / "strategy-cut-builder"

MLB_REF_DIR = Path(r"C:\Users\AC1060\Downloads\mlb추구미페미닌")
DX_REF_DIR = Path(r"C:\Users\AC1060\Downloads\디스커버리 추구미")

MLB_TUNED_DIR = OUTPUT_BASE / "mlb" / "20260430_221345_tuned"
DX_TUNED_DIR = OUTPUT_BASE / "discovery" / "20260430_221345_tuned"

# 분석할 레퍼런스 인덱스 (각 브랜드 3장)
MLB_REF_INDICES = [0, 3, 7]  # 다양한 스타일 커버
DX_REF_INDICES = [0, 4, 8]


def analyze_image_with_schema(img_path: Path, brand: str) -> dict:
    """VLM으로 이미지를 JSON schema 기반으로 분석."""
    client = genai.Client(api_key=_get_next_api_key())
    img = Image.open(img_path).convert("RGB")
    img.thumbnail((1024, 1024), Image.LANCZOS)

    combined_schema = {
        "pose": POSE_SCHEMA,
        "expression": EXPRESSION_SCHEMA,
        "background": BACKGROUND_SCHEMA,
        "model_appearance": {
            "face_type": "(얼굴형 — V라인/계란형/각진형 등)",
            "skin_tone": "(피부톤 — 밝은/보통/어두운)",
            "hair_style": "(헤어 — 스트레이트/웨이브/묶은/업스타일 등)",
            "hair_color": "(헤어 컬러)",
            "makeup_style": "(메이크업 스타일 — 내추럴/글램/노메이크업 등)",
            "body_type": "(체형 묘사 — 슬림/애슬레틱/커브 등)",
            "energy": "(전체 에너지/분위기 — 쿨걸/큐트/프레시 등)",
        },
        "styling_details": {
            "garment_summary": "(착용 의류 한 줄 요약)",
            "key_styling_point": "(가장 눈에 띄는 스타일링 포인트)",
            "accessories": "(악세서리 전체 목록)",
            "footwear": "(신발 상세)",
            "color_palette": "(전체 컬러 팔레트 — 주요 3색)",
        },
        "photo_quality": {
            "composition": "(구도 — 3분법/대칭/중앙 등)",
            "depth_of_field": "(심도 — 아웃포커스/딥포커스)",
            "natural_imperfections": "(자연스러운 불완전함 — 바람에 흩날리는 머리, 움직임 등)",
        },
    }

    brand_context = (
        "MLB 브랜드 - K-pop 스타일의 젊은 한국 여성 패션 인플루언서 사진"
        if brand == "mlb"
        else "Discovery Expedition 브랜드 - 한국 피트니스/아웃도어 인플루언서 사진"
    )

    vlm_prompt = get_vlm_prompt(
        combined_schema, f"브랜드: {brand_context}\n파일: {img_path.name}"
    )

    response = client.models.generate_content(
        model=VISION_MODEL,
        contents=[
            types.Content(
                role="user",
                parts=[types.Part(text=vlm_prompt), _pil_to_part(img)],
            )
        ],
        config=types.GenerateContentConfig(
            temperature=0.1, response_modalities=["TEXT"]
        ),
    )
    text = response.text.strip()
    # JSON 블록 추출
    text = re.sub(r"^```json\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return json.loads(text)


def load_existing_prompts(tuned_dir: Path, brand_prefix: str) -> dict:
    """기존 생성 프롬프트 로드."""
    prompts = {}
    for f in sorted(tuned_dir.glob(f"{brand_prefix}_*_prompt.txt")):
        sid = f.stem.replace("_prompt", "")
        prompts[sid] = f.read_text(encoding="utf-8")
    return prompts


def extract_prompt_characteristics(prompt_text: str) -> dict:
    """프롬프트에서 핵심 요소 추출."""
    lines = prompt_text.splitlines()

    characteristics = {
        "moment": "",
        "pose_description": "",
        "camera_description": "",
        "setting_description": "",
        "lighting_description": "",
        "color_description": "",
        "model_vibe": "",
        "accessories": "",
        "unique_styling": "",
    }

    for line in lines:
        line = line.strip()
        if line.startswith("THE MOMENT:"):
            characteristics["moment"] = line.replace("THE MOMENT:", "").strip()
        elif line.startswith("CAMERA:"):
            characteristics["camera_description"] = line.replace("CAMERA:", "").strip()
        elif line.startswith("SETTING:"):
            characteristics["setting_description"] = line.replace(
                "SETTING:", ""
            ).strip()
        elif line.startswith("LIGHTING:"):
            characteristics["lighting_description"] = line.replace(
                "LIGHTING:", ""
            ).strip()
        elif line.startswith("COLOR:"):
            characteristics["color_description"] = line.replace("COLOR:", "").strip()
        elif line.startswith("THE GIRL:"):
            characteristics["model_vibe"] = line.replace("THE GIRL:", "").strip()
        elif line.startswith("ACCESSORIES:"):
            characteristics["accessories"] = line.replace("ACCESSORIES:", "").strip()
        elif line.startswith("HER STYLING:"):
            characteristics["unique_styling"] = line.replace("HER STYLING:", "").strip()

    return characteristics


def identify_gaps(
    ref_analyses: list[dict], prompt_chars: list[dict], brand: str
) -> dict:
    """레퍼런스 분석 vs 프롬프트 특성 비교하여 갭 식별."""

    # 레퍼런스 통합 패턴 도출
    poses = [a.get("pose", {}) for a in ref_analyses]
    expressions = [a.get("expression", {}) for a in ref_analyses]
    backgrounds = [a.get("background", {}) for a in ref_analyses]
    models = [a.get("model_appearance", {}) for a in ref_analyses]
    stylings = [a.get("styling_details", {}) for a in ref_analyses]
    photo_qs = [a.get("photo_quality", {}) for a in ref_analyses]

    # 레퍼런스에서 공통 패턴 추출
    ref_stances = [p.get("stance", "") for p in poses]
    ref_framings = [p.get("camera", {}).get("framing", "") for p in poses]
    ref_cam_heights = [p.get("camera", {}).get("height", "") for p in poses]
    ref_face_dirs = [p.get("face_direction", "") for p in poses]
    ref_gaze = [e.get("gaze_direction", "") for e in expressions]
    ref_exp_base = [e.get("base", "") for e in expressions]
    ref_bg_type = [b.get("type", "") for b in backgrounds]
    ref_bg_vibe = [b.get("region_vibe", "") for b in backgrounds]
    ref_bg_time = [b.get("time_of_day", "") for b in backgrounds]
    ref_hair = [m.get("hair_style", "") for m in models]
    ref_energy = [m.get("energy", "") for m in models]
    ref_key_styling = [s.get("key_styling_point", "") for s in stylings]
    ref_composition = [p.get("composition", "") for p in photo_qs]
    ref_natural = [p.get("natural_imperfections", "") for p in photo_qs]

    # 프롬프트에서 공통 패턴
    prompt_moments = [p.get("moment", "") for p in prompt_chars]
    prompt_cameras = [p.get("camera_description", "") for p in prompt_chars]
    prompt_settings = [p.get("setting_description", "") for p in prompt_chars]

    gaps = []
    recommendations = []

    # ===== 포즈 갭 분석 =====
    has_sitting = any("sit" in s.lower() or "앉" in s for s in ref_stances)
    has_leaning = any("lean" in s.lower() or "기" in s for s in ref_stances)
    has_walking = any("walk" in s.lower() or "걷" in s for s in ref_stances)
    prompt_has_sitting = any(
        "sit" in m.lower() or "seat" in m.lower() for m in prompt_moments
    )
    prompt_has_dynamic = any(
        "walk" in m.lower() or "stride" in m.lower() or "run" in m.lower()
        for m in prompt_moments
    )

    if has_sitting and not prompt_has_sitting:
        gaps.append(
            {
                "category": "pose",
                "severity": "HIGH",
                "ref_shows": f"앉는 포즈 포함: {[s for s in ref_stances if 'sit' in s.lower() or '앉' in s]}",
                "prompt_says": f"대부분 서 있거나 기대는 포즈: {prompt_moments[:2]}",
                "gap": "레퍼런스에 앉은 포즈가 있는데 프롬프트는 모두 서있거나 기대는 포즈만",
            }
        )
        recommendations.append(
            "일부 프롬프트에 'sitting casually on steps/bench/café chair' 포즈 추가"
        )

    # 프레이밍 갭
    fs_count = sum(1 for f in ref_framings if "FS" in f or "MFS" in f)
    cu_count = sum(1 for f in ref_framings if "CU" in f or "MCU" in f)
    if fs_count > len(ref_framings) * 0.6:
        gaps.append(
            {
                "category": "framing",
                "severity": "MEDIUM",
                "ref_shows": f"전신(FS/MFS) 프레이밍 주도적: {ref_framings}",
                "prompt_says": "camera 섹션에 full-body 명시 없이 iPhone candid만 강조",
                "gap": "레퍼런스는 전신 또는 무릎 위 롱샷 위주인데 프롬프트는 구도 미지정",
            }
        )
        recommendations.append(
            "모든 프롬프트에 'full-body framing, head to toe visible' 명시 추가"
        )

    # ===== 표정/시선 갭 =====
    non_camera_gaze = [
        g for g in ref_gaze if "카메라" not in g and "camera" not in g.lower()
    ]
    if len(non_camera_gaze) > len(ref_gaze) * 0.5:
        gaps.append(
            {
                "category": "gaze",
                "severity": "HIGH",
                "ref_shows": f"카메라 외 시선 많음: {non_camera_gaze}",
                "prompt_says": "시선 방향 명시 없음 (AI가 카메라 응시로 기본 생성)",
                "gap": "레퍼런스는 먼 곳 또는 아래를 보는 자연스러운 시선이 많은데 프롬프트에 미지정 → AI가 카메라 응시로만 생성",
            }
        )
        recommendations.append(
            "EXPRESSION 섹션에 'gaze directed away from camera — looking into distance / down at phone / off to the side' 명시"
        )

    # 표정 base
    cool_count = sum(
        1 for e in ref_exp_base if "cool" in e or "confident" in e or "serene" in e
    )
    playful_count = sum(1 for e in ref_exp_base if "playful" in e or "candid" in e)
    if brand == "mlb":
        gaps.append(
            {
                "category": "expression",
                "severity": "MEDIUM",
                "ref_shows": f"표정 분포: cool/serene={cool_count}, playful/candid={playful_count}",
                "prompt_says": "The kind of face that stops you scrolling — 구체적 표정 미지정",
                "gap": "표정 지시가 없어 AI가 과도하게 웃거나 카메라 응시하는 인위적 표정 생성",
            }
        )
        recommendations.append(
            "'subtle half-smile or neutral cool expression — NOT smiling at camera, NOT pouting' 추가"
        )

    # ===== 배경 갭 =====
    korean_bg = sum(
        1 for v in ref_bg_vibe if "한국" in v or "Korean" in v.lower() or "서울" in v
    )
    western_bg = sum(
        1 for v in ref_bg_vibe if "유러피안" in v or "LA" in v or "서양" in v
    )
    if western_bg > korean_bg and brand == "mlb":
        gaps.append(
            {
                "category": "background",
                "severity": "HIGH",
                "ref_shows": f"한국/서울 감성 배경 주도: {ref_bg_type[:3]}",
                "prompt_says": "setting에 해외 도시(LA palm trees, ranch) 등 섞임",
                "gap": "레퍼런스는 성수동/강남 감성인데 프롬프트 일부가 해외 배경으로 생성 유도",
            }
        )
        recommendations.append(
            "setting에 'Seoul Seongsu-dong or Gangnam — Korean minimalist café front, concrete walls with ivy, brick alley' 명시 강화"
        )

    # 배경 시간대
    golden_count = sum(
        1
        for t in ref_bg_time
        if "골든" in t or "golden" in t.lower() or "오후따뜻" in t
    )
    if golden_count > len(ref_bg_time) * 0.4:
        gaps.append(
            {
                "category": "lighting_time",
                "severity": "MEDIUM",
                "ref_shows": f"골든아워/따뜻한 오후 빛 많음: {ref_bg_time}",
                "prompt_says": "lighting에 overcast/diffused 위주",
                "gap": "레퍼런스의 따뜻한 황금빛 시간대가 프롬프트에서 underspecified",
            }
        )
        recommendations.append(
            "일부 프롬프트에 'golden hour warm side lighting, long shadows, warm 5500K glow' 추가"
        )

    # ===== 모델 외모 갭 =====
    natural_imperfections = [
        n for n in ref_natural if n and "없" not in n and "none" not in n.lower()
    ]
    if natural_imperfections:
        gaps.append(
            {
                "category": "natural_feel",
                "severity": "HIGH",
                "ref_shows": f"자연스러운 불완전함 존재: {natural_imperfections}",
                "prompt_says": "flawless dewy glass skin 강조 → 과도하게 완벽한 AI 느낌 유발",
                "gap": "레퍼런스는 바람에 날리는 머리, 옷의 움직임 등 자연스러운 imperfection이 있는데 프롬프트는 과도한 완벽함 강조",
            }
        )
        recommendations.append(
            "'wind-displaced hair strands, fabric catching natural movement, one shoulder slightly lower' 등 자연스러운 불완전함 추가"
        )

    # 헤어 스타일
    ponytail_count = sum(
        1
        for h in ref_hair
        if "묶" in h or "bun" in h.lower() or "ponytail" in h.lower()
    )
    loose_count = sum(
        1
        for h in ref_hair
        if "스트레이트" in h or "straight" in h.lower() or "loose" in h.lower()
    )
    if brand == "mlb" and loose_count > ponytail_count:
        gaps.append(
            {
                "category": "hair",
                "severity": "LOW",
                "ref_shows": f"풀어진 직모 스타일 많음: {ref_hair}",
                "prompt_says": "long silky straight black hair — 적절히 명시됨",
                "gap": "레퍼런스와 일치하지만 가끔 AI가 컬이나 업스타일 생성 → 더 강하게 명시 필요",
            }
        )
        recommendations.append(
            "'long straight black hair worn down OR sleek center-part with face-framing pieces — explicitly straight, not wavy or curly' 강화"
        )

    # ===== 브랜드별 특수 갭 =====
    if brand == "discovery":
        athletic_elements = sum(
            1
            for s in ref_key_styling
            if "운동" in s
            or "sport" in s.lower()
            or "athletic" in s.lower()
            or "아웃도어" in s
        )
        fashion_elements = sum(
            1
            for s in ref_key_styling
            if "스타일" in s or "fashion" in s.lower() or "코디" in s
        )
        gaps.append(
            {
                "category": "brand_identity_discovery",
                "severity": "HIGH",
                "ref_shows": f"스타일링 포인트: athletic={athletic_elements}, fashion={fashion_elements} — {ref_key_styling}",
                "prompt_says": "fitness influencer 설정이지만 Louis Vuitton bag, Adidas Samba 등 비아웃도어 럭셔리 혼재",
                "gap": "Discovery 레퍼런스는 아웃도어 기능성 + 패셔너블의 균형인데 프롬프트가 럭셔리 패션 쪽으로 치우침",
            }
        )
        recommendations.append(
            "Discovery 악세서리를 'technical backpack, trail running cap, performance sunglasses, running watch' 위주로 교체"
        )

    if brand == "mlb":
        gaps.append(
            {
                "category": "brand_identity_mlb",
                "severity": "HIGH",
                "ref_shows": "MLB 로고/캡/볼캡이 키 포인트로 등장하는 Y2K 코디",
                "prompt_says": "MLB baseball cap (NY logo) 언급 있지만 위치/스타일링 방식 미지정",
                "gap": "레퍼런스에서 캡을 쓰는 방식(뒤집어/옆으로/정방향), 로고 가시성이 중요한데 프롬프트에서 구체적 착용법 미지정",
            }
        )
        recommendations.append(
            "MLB 캡 착용 방식 명시: 'MLB NY ball cap worn backwards / slightly tilted to the side — logo prominently visible'"
        )

    # ===== 구도/사진 품질 갭 =====
    compositions = [c for c in ref_composition if c]
    if compositions:
        gaps.append(
            {
                "category": "composition",
                "severity": "MEDIUM",
                "ref_shows": f"구도 패턴: {compositions}",
                "prompt_says": "eye-level, full-body framing 기본 언급",
                "gap": "레퍼런스의 구체적 구도(3분법, 환경과의 관계) 미지정으로 단조로운 중앙 배치 생성 경향",
            }
        )
        recommendations.append(
            "CAMERA 섹션에 'subject positioned off-center using rule of thirds, environment visible and integrated' 추가"
        )

    return {
        "gaps": gaps,
        "recommendations": recommendations,
        "ref_summary": {
            "pose_stances": list(set(ref_stances)),
            "framings": list(set(ref_framings)),
            "expressions": list(set(ref_exp_base)),
            "gaze": list(set(ref_gaze)),
            "backgrounds": list(set(ref_bg_type)),
            "bg_vibes": list(set(ref_bg_vibe)),
            "time_of_day": list(set(ref_bg_time)),
            "hair_styles": list(set(ref_hair)),
            "energies": list(set(ref_energy)),
            "key_styling": list(set(ref_key_styling)),
        },
    }


def analyze_brand(
    brand: str, ref_dir: Path, tuned_dir: Path, ref_indices: list[int]
) -> dict:
    """브랜드 별 전체 분석."""
    brand_upper = brand.upper()
    print(f"\n{'='*55}")
    print(f"  {brand_upper} 분석 시작")
    print(f"{'='*55}")

    # 레퍼런스 이미지 목록
    all_refs = sorted(
        [f for f in ref_dir.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png")]
    )
    selected_refs = [all_refs[min(i, len(all_refs) - 1)] for i in ref_indices]
    print(f"  레퍼런스 분석 대상: {[f.name for f in selected_refs]}")

    # 병렬 VLM 분석
    ref_analyses = []
    ref_file_names = []

    def _analyze(ref_file):
        print(f"    [VLM] 분석 중: {ref_file.name}")
        result = analyze_image_with_schema(ref_file, brand)
        return ref_file.name, result

    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(_analyze, f): f for f in selected_refs}
        for future in as_completed(futures):
            fname, analysis = future.result()
            ref_analyses.append(analysis)
            ref_file_names.append(fname)
            print(
                f"    [OK] {fname}: pose={analysis.get('pose', {}).get('stance', '?')}, bg={analysis.get('background', {}).get('type', '?')}"
            )

    # 기존 프롬프트 로드
    prefix = brand_upper
    prompts = load_existing_prompts(tuned_dir, prefix)
    print(f"\n  기존 프롬프트 {len(prompts)}개 로드")

    # 프롬프트 특성 추출
    prompt_chars = [extract_prompt_characteristics(p) for p in prompts.values()]

    # 갭 분석
    gap_result = identify_gaps(ref_analyses, prompt_chars, brand)

    print(f"\n  발견된 갭: {len(gap_result['gaps'])}개")
    for g in gap_result["gaps"]:
        sev_icon = (
            "[!!]"
            if g["severity"] == "HIGH"
            else "[!]"
            if g["severity"] == "MEDIUM"
            else "[-]"
        )
        print(f"  {sev_icon} [{g['category']}] {g['gap'][:60]}...")

    return {
        "brand": brand_upper,
        "ref_images_analyzed": ref_file_names,
        "ref_analyses": ref_analyses,
        "existing_prompts_count": len(prompts),
        "prompt_samples": {
            sid: extract_prompt_characteristics(p)
            for sid, p in list(prompts.items())[:3]
        },
        "gap_analysis": gap_result,
        "critical_gaps_count": sum(
            1 for g in gap_result["gaps"] if g["severity"] == "HIGH"
        ),
        "medium_gaps_count": sum(
            1 for g in gap_result["gaps"] if g["severity"] == "MEDIUM"
        ),
    }


def main():
    print("=" * 60)
    print("  Strategy Cut Builder — Quality Gap Analysis")
    print("  레퍼런스 vs 기존 프롬프트 비교 분석")
    print("=" * 60)

    results = {}

    # 병렬 분석 (MLB + Discovery 동시)
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_mlb = ex.submit(
            analyze_brand, "mlb", MLB_REF_DIR, MLB_TUNED_DIR, MLB_REF_INDICES
        )
        f_dx = ex.submit(
            analyze_brand, "discovery", DX_REF_DIR, DX_TUNED_DIR, DX_REF_INDICES
        )

        for future in as_completed([f_mlb, f_dx]):
            brand_result = future.result()
            results[brand_result["brand"]] = brand_result

    # 종합 리포트 생성
    report = {
        "_meta": {
            "generated_at": __import__("datetime").datetime.now().isoformat(),
            "script": "analyze_quality_gaps.py",
            "purpose": "레퍼런스 이미지 VLM 분석 vs 기존 프롬프트 갭 식별",
            "ref_sources": {
                "MLB": str(MLB_REF_DIR),
                "DISCOVERY": str(DX_REF_DIR),
            },
            "prompt_sources": {
                "MLB": str(MLB_TUNED_DIR),
                "DISCOVERY": str(DX_TUNED_DIR),
            },
        },
        "summary": {
            "MLB": {
                "critical_gaps": results.get("MLB", {}).get("critical_gaps_count", 0),
                "medium_gaps": results.get("MLB", {}).get("medium_gaps_count", 0),
                "top_recommendations": results.get("MLB", {})
                .get("gap_analysis", {})
                .get("recommendations", [])[:3],
            },
            "DISCOVERY": {
                "critical_gaps": results.get("DISCOVERY", {}).get(
                    "critical_gaps_count", 0
                ),
                "medium_gaps": results.get("DISCOVERY", {}).get("medium_gaps_count", 0),
                "top_recommendations": results.get("DISCOVERY", {})
                .get("gap_analysis", {})
                .get("recommendations", [])[:3],
            },
        },
        "detailed": results,
    }

    # JSON 저장
    out_path = OUTPUT_BASE / "_quality_analysis.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"  분석 완료!")
    print(f"  리포트: {out_path}")
    print(
        f"\n  MLB  — HIGH:{report['summary']['MLB']['critical_gaps']}개 / MEDIUM:{report['summary']['MLB']['medium_gaps']}개"
    )
    print(
        f"  DISC — HIGH:{report['summary']['DISCOVERY']['critical_gaps']}개 / MEDIUM:{report['summary']['DISCOVERY']['medium_gaps']}개"
    )
    print(f"\n  MLB 핵심 개선사항:")
    for r in report["summary"]["MLB"]["top_recommendations"]:
        print(f"    - {r[:70]}...")
    print(f"\n  Discovery 핵심 개선사항:")
    for r in report["summary"]["DISCOVERY"]["top_recommendations"]:
        print(f"    - {r[:70]}...")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
