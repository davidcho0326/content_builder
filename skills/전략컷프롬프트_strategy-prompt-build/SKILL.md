---
name: strategy-prompt-build
description: 브랜드 DNA + 추구미 레퍼런스 → 에디토리얼 프롬프트 생성. 전략실컷빌더 Step 3.
user-invocable: true
trigger-keywords: ["전략컷 프롬프트", "DNA 프롬프트", "strategy prompt", "프롬프트 빌드"]
---

# 전략컷 프롬프트 빌드 (Strategy Prompt Build)

> **역설계 구조**: 추구미(라이프스타일 비전)를 먼저 VLM 초정밀 분석하여 "촬영 감독 지시서"로 변환한 뒤,
> 브랜드 DNA(옷/컬러/소재)를 블렌딩하여 최종 프롬프트를 조립한다.
> 프롬프트 온리 생성용 — 레퍼런스 이미지를 API 인풋으로 넣지 않는다.

---

## 절대 규칙

1. **Anti-AI 기법 5종 전체 포함 필수** — 하나라도 누락 시 AI 느낌 강해짐
2. **프롬프트 온리** — 레퍼런스 이미지는 분석용으로만, 생성 API 인풋에 넣지 않음
3. **3:4 세로 고정** — `3:4 portrait orientation` 필수 포함
4. **DNA 가드레일 범위 내** — 컬러/소재/광택이 가드레일 벗어나면 프롬프트 조정

---

## 입력

| 입력 | 필수 | 형식 | 예시 |
|------|------|------|------|
| 브랜드 DNA JSON | O | JSON 파일 경로 | `.claude/projects/strategy-cut-builder/brand-dna/duvetica.json` |
| 추구미 이미지 폴더 | O | 폴더 경로 | `db/strategy-cut-builder/duvetica/mood-references/` |

---

## 출력

| 출력 | 형식 | 위치 |
|------|------|------|
| 씬별 프롬프트 | 텍스트 | 출력 폴더 내 `_prompt.txt` |
| 블렌딩 리포트 | JSON | 출력 폴더 내 `_blend_report.json` |

---

## 프롬프트 조립 3단계

```
[1] VLM 초정밀 분석 — 추구미 이미지를 "촬영 감독 지시서"로 변환
[2] DNA 블렌딩 — 분석 결과의 의상/컬러/소재를 브랜드 DNA로 교체
[3] Anti-AI 키워드 주입 — 화보 퀄리티 + 순간 포착 + 필름 스펙 적용
```

---

## 1단계: VLM 초정밀 분석 (촬영 감독 지시서)

각 추구미 이미지를 아래 8개 항목으로 분석:

| 항목 | 추출 내용 |
|------|----------|
| `moment` | 포착된 순간 (행동 묘사 — "~하는 순간") |
| `camera` | 렌즈, 필름, 조리개, 앵글, 프레이밍 |
| `lighting` | 광원 위치/방향, 품질, 색온도, 그림자, 하이라이트 |
| `color_grading` | 전체 톤, 피부톤, 그림자 색, 하이라이트 색, 채도 |
| `subject` | 바디 포지션, 손, 표정, 머리카락, 피부 |
| `clothing` | 아이템, 착용 방식, 패브릭 거동, 악세서리 |
| `background` | 세팅, 깊이 레이어, 텍스처, 컬러, 분위기 |
| `imperfections` | 자연스러운 불완전함 (바람에 흩날리는 머리카락, 움직이는 옷감 등) |

