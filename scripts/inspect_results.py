# WORKFLOW_BYPASS_OK: strategy-cut-builder VLM 검수 자동화 (2026-04-30)
"""
전략컷 검수 스크립트 (Step 5) — strategy-inspect 스킬 구현체.

사용법:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/inspect_results.py \
        --folder Fnf_studio_outputs/strategy-cut-builder/duvetica/20260430_204322_dna_auto \
        --brand duvetica

브랜드 DNA 가드레일 7-Gate로 생성 이미지를 자동 검수.
병렬 처리 (max_workers=5), 결과는 폴더 내 validation.json 저장.
"""

import sys
import os
import json
import re
import base64
import io
import argparse
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# 한글 출력
sys.stdout.reconfigure(encoding="utf-8")

# 프로젝트 루트 경로 설정
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from PIL import Image
from core.config import VISION_MODEL
from core.api import _get_next_api_key, _pil_to_part

try:
    from google import genai
    from google.genai import types
except ImportError:
    raise ImportError("google-genai 패키지 필요: uv pip install google-genai")


# ============================================================
# 상수
# ============================================================

# 생성 이미지 확장자
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

# 7-Gate 심각도 매핑
GATE_SEVERITY = {
    "garment_type_match": "major",
    "color_palette": "major",
    "sheen_level": "minor",
    "background_mood": "minor",
    "model_appearance": "critical",
    "editorial_quality": "major",
    "fabric_representation": "minor",
}

# 에디토리얼 품질 통과 기준점
EDITORIAL_QUALITY_THRESHOLD = 6  # 10점 만점 기준


# ============================================================
# DNA 로드
# ============================================================


def load_brand_dna(brand: str) -> dict:
    """브랜드 DNA JSON 로드."""
    brand_lower = brand.lower()
    dna_path = (
        PROJECT_ROOT
        / ".claude"
        / "projects"
        / "strategy-cut-builder"
        / "brand-dna"
        / f"{brand_lower}.json"
    )
    if not dna_path.exists():
        raise FileNotFoundError(f"브랜드 DNA 파일 없음: {dna_path}")
    with open(dna_path, encoding="utf-8") as f:
        return json.load(f)


def build_guardrail_context(dna: dict) -> dict:
    """DNA에서 검수에 필요한 가드레일 정보 추출."""
    guardrails = dna.get("data_driven_guardrails", {})
    marketing = dna.get("marketing_dna", {})
    colors = dna.get("color", {})

    # 전체 허용 컬러 목록 (base + key + accent)
    all_colors = []
    for tier in ("base", "key", "accent"):
        for c in colors.get(tier, {}).get("colors", []):
            all_colors.append(c.get("name", ""))

    # 카테고리별 가드레일 (woven_jacket 기준 fallback)
    wj = guardrails.get("woven_jacket", {})
    setup = guardrails.get("setup", {})

    # 합산 garment_types
    garment_types = []
    for cat_key in guardrails:
        if cat_key.startswith("_"):
            continue
        garment_types.extend(guardrails[cat_key].get("garment_types", []))

    # 배경 무드 키워드
    bg_info = marketing.get("background", {})
    bg_mood_keys = [
        bg_info.get("dominant_pattern", ""),
        bg_info.get("secondary_pattern", ""),
    ]
    bg_forbidden = bg_info.get("brand_rules", {}).get("금지", [])
    bg_preferred = bg_info.get("brand_rules", {}).get("지향", [])

    # 모델 묘사
    model_info = dna.get("model", {})

    # 광택 범위 (전 카테고리 union)
    sheen_min = 5
    sheen_max = 1
    for cat_key in guardrails:
        if cat_key.startswith("_"):
            continue
        attrs = guardrails[cat_key].get("attributes", {})
        sh = attrs.get("sheen", {})
        if sh:
            sheen_min = min(sheen_min, sh.get("min", 1))
            sheen_max = max(sheen_max, sh.get("max", 5))

    # fabric 범위 (전 카테고리 union)
    fabric_min = 5
    fabric_max = 1
    for cat_key in guardrails:
        if cat_key.startswith("_"):
            continue
        attrs = guardrails[cat_key].get("attributes", {})
        fb = attrs.get("fabric", {})
        if fb:
            fabric_min = min(fabric_min, fb.get("min", 1))
            fabric_max = max(fabric_max, fb.get("max", 5))

    return {
        "brand": dna.get("brand", ""),
        "all_colors": all_colors,
        "garment_types": garment_types,
        "sheen_min": sheen_min,
        "sheen_max": sheen_max,
        "fabric_min": fabric_min,
        "fabric_max": fabric_max,
        "bg_mood_keys": bg_mood_keys,
        "bg_forbidden": bg_forbidden,
        "bg_preferred": bg_preferred,
        "model_desc": f"{model_info.get('age_range','')}, {model_info.get('beauty','')}, {model_info.get('expression','')}",
        "setting_locations": dna.get("setting", {}).get("location", []),
    }


