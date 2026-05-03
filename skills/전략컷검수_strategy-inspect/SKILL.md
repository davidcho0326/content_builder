---
name: strategy-inspect
description: 생성된 전략컷을 DNA 가드레일 대비 검수. 전략실컷빌더 Step 5.
user-invocable: true
trigger-keywords: ["전략컷 검수", "strategy inspect", "전략컷 품질", "DNA 검수"]
---

# 전략컷 검수 (Strategy Inspect)

> 생성된 이미지를 브랜드 DNA 가드레일과 대비하여 품질 검증한다.
> 실패한 이미지는 프롬프트 조정 피드백과 함께 재생성 루프로 돌아간다.

---

## 절대 규칙

1. **VLM 검수는 항상 Gemini Flash** — `from core.config import VISION_MODEL` 사용
2. **DNA 가드레일 기반 판정** — 감각적 판단이 아닌 정량 기준
3. **재시도 최대 2회** — 3회 실패 시 사용자에게 보고 (3-Strike Rule)
4. **검수 결과 한국어 출력** — `rules/validation-output.md` 형식 준수

---

## 입력

| 입력 | 필수 | 형식 | 예시 |
|------|------|------|------|
| 생성된 이미지 폴더 | O | 경로 | `Fnf_studio_outputs/strategy-cut-builder/duvetica/20260430_*/` |
| 브랜드 DNA JSON | O | JSON 경로 | `.claude/projects/strategy-cut-builder/brand-dna/duvetica.json` |

---

## 출력

| 출력 | 형식 | 위치 |
|------|------|------|
| 이미지별 판정 | JSON | 출력 폴더 내 `validation.json` |
| 검수 결과 표 | 텍스트 | 사용자에게 직접 표시 |
| 프롬프트 조정 피드백 | 텍스트 | 실패 이미지별 (재생성 시 사용) |

---

## 검수 항목 (7-Gate)

| # | 항목 | 영문 | 판정 기준 | 심각도 |
|---|------|------|----------|--------|
| 1 | 의류 유형 일치 | garment_type_match | DNA 가드레일의 garment_types에 포함 | major |
| 2 | 컬러 팔레트 준수 | color_palette | DNA color의 base/key/accent 팔레트 내 | major |
| 3 | 광택 수준 | sheen_level | DNA 가드레일 sheen min~max 범위 내 | minor |
| 4 | 배경 무드 | background_mood | DNA setting의 분위기와 일치 | minor |
| 5 | 모델 외관 | model_appearance | AI 느낌 없음 (플라스틱 피부/이상한 손가락 X) | critical |
| 6 | 에디토리얼 품질 | editorial_quality | 화보 수준 구도/조명/색감 | major |
| 7 | 소재 표현 | fabric_representation | DNA fabric 가드레일과 소재 느낌 일치 | minor |

---

## 판정 체계

| 구분 | 설명 | 조치 |
|------|------|------|
| **PASS** | 7개 항목 모두 통과 | 최종 결과물로 채택 |
| **FAIL (minor)** | minor 항목 1~2개 실패 | 경고 표시, 통과 가능 |
| **FAIL (major)** | major 항목 1개+ 실패 | 재생성 필요 |
| **FAIL (critical)** | critical 항목 실패 | 즉시 재생성 |

---

## VLM 검수 프롬프트 (단계별 강제)

`rules/vlm-inspection.md` 원칙 준수 — 지시만 하지 말고 단계별 출력 강제:

```python
INSPECT_PROMPT = """You are inspecting a generated fashion image against brand DNA guardrails.

[STEP 1] GENERATED IMAGE 분석:
- 의류 유형: ?
- 메인 컬러: ? (hex 추정)
- 광택 수준: 1-5 ?
- 배경 분위기: ?
- 모델 외관: AI 징후 있음/없음 (손가락 수, 피부 질감)
- 에디토리얼 품질: 1-10 ?
- 소재 느낌: ?

[STEP 2] DNA 가드레일 대비:
- garment_type: GEN={?}, DNA_ALLOWED={guardrail.garment_types}
- color: GEN={?}, DNA_PALETTE={top_colors}
- sheen: GEN={?}, DNA_RANGE={min}~{max}
- background: GEN={?}, DNA_SETTING={setting}
- fabric: GEN={?}, DNA_RANGE={min}~{max}

[STEP 3] 항목별 판정:
- garment_type_match: PASS/FAIL (reason: "GEN:?, DNA:?")
- color_palette: PASS/FAIL (reason: "GEN:?, DNA:?")
- sheen_level: PASS/FAIL (reason: "GEN:?, RANGE:?~?")
- background_mood: PASS/FAIL (reason: "GEN:?, DNA:?")
- model_appearance: PASS/FAIL (reason: "AI징후:?")
- editorial_quality: PASS/FAIL (reason: "score:?/10")
- fabric_representation: PASS/FAIL (reason: "GEN:?, DNA:?")

[STEP 4] 종합:
- total_pass: ?/7
- verdict: PASS/FAIL
- severity: none/minor/major/critical
- adjustment_feedback: "프롬프트 조정 제안"

JSON 형식으로 응답."""
```