```python
from core.config import VISION_MODEL
from core.api import call_gemini_vision, _pil_to_part

VLM_ANALYSIS_PROMPT = """You are a world-class fashion photography director.
Analyze this image as if you're writing detailed shot instructions for recreating it.

Extract these 8 categories as JSON:
{
  "moment": "describe the exact captured moment as an action",
  "camera": {"lens": "...", "film": "...", "aperture": "...", "angle": "...", "framing": "..."},
  "lighting": {"source": "...", "direction": "...", "quality": "...", "color_temp": "...", "shadows": "...", "highlights": "..."},
  "color_grading": {"overall_tone": "...", "skin_tone": "...", "shadow_color": "...", "highlight_color": "...", "saturation": "..."},
  "subject": {"body_position": "...", "hands": "...", "expression": "...", "hair": "...", "skin": "..."},
  "clothing": {"items": [...], "how_worn": "...", "fabric_behavior": "...", "accessories": [...]},
  "background": {"setting": "...", "depth_layers": "...", "texture": "...", "colors": "...", "mood": "..."},
  "imperfections": ["...", "..."]
}"""
```

---

## 2단계: DNA 블렌딩 (자동)

VLM 분석 결과에서 의상/컬러/소재를 브랜드 DNA로 교체:

```python
from scripts.strategy_cut_builder.dna_to_prompt import load_dna, pick_color, get_fabric_desc

dna = load_dna(brand)

# 컬러 자동 선택 (가중 랜덤: base 70%, key 20%, accent 10%)
color = pick_color(dna, tier="weighted")

# 소재 묘사 (가드레일 median 기준)
fabric_desc = get_fabric_desc(dna, category)

# 핏 가드레일
fit_guardrail = dna["data_driven_guardrails"][category]["attributes"]["fit"]

# 스타일링 디테일 (랜덤 셀렉)
styling_details = random.choice(dna.get("styling", {}).get("details", []))
```

### DNA 블렌딩 규칙

| 항목 | 블렌딩 방법 |
|------|-----------|
| 컬러 | `pick_color(dna, "weighted")` — base 70% / key 20% / accent 10% |
| 소재 | `get_fabric_desc(dna, category)` — 가드레일 median 기준 |
| 핏 | 가드레일 min~max 범위 내 랜덤 |
| 광택 | 가드레일 median 기준 ± 1 |
| 스타일링 | `dna.styling.details`에서 랜덤 선택 |
| 배경 | `dna.setting` 기반, VLM 분석의 분위기와 합성 |
| 모델 | `dna.model` 기반 (연령/뷰티/표정 디렉션) |

---

## 3단계: Anti-AI 키워드 주입 (CRITICAL)

5종 전체 필수 — 하나라도 누락 시 AI 느낌 강해짐:

### 1. "~하는 순간을 포착" (Captured Moment)

```
X: "A woman wearing a jacket standing by a pool"
O: "Capturing the moment she just looked up from her book as golden hour light hit her face"
```

### 2. 카메라/필름 스펙 지정

| 유형 | 카메라 | 필름 |
|------|--------|------|
| **Campaign** | Hasselblad 500CM | Kodak Portra 400, f/2.8 |
| **Influencer** | iPhone 15 Pro | VSCO filter, bright clean |

### 3. 모델 스펙 지정

| 유형 | 모델 묘사 |
|------|----------|
| **Campaign** | professional high-fashion model, angular jawline, high cheekbones, long elegant neck |
| **Influencer** | Korean influencer in her mid-20s, naturally pretty, warm approachable vibe |

### 4. 후보정 묘사

| 유형 | 후보정 |
|------|--------|
| **Campaign** | analog film grain, creamy highlight rolloff, professional fashion retouching |
| **Influencer** | VSCO filter, bright clean, Instagram-ready natural look |

### 5. 자연스러운 불완전함

```
필수 포함:
- wind-displaced strands of hair
- fabric caught mid-movement
- one shoulder slightly higher than the other
- natural skin texture visible
```

---

## 프롬프트 템플릿 (2종)

### Campaign 프롬프트 (Vogue 에디토리얼)