# ============================================================
# VLM 검수 프롬프트 (강제 JSON 스키마 방식)
# ============================================================

INSPECT_SCHEMA = {
    "step1_image_analysis": {
        "garment_type_observed": "(의류 유형 — 예: hooded windbreaker jacket)",
        "main_color": "(메인 컬러 이름 + hex 추정)",
        "sheen_level": "(1~5 정수 — 1=풀매트, 5=하이광택)",
        "fabric_feel": "(1~5 정수 — 1=천연프리미엄, 5=헤비테크)",
        "background_description": "(배경 묘사 — 장소, 분위기, 색감)",
        "model_ai_signs": "(AI 징후 — 플라스틱 피부/워터마크/텍스트 왜곡 등. 손가락 왜곡은 검수 제외. 없으면 '없음')",
        "editorial_score": "(1~10 정수 — 화보 퀄리티. 1=SNS 스냅, 10=Vogue 화보)",
    },
    "step2_gate_comparison": {
        "garment_type_match": {
            "verdict": "(PASS or FAIL)",
            "evidence": "(형식: 'GEN:{관찰값}, DNA:{허용목록}')",
        },
        "color_palette": {
            "verdict": "(PASS or FAIL)",
            "evidence": "(형식: 'GEN:{관찰컬러}, DNA:{가장가까운허용컬러}')",
        },
        "sheen_level": {
            "verdict": "(PASS or FAIL)",
            "evidence": "(형식: 'GEN:{관찰값}, RANGE:{min}~{max}')",
        },
        "background_mood": {
            "verdict": "(PASS or FAIL)",
            "evidence": "(형식: 'GEN:{배경묘사}, DNA:{지향패턴}')",
        },
        "model_appearance": {
            "verdict": "(PASS or FAIL)",
            "evidence": "(AI징후 목록. 손가락 왜곡은 무시. 없으면 'AI징후:없음')",
        },
        "editorial_quality": {
            "verdict": "(PASS or FAIL)",
            "evidence": "(형식: 'score:{점수}/10, {판정이유}')",
        },
        "fabric_representation": {
            "verdict": "(PASS or FAIL)",
            "evidence": "(형식: 'GEN:{관찰소재감}, RANGE:{min}~{max}')",
        },
    },
    "step3_summary": {
        "total_pass": "(정수 — PASS 개수/7)",
        "verdict": "(PASS or FAIL)",
        "severity": "(none / minor / major / critical — 가장 높은 실패 심각도)",
        "failed_gates": ["(실패한 gate 이름들. 없으면 빈 배열)"],
        "adjustment_feedback": "(실패 항목별 프롬프트 조정 제안. 모두 PASS면 '조정 불필요')",
    },
}


def build_inspect_prompt(guardrail: dict) -> str:
    """검수 VLM 프롬프트 생성 — 강제 JSON 스키마 방식."""
    schema_str = json.dumps(INSPECT_SCHEMA, ensure_ascii=False, indent=2)

    colors_str = ", ".join(guardrail["all_colors"][:15])  # 너무 길면 상위 15개
    garments_str = ", ".join(guardrail["garment_types"][:10])
    bg_preferred_str = ", ".join(guardrail["bg_preferred"])
    bg_forbidden_str = ", ".join(guardrail["bg_forbidden"])
    locations_str = ", ".join(guardrail["setting_locations"])

    return f"""You are a fashion editorial quality inspector for the brand {guardrail['brand']}.
Inspect this generated image against the brand DNA guardrails below.

=== BRAND DNA GUARDRAILS ===
[Garment Types Allowed]: {garments_str}
[Color Palette Allowed]: {colors_str}
[Sheen Level Range]: {guardrail['sheen_min']}~{guardrail['sheen_max']} (1=full matte, 5=high gloss)
[Fabric Feel Range]: {guardrail['fabric_min']}~{guardrail['fabric_max']} (1=natural premium, 5=heavy tech)
[Background Preferred]: {bg_preferred_str}
[Background Forbidden]: {bg_forbidden_str}
[Setting Locations]: {locations_str}
[Model Description]: {guardrail['model_desc']}
[Editorial Quality Threshold]: score >= {EDITORIAL_QUALITY_THRESHOLD}/10

=== INSPECTION RULES ===
- sheen_level PASS condition: observed value is within [{guardrail['sheen_min']}, {guardrail['sheen_max']}]
- fabric_representation PASS condition: observed value is within [{guardrail['fabric_min']}, {guardrail['fabric_max']}]
- editorial_quality PASS condition: score >= {EDITORIAL_QUALITY_THRESHOLD}
- model_appearance FAIL if: plastic skin, watermark, or text distortion visible. IMPORTANT: finger/hand distortion is EXCLUDED from inspection — do NOT fail for finger issues
- color_palette PASS if observed color is reasonably close to any allowed color name
- background_mood FAIL if forbidden keywords match the background

=== INSTRUCTION ===
Fill in ALL fields in the JSON below. Replace every parenthetical description with actual values.
For step2_gate_comparison, each verdict must be exactly "PASS" or "FAIL".
For step3_summary.verdict: PASS only if ALL 7 gates pass.
For step3_summary.severity: use the highest severity among failed gates
  (critical > major > minor > none).

```json
{schema_str}
```

Output ONLY the filled JSON. No markdown, no explanation."""


