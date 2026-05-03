---
name: strategy-dna-extract
description: VLM으로 이미지 분류(product/marketing) + 브랜드 DNA 속성 추출. 전략실컷빌더 Step 1 후반.
user-invocable: true
trigger-keywords: ["DNA 분석", "DNA 추출", "strategy dna", "브랜드 DNA"]
---

# 전략컷 DNA 분석 (Strategy DNA Extract)

> 크롤링된 이미지를 VLM으로 분류(product/marketing/graphic)하고, 카테고리별 DNA 속성을 정량 추출한다.
> 추출 결과는 `brand-dna/{brand}.json`의 `data_driven_guardrails`로 반영된다.

---

## 절대 규칙

1. **VLM 분석은 항상 Gemini Flash** — `from core.config import VISION_MODEL` 사용
2. **병렬 분석 필수** — `ThreadPoolExecutor(max_workers=5)` (API 키 로테이션)
3. **product/marketing 2단 분류** — product는 정량 5속성, marketing은 프리셋 수준 상세
4. **🔴 DNA 분석은 반드시 JSON 스키마 기반 (CRITICAL)**
   - VLM에게 자유형 분석 시키면 안 된다
   - `scripts/strategy_cut_builder/dna_schema.py`의 빈 JSON 스키마를 VLM에 전달하고 **값만 채우게 한다**
   - 포즈: `POSE_SCHEMA` (left_arm/right_arm/left_leg/right_leg/hip/camera 전부 각도까지)
   - 표정: `EXPRESSION_SCHEMA` (eyes/gaze/mouth/chin/note)
   - 배경: `BACKGROUND_SCHEMA` (setting_description/lighting_detail/provided_elements)
   - 제품: `PRODUCT_SCHEMA` (fabric/fit/sheen/weight 1-5 + logo_visibility)
   - 이 수준은 기존 `db/presets/duvetica/pose_presets.json`과 동일한 디테일
   - **예외 없음. "대충 분석"은 VIOLATION.**

---

## 입력

| 입력 | 필수 | 형식 | 예시 |
|------|------|------|------|
| 이미지 폴더 경로 | O | 경로 | `db/strategy-cut-builder/duvetica/official-site/` |
| 브랜드명 | O | 문자열 | `duvetica` |

---

## 출력

```
db/strategy-cut-builder/{brand}/official-site/
├── _dna/
│   ├── full_dna_report.json         # 전체 분류 + 속성 (이미지별)
│   ├── detailed_dna_report.json     # 상세 DNA (marketing 프리셋)
│   └── classification_summary.json  # 분류 통계 요약
└── _classified/
    ├── product/                     # 제품 이미지 복사
    └── marketing/                   # 마케팅 이미지 복사

.claude/projects/strategy-cut-builder/brand-dna/{brand}.json
  → data_driven_guardrails 섹션 업데이트
```

---

## 분류 기준

| 분류 | 정의 | 예시 |
|------|------|------|
| **product** | 단일 의류 + 흰/무지 배경, 평치기, 디테일 크롭, 소재 클로즈업 | 흰 배경 다운재킷 |
| **marketing** | 모델 착용, 라이프스타일, 캠페인 비주얼, 에디토리얼 | 모델이 입고 있는 화보 |
| **graphic** | 로고, 텍스트, 배너, 그래픽 요소 | 브랜드 로고 이미지 (분석 제외) |

---

## Product 이미지 분석 항목 (정량 5속성)

| 속성 | 스케일 | 설명 |
|------|--------|------|
| `fabric` | 1~5 | 1=천연 프리미엄 린넨/코튼, 3=중간, 5=헤비 테크니컬 |
| `fit` | 1~5 | 1=스킨 타이트, 3=레귤러, 5=오버사이즈 |
| `sheen` | 1~5 | 1=풀 매트, 3=세미, 5=하이 글로스 |
| `weight` | 1~5 | 1=울트라 라이트, 3=미드, 5=베리 헤비 |
| `garment_type` | 문자열 | quilted down jacket, zip-up hoodie 등 |
| `target_category` | 문자열 | woven_jacket, setup, down, knit_polo, pants, other |
| `color_description` | 문자열 | 컬러 묘사 |

### 가드레일 계산 (카테고리별 집계)

```python
# 카테고리별로 속성 min/max/median 산출
guardrails = {
    "woven_jacket": {
        "attributes": {
            "fabric": {"min": 2, "max": 4, "median": 3},
            "fit": {"min": 3, "max": 4, "median": 3},
            "sheen": {"min": 1, "max": 3, "median": 2},
            "weight": {"min": 2, "max": 3, "median": 2}
        },
        "top_colors": ["Ivory", "Navy", "Stone"],
        "garment_types": ["woven jacket", "overshirt"]
    }
}
```