```
High-end fashion editorial for Vogue Italia / {brand} {season} campaign.
3:4 portrait orientation.

MOMENT: {vlm_analysis.moment}

MODEL: Professional high-fashion model, {dna.model.beauty}, {dna.model.expression}.
WEARING: {dna_blended_garment_description}
COLOR: {color.name} ({color.hex}) — {fabric_desc}
STYLING: {styling_details}

CAMERA: Hasselblad 500CM, Kodak Portra 400, f/2.8 — background softly blurred.
LIGHTING: {vlm_analysis.lighting}
COLOR GRADING: {vlm_analysis.color_grading}

BACKGROUND: {dna.setting} — {vlm_analysis.background.mood}
{vlm_analysis.background.setting}

IMPERFECTIONS: wind-displaced strands of hair, fabric caught mid-movement,
natural skin texture visible, one shoulder slightly higher.

POST-PRODUCTION: analog film grain visible throughout, creamy highlight rolloff,
professional fashion retouching — skin flawless but visible texture and pores.
Warm, timeless, unmistakably high-end editorial.

Editorial art direction — intentional negative space, rule of thirds.
```

### Influencer 프롬프트 (Instagram 스냅)

```
Instagram lifestyle photo by Korean fashion influencer.
3:4 portrait orientation.

MOMENT: {vlm_analysis.moment — 더 캐주얼하게 변환}

MODEL: Korean influencer in her mid-20s, naturally pretty, warm approachable vibe.
WEARING: {dna_blended_garment_description — 캐주얼 톤다운}
COLOR: {color.name} — {fabric_desc}

CAMERA: iPhone 15 Pro, natural daylight, slight overexposure.
SETTING: {dna.setting — 캐주얼 배경 변환}

FEEL: VSCO filter, bright clean aesthetic, Instagram-ready.
Natural imperfections — candid angle, slightly imperfect framing.

NOT an ad. Looks like a real person posting on their feed.
```

---

## 백엔드 스크립트

| 스크립트 | 역할 |
|---------|------|
| `scripts/strategy_cut_builder/dna_to_prompt.py` | DNA JSON → 의상/컬러/소재 프롬프트 자동 생성 |
| `scripts/strategy_cut_builder/attribute_to_prompt.py` | 속성값 → 텍스트 변환 |
| `scripts/strategy_cut_builder/attribute_to_prompt_multi.py` | 다중 속성 병렬 변환 |
| `scripts/strategy_cut_builder/lifestyle_scenarios.py` | 라이프스타일 시나리오 정의 |

---

## 금지 패턴

```python
# FORBIDDEN: 레퍼런스 이미지를 생성 API 인풋으로 전달
generate_image(prompt, reference_images=[ref_img])  # 프롬프트 온리!

# FORBIDDEN: Anti-AI 키워드 누락
prompt = f"A woman wearing {garment} in {background}"  # AI 느낌 강함

# FORBIDDEN: 모델 스펙 미지정
prompt = "a model wearing..."  # "아줌마 사진" 수준

# FORBIDDEN: 가로형 비율
aspect_ratio = "16:9"  # 패션 화보는 무조건 세로 3:4

# FORBIDDEN: DNA 가드레일 무시
sheen = 5  # 가드레일 max=3 인데 5 사용
```

---

## 실행 방법

```python
from scripts.strategy_cut_builder.dna_to_prompt import (
    load_dna, build_full_editorial_prompt, build_garment_prompt
)

dna = load_dna("duvetica")
campaign_prompt = build_full_editorial_prompt(dna, category="woven_jacket", cut_type="campaign")
influencer_prompt = build_full_editorial_prompt(dna, category="woven_jacket", cut_type="influencer")
```

---

## 실패한 접근법 (반복 금지)

| 접근 | 결과 | 원인 |
|------|------|------|
| 한국 스튜디오 제품사진을 레퍼런스로 | 카탈로그 느낌 | 스튜디오 배경이 전이됨 |
| "fashion photo" 한 줄 지시 | AI 느낌 강함 | 화보 퀄리티 키워드 부재 |
| 모델 스펙 미지정 | 아줌마 사진 | "model"만으로는 부족 |
| 가로형 비율 | 패션 느낌 없음 | 화보는 무조건 세로 |
| 레퍼런스를 그대로 복사 | 너무 똑같음 | 새로운 구도 필요 |