# ============================================================
# VLM 호출 (Gemini)
# ============================================================


def call_vlm_inspect(image_path: Path, prompt: str) -> dict:
    """이미지를 VLM으로 검수하고 파싱된 JSON 반환."""
    img = Image.open(image_path)
    api_key = _get_next_api_key()
    client = genai.Client(api_key=api_key)

    image_part = _pil_to_part(img, format="JPEG", quality=85)
    text_part = types.Part(text=prompt)

    response = client.models.generate_content(
        model=VISION_MODEL,
        contents=[types.Content(role="user", parts=[text_part, image_part])],
        config=types.GenerateContentConfig(temperature=0.1),
    )

    raw_text = ""
    if hasattr(response, "text") and response.text:
        raw_text = response.text
    else:
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, "text") and part.text:
                    raw_text += part.text

    # JSON 추출 (코드블록 제거)
    json_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw_text)
    if json_match:
        raw_text = json_match.group(1)

    return json.loads(raw_text.strip())


# ============================================================
# 단일 이미지 검수
# ============================================================


def determine_model_tag(filename: str) -> str:
    """파일명에서 모델 태그 추출 (gemini/gpt/unknown)."""
    name = filename.lower()
    if "gemini" in name:
        return "gemini"
    if "gpt" in name:
        return "gpt"
    if "higgsfield" in name:
        return "higgsfield"
    return "unknown"


def determine_severity_from_gates(criteria: dict) -> str:
    """실패 항목들의 최대 심각도 계산."""
    severity_order = {"none": 0, "minor": 1, "major": 2, "critical": 3}
    max_severity = "none"
    for gate_name, gate_data in criteria.items():
        if isinstance(gate_data, dict) and gate_data.get("verdict") == "FAIL":
            gate_severity = GATE_SEVERITY.get(gate_name, "minor")
            if severity_order[gate_severity] > severity_order[max_severity]:
                max_severity = gate_severity
    return max_severity


def inspect_single_image(
    image_path: Path,
    prompt: str,
    idx: int,
    total: int,
) -> dict:
    """단일 이미지 검수 — ThreadPoolExecutor에서 호출."""
    filename = image_path.name
    print(f"  [{idx}/{total}] 검수 중: {filename}")

    try:
        vlm_result = call_vlm_inspect(image_path, prompt)
    except Exception as e:
        print(f"  [ERROR] {filename}: VLM 호출 실패 — {e}")
        return {
            "image": filename,
            "model": determine_model_tag(filename),
            "verdict": "ERROR",
            "severity": "critical",
            "score": 0,
            "error": str(e),
            "criteria": {},
            "adjustment_feedback": "VLM 호출 오류로 검수 불가 — 재시도 필요",
        }

    # step2 criteria 추출
    step2 = vlm_result.get("step2_gate_comparison", {})
    step3 = vlm_result.get("step3_summary", {})
    step1 = vlm_result.get("step1_image_analysis", {})

    # criteria 정형화
    criteria = {}
    for gate_name in GATE_SEVERITY:
        gate_data = step2.get(gate_name, {})
        if isinstance(gate_data, dict):
            verdict = gate_data.get("verdict", "FAIL").upper()
            evidence = gate_data.get("evidence", "")
            entry = {"verdict": verdict, "evidence": evidence}
            if verdict == "FAIL":
                entry["severity"] = GATE_SEVERITY[gate_name]
            criteria[gate_name] = entry
        else:
            criteria[gate_name] = {
                "verdict": "FAIL",
                "evidence": "파싱 실패",
                "severity": GATE_SEVERITY[gate_name],
            }

    # 총점 계산
    pass_count = sum(1 for g in criteria.values() if g.get("verdict") == "PASS")
    severity = determine_severity_from_gates(criteria)

    # 최종 verdict
    verdict = "PASS" if pass_count == 7 else "FAIL"

    # 실패 항목명 (한국어)
    gate_kr = {
        "garment_type_match": "의류 유형 일치",
        "color_palette": "컬러 팔레트",
        "sheen_level": "광택 수준",
        "background_mood": "배경 무드",
        "model_appearance": "모델 외관",
        "editorial_quality": "에디토리얼 품질",
        "fabric_representation": "소재 표현",
    }
    failed_gates_kr = [
        gate_kr.get(g, g)
        for g in GATE_SEVERITY
        if criteria.get(g, {}).get("verdict") == "FAIL"
    ]

    result = {
        "image": filename,
        "model": determine_model_tag(filename),
        "verdict": verdict,
        "severity": severity,
        "score": pass_count,
        "criteria": criteria,
        "failed_gates": failed_gates_kr,
        "adjustment_feedback": step3.get("adjustment_feedback", ""),
        "step1_analysis": step1,
    }

    status_icon = "PASS" if verdict == "PASS" else f"FAIL({severity})"
    print(f"  [{idx}/{total}] {filename}: {status_icon} ({pass_count}/7)")
    return result