---

## 재생성 루프

```
검수 실패
    ↓
프롬프트 조정 피드백 생성
    ├── temperature 상승 (1.0 → 1.2)
    ├── 실패 항목 구체성 추가 (컬러 hex 명시 등)
    └── 실패 원인별 키워드 보강
    ↓
/전략컷생성 재실행 (실패 씬만)
    ↓
재검수 (최대 2회)
    ├── PASS → 완료
    └── 2회 실패 → 사용자 보고 (3-Strike)
```

### 프롬프트 조정 전략

| 실패 항목 | 조정 방법 |
|----------|----------|
| 컬러 불일치 | hex 코드 명시: `exactly {hex} color, not {wrong_color}` |
| 광택 과다/부족 | 구체적 소재 지시: `completely matte cotton` or `semi-glossy nylon` |
| 배경 부적합 | 배경 키워드 교체 + 구체적 장소 명시 |
| AI 느낌 | 불완전함 키워드 강화 + `natural skin pores and texture visible` 추가 |
| 에디토리얼 미달 | `high-end fashion editorial for Vogue Italia` 강조 + 구도 키워드 추가 |
| 소재 불일치 | 소재명 직접 명시: `premium Italian nylon, weight=2, semi-matte finish` |
| 의류 유형 오류 | garment_type 직접 명시: `quilted down jacket, NOT puffer coat` |

---

## validation.json 형식

```json
{
  "brand": "duvetica",
  "timestamp": "2026-04-30T15:00:00",
  "results": [
    {
      "image": "scene_01_gemini.png",
      "model": "gemini",
      "verdict": "PASS",
      "severity": "none",
      "score": 7,
      "criteria": {
        "garment_type_match": {"verdict": "PASS", "evidence": "GEN:quilted down jacket, DNA:[down jacket, quilted jacket]"},
        "color_palette": {"verdict": "PASS", "evidence": "GEN:#F5F0E8 ivory, DNA:base[Ivory #F5F0E8]"},
        "sheen_level": {"verdict": "PASS", "evidence": "GEN:2, RANGE:1~3"},
        "background_mood": {"verdict": "PASS", "evidence": "GEN:mediterranean resort, DNA:Mediterranean summer"},
        "model_appearance": {"verdict": "PASS", "evidence": "AI징후:없음, 손가락5개, 피부질감자연"},
        "editorial_quality": {"verdict": "PASS", "evidence": "score:8/10"},
        "fabric_representation": {"verdict": "PASS", "evidence": "GEN:lightweight nylon, DNA:2~3"}
      }
    },
    {
      "image": "scene_02_gpt.png",
      "model": "gpt",
      "verdict": "FAIL",
      "severity": "major",
      "score": 5,
      "criteria": {
        "color_palette": {"verdict": "FAIL", "severity": "major", "evidence": "GEN:#000000 black, DNA:base[Ivory, Stone, Latte]"},
        "sheen_level": {"verdict": "FAIL", "severity": "minor", "evidence": "GEN:4, RANGE:1~3"}
      },
      "adjustment_feedback": "컬러를 ivory/stone/latte 중 하나로 명시. 광택 matte 방향으로 소재 키워드 추가."
    }
  ],
  "summary": {
    "total": 12,
    "pass": 9,
    "fail_minor": 1,
    "fail_major": 2,
    "fail_critical": 0,
    "pass_rate": 0.75
  }
}
```

---

## 검수 결과 출력 형식 (한국어)

```
## 검수 결과

| 이미지 | 모델 | 판정 | 심각도 | 탈락 항목 |
|--------|------|------|--------|----------|
| scene_01_gemini.png | Gemini | PASS | - | - |
| scene_01_gpt.png | GPT | PASS | - | - |
| scene_02_gemini.png | Gemini | FAIL | major | 컬러 팔레트 |
| scene_02_gpt.png | GPT | FAIL | minor | 광택 수준 |

**통과율**: 9/12 (75%)

### 탈락 사유
- scene_02_gemini.png (major): 컬러 불일치 — GEN: 검정, DNA: Ivory/Stone/Latte
- scene_02_gpt.png (minor): 광택 과다 — GEN: 4, 가드레일: 1~3

### 재생성 대상
- scene_02: 컬러 ivory 명시 + 소재 matte cotton 추가
```

---

## 금지 패턴

```python
# FORBIDDEN: 감각적 판단 (정량 기준 없이)
verdict = "이 이미지는 느낌이 좋으니 PASS"

# FORBIDDEN: DNA 가드레일 미참조
if looks_good:
    verdict = "PASS"

# FORBIDDEN: 재시도 횟수 무제한
while not passed:
    regenerate()  # 최대 2회!

# FORBIDDEN: 검수 결과 영어 출력
print("verdict: FAIL, reason: color mismatch")  # 한국어 출력!
```