---

## Marketing 이미지 분석 항목 (프리셋 수준 상세)

기존 `db/presets/` 포맷과 동일한 수준으로 추출:

### Pose 분석

| 항목 | 값 예시 |
|------|--------|
| `stance` | stand, sit, lean, walk, lie_back, recline, crouch |
| `left_arm` | { description, hand, elbow_angle, elbow_direction } |
| `right_arm` | { description, hand, elbow_angle, elbow_direction } |
| `left_leg` | { knee_angle, knee_direction, knee_height, foot_direction, foot_position } |
| `right_leg` | { knee_angle, knee_direction, knee_height, foot_direction, foot_position } |
| `hip` | 힙 방향/기울기 |
| `shoulder_line` | 어깨 라인 기울기 |
| `face_direction` | 얼굴 방향 |
| `camera` | { angle, height, framing } |

### Expression 분석

| 항목 | 값 예시 |
|------|--------|
| `base` | dreamy, serene, candid, confident, cool, neutral |
| `eyes` | half-closed dreamy, direct gaze calm |
| `gaze_direction` | camera, left, down, distant |
| `mouth` | closed relaxed, slight smile |
| `face_angle` | 3/4 turn, frontal |
| `chin` | slightly raised, neutral |
| `note` | 전체 분위기 메모 |

### Background 분석

| 항목 | 값 예시 |
|------|--------|
| `type` | outdoor-resort, studio, urban, nature |
| `region_vibe` | Mediterranean, Nordic, Urban Tokyo |
| `time_of_day` | golden hour, midday, blue hour |
| `colors` | 배경 주요 컬러 |
| `setting_description` | 상세 세팅 묘사 |
| `mood` | 분위기 키워드 |
| `provided_elements` | 소품/건축 요소 |
| `available_poses` | 이 배경에 어울리는 포즈 |
| `lighting_detail` | 조명 상세 (방향, 품질, 색온도) |
| `notes` | 추가 메모 |

---

## 실행 파이프라인

```
1. 이미지 폴더 스캔 (jpg, jpeg, png, webp)
       ↓
2. VLM 1차 분류 (product / marketing / graphic)
   - 병렬 실행: ThreadPoolExecutor(max_workers=5)
   - 배치: 5장씩 묶어 처리
       ↓
3. Product 이미지 → 정량 5속성 추출
   Marketing 이미지 → 프리셋 수준 상세 추출
       ↓
4. 카테고리별 가드레일 산출 (min/max/median)
       ↓
5. brand-dna/{brand}.json 업데이트
   - data_driven_guardrails 섹션 추가/갱신
       ↓
6. 결과 보고 (분류 통계 + 가드레일 요약)
```

---

## 백엔드 스크립트

| 스크립트 | 역할 |
|---------|------|
| `scripts/strategy_cut_builder/classify_and_extract_dna.py` | 1차 분류 + 기본 속성 추출 |
| `scripts/strategy_cut_builder/extract_detailed_dna.py` | marketing 이미지 프리셋 수준 상세 추출 |
| `scripts/strategy_cut_builder/extract_brand_dna.py` | 브랜드 DNA JSON 통합 생성 |
| `scripts/strategy_cut_builder/extract_instagram_dna.py` | 인스타그램 DNA 추출 |

---

## VLM 프롬프트 패턴

```python
from core.config import VISION_MODEL
from core.api import _get_next_api_key, _pil_to_part, call_gemini_vision

# 분류 프롬프트
CLASSIFY_PROMPT = """Classify this fashion brand image:
1. "product" - garment on white/neutral background
2. "marketing" - model wearing clothes, campaign visual
3. "graphic" - logo, text, banner

Also extract: garment_type, color_description, target_category,
fabric(1-5), fit(1-5), sheen(1-5), weight(1-5)

For "marketing": additionally extract pose/expression/background details.

Respond ONLY with valid JSON."""
```

---

## 금지 패턴

```python
# FORBIDDEN: VLM 모델 하드코딩
client = genai.Client(...)
model = "gemini-2.0-flash"  # 금지!

# FORBIDDEN: 순차 분석
for img_path in image_paths:
    result = analyze_image(img_path)
    time.sleep(2)

# FORBIDDEN: graphic 이미지를 DNA에 포함
# graphic 분류된 이미지는 분석에서 제외
```

---

## 실행 방법

```bash
# 분류 + 기본 DNA 추출
PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/classify_and_extract_dna.py

# 상세 DNA 추출 (marketing 이미지 대상)
PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/extract_detailed_dna.py
```