# ============================================================
# 이미지 목록 수집
# ============================================================


def collect_images(folder: Path) -> list[Path]:
    """검수 대상 이미지 수집 (레퍼런스/썸네일 제외)."""
    images = []
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        # 레퍼런스 이미지 (_00_reference 패턴) 제외
        if "_00_reference" in f.name or "reference" in f.name.lower():
            continue
        # 썸네일 제외
        if "thumb_" in f.name:
            continue
        images.append(f)
    return images


# ============================================================
# 검수 결과 출력 (한국어 표)
# ============================================================


def print_summary_table(results: list[dict], brand: str) -> None:
    """검수 결과 한국어 표 출력."""
    print("\n" + "=" * 70)
    print(f"## 검수 결과 — {brand.upper()}")
    print("=" * 70)

    # 표 헤더
    header = f"{'이미지':<30} {'모델':<10} {'판정':<8} {'심각도':<10} {'탈락 항목'}"
    print(header)
    print("-" * 70)

    for r in results:
        if r.get("verdict") == "ERROR":
            print(
                f"{r['image']:<30} {r.get('model',''):<10} ERROR    critical   VLM 오류"
            )
            continue
        verdict = r["verdict"]
        severity = r["severity"] if verdict == "FAIL" else "-"
        failed = ", ".join(r.get("failed_gates", [])) or "-"
        print(
            f"{r['image']:<30} {r.get('model',''):<10} {verdict:<8} {severity:<10} {failed}"
        )

    print("-" * 70)

    total = len(results)
    pass_count = sum(1 for r in results if r.get("verdict") == "PASS")
    fail_minor = sum(
        1
        for r in results
        if r.get("verdict") == "FAIL" and r.get("severity") == "minor"
    )
    fail_major = sum(
        1
        for r in results
        if r.get("verdict") == "FAIL" and r.get("severity") == "major"
    )
    fail_critical = sum(
        1
        for r in results
        if r.get("verdict") in ("FAIL", "ERROR") and r.get("severity") == "critical"
    )

    print(f"\n통과율: {pass_count}/{total} ({pass_count/total*100:.0f}%)")
    print(
        f"PASS: {pass_count}  |  FAIL(minor): {fail_minor}  |  FAIL(major): {fail_major}  |  FAIL(critical): {fail_critical}"
    )

    # 탈락 사유 상세
    failed_items = [r for r in results if r.get("verdict") in ("FAIL", "ERROR")]
    if failed_items:
        print("\n### 탈락 사유")
        for r in failed_items:
            if r.get("verdict") == "ERROR":
                print(f"  - {r['image']}: VLM 오류")
                continue
            for gate_name in GATE_SEVERITY:
                gate_data = r["criteria"].get(gate_name, {})
                if gate_data.get("verdict") == "FAIL":
                    sev = gate_data.get("severity", GATE_SEVERITY[gate_name])
                    evidence = gate_data.get("evidence", "")
                    gate_kr = {
                        "garment_type_match": "의류 유형",
                        "color_palette": "컬러 팔레트",
                        "sheen_level": "광택 수준",
                        "background_mood": "배경 무드",
                        "model_appearance": "모델 외관",
                        "editorial_quality": "에디토리얼 품질",
                        "fabric_representation": "소재 표현",
                    }
                    print(
                        f"  - {r['image']} ({sev}): {gate_kr.get(gate_name, gate_name)} — {evidence}"
                    )

    # 재생성 피드백
    regen_needed = [r for r in results if r.get("severity") in ("major", "critical")]
    if regen_needed:
        print("\n### 재생성 대상 (major/critical 실패)")
        for r in regen_needed:
            feedback = r.get("adjustment_feedback", "")
            if feedback:
                print(f"  - {r['image']}: {feedback}")

    print("=" * 70)


# ============================================================
# 메인
# ============================================================


def inspect_folder(folder: Path, brand: str, max_workers: int = 5) -> dict:
    """폴더 내 이미지 전체 검수 실행."""
    if not folder.exists():
        raise FileNotFoundError(f"폴더 없음: {folder}")

    print(f"\n[검수 시작] 브랜드={brand.upper()}, 폴더={folder.name}")

    # DNA 로드
    dna = load_brand_dna(brand)
    guardrail = build_guardrail_context(dna)
    prompt = build_inspect_prompt(guardrail)

    # 이미지 수집
    images = collect_images(folder)
    if not images:
        raise ValueError(f"검수할 이미지가 없습니다: {folder}")

    print(f"[대상] {len(images)}개 이미지 발견")

    # 병렬 검수 (max_workers=5)
    results = [None] * len(images)
    total = len(images)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(inspect_single_image, img_path, prompt, idx + 1, total): idx
            for idx, img_path in enumerate(images)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                results[idx] = {
                    "image": images[idx].name,
                    "model": determine_model_tag(images[idx].name),
                    "verdict": "ERROR",
                    "severity": "critical",
                    "score": 0,
                    "error": str(e),
                    "criteria": {},
                    "failed_gates": [],
                    "adjustment_feedback": f"처리 오류: {e}",
                }

    # 결과 정리
    pass_count = sum(1 for r in results if r.get("verdict") == "PASS")
    fail_minor = sum(
        1
        for r in results
        if r.get("verdict") == "FAIL" and r.get("severity") == "minor"
    )
    fail_major = sum(
        1
        for r in results
        if r.get("verdict") == "FAIL" and r.get("severity") == "major"
    )
    fail_critical = sum(
        1
        for r in results
        if r.get("verdict") in ("FAIL", "ERROR") and r.get("severity") == "critical"
    )

    summary = {
        "total": total,
        "pass": pass_count,
        "fail_minor": fail_minor,
        "fail_major": fail_major,
        "fail_critical": fail_critical,
        "pass_rate": round(pass_count / total, 2),
    }

    report = {
        "brand": brand.lower(),
        "timestamp": datetime.now().isoformat(),
        "folder": str(folder),
        "guardrail_context": {
            "sheen_range": f"{guardrail['sheen_min']}~{guardrail['sheen_max']}",
            "fabric_range": f"{guardrail['fabric_min']}~{guardrail['fabric_max']}",
            "garment_types_count": len(guardrail["garment_types"]),
            "allowed_colors_count": len(guardrail["all_colors"]),
        },
        "results": results,
        "summary": summary,
    }

    # validation.json 저장
    out_path = folder / "validation.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 한국어 표 출력
    print_summary_table(results, brand)
    print(f"\n[저장] {out_path}")

    return report


def main():
    parser = argparse.ArgumentParser(
        description="전략컷 VLM 검수 스크립트 (Step 5 — strategy-inspect)"
    )
    parser.add_argument(
        "--folder",
        required=True,
        help="검수할 이미지 폴더 경로 (예: Fnf_studio_outputs/strategy-cut-builder/duvetica/20260430_xxx/)",
    )
    parser.add_argument(
        "--brand",
        required=True,
        choices=["duvetica", "mlb", "discovery"],
        help="브랜드 이름",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=5,
        help="병렬 워커 수 (기본 5)",
    )
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.is_absolute():
        folder = PROJECT_ROOT / folder

    report = inspect_folder(folder, args.brand, max_workers=args.workers)

    summary = report["summary"]
    print(
        f"\n[완료] 총 {summary['total']}개 검수 완료 "
        f"— PASS {summary['pass']}개 "
        f"/ FAIL(minor) {summary['fail_minor']}개 "
        f"/ FAIL(major) {summary['fail_major']}개 "
        f"/ FAIL(critical) {summary['fail_critical']}개"
    )


if __name__ == "__main__":
    main()
