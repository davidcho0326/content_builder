# 전략실컷빌더 프롬프트 전략 (2026-04-30 확정)

> 레퍼런스 이미지 없이 프롬프트만으로 매거진 화보 수준 이미지 생성하는 검증된 전략

## CRITICAL RULES (절대 규칙)

### 1. DNA 분석은 항상 JSON 스키마 기반 (프리셋 수준 강제)
VLM에게 자유롭게 분석하라고 하면 안 된다. **빈 JSON 스키마를 주고 값만 채우게 해야 한다.**
스키마: `scripts/strategy_cut_builder/dna_schema.py`의 `POSE_SCHEMA`, `EXPRESSION_SCHEMA`, `BACKGROUND_SCHEMA`, `PRODUCT_SCHEMA` 사용.

```
X: "이 이미지의 포즈를 분석해주세요" (자유형 → 대충 나옴)
O: "이 JSON의 괄호 안 값을 채우세요" + POSE_SCHEMA 전달 (강제형 → 프리셋 수준)
```

이 규칙은 기존 `db/presets/duvetica/pose_presets.json` 수준과 동일한 디테일을 보장한다.
**예외 없음. 모든 DNA 분석에 적용.**

### 2. 모델 묘사는 브랜드별 고정 키워드 필수

| 브랜드 | 모델 묘사 키워드 |
|--------|----------------|
| **듀베티카** | "professional high-fashion model, angular jawline, high cheekbones, long elegant neck, slim editorial proportions" |
| **MLB** | "K-pop girl group member on her day off — tiny small face, sharp V-line jaw, big double-eyelid eyes, flawless dewy glass skin, long silky straight black hair, ultra slim with long legs" |
| **디스커버리** | "stunningly beautiful Korean fitness influencer — tiny face, sharp jawline, toned but feminine athletic build, sun-kissed glowing skin" |

이 키워드 없이 "model" 또는 "woman" 만 쓰면 퀄리티가 급격히 떨어진다.

### 3. 이미지 생성은 항상 3모델 병렬
가용한 모델 전부 병렬 생성하고 비교 셀렉한다:
- **Gemini** (gemini-3-pro-image-preview) — 기본
- **GPT Image 2** (gpt-image-2) — OpenAI
- **Higgsfield** (soul_2 / nano_banana_2) — MCP 연결 시

2개만 가용하면 2개, 3개 가용하면 3개. 단일 모델 생성 금지.

### 4. 추구미(레퍼런스) 이미지 선정은 AI 자동 셀렉이 기본 (CRITICAL)

**사람이 Pinterest에서 이쁜 사진 모아오는 것은 Plan B. 기본은 AI가 데이터 기반으로 자동 선별.**

회장님 요구: 트렌드 수집 → 추구미 선정 → 이미지 생성까지 전 과정이 AI 기반 데이터 파이프라인.

```
[AI 자동 추구미 파이프라인]

경쟁사 크롤링 (90장+)
    ↓
5속성 정량 분석 (fabric/fit/sheen/weight/lifestyle)
    ↓
브랜드 DNA 가드레일 매칭
    ↓
A등급 자동 셀렉 = "AI가 선정한 추구미"
    ↓
이 A등급 이미지를 레퍼런스로 → 마케팅 컷 생성
```

- **A등급**: 5속성 전부 가드레일 범위 내 → 그대로 사용 가능
- **B등급**: 일부 속성만 벗어남 → DNA 변환 후 사용 (소재/컬러만 교체)
- **C등급**: 2개+ 속성 크게 벗어남 → 리젝

**보고 프레이밍**: "AI가 경쟁사 트렌드 N장을 정량 분석하여, 우리 브랜드 DNA에 부합하는 이미지를 자동 선별"

### 5. 이미지 생성 시 추구미를 참조 이미지로 직접 첨부 (레퍼런스 가이드 방식)

프롬프트 온리보다 **추구미 이미지를 참조로 직접 첨부**하는 것이 더 좋은 결과를 낸다 (2026-04-30 검증).

```
X (프롬프트 온리): 추구미 VLM 분석 → 텍스트만으로 생성 → 포즈/구도 다름
O (레퍼런스 가이드): 추구미 이미지 직접 첨부 + "포즈/구도는 따라가고 옷만 바꿔" → 감도+구도 일치
```

레퍼런스 가이드 프롬프트 핵심:
- "POSE and BODY POSITION — replicate the exact pose"
- "COMPOSITION and FRAMING — same camera angle, distance, crop"
- "LIGHTING DIRECTION and QUALITY — same light source direction"
- "But CHANGE the garment to [DNA 블렌딩 결과]"

**검증 결과**: `Fnf_studio_outputs/strategy-cut-builder/duvetica/20260430_222257_dna_ref_guided/` — 18/18 성공

### 이중 전략 (Plan A / Plan B)

```
Plan A (기본): AI 자동 추구미
  경쟁사 크롤링 → 5속성 분석 → A등급 자동 셀렉 → 레퍼런스 가이드 생성
  → 보고: "AI가 데이터 기반으로 트렌드를 선별하여 마케팅 컷 생성"

Plan B (폴백): 수동 추구미 역설계
  사람이 추구미 이미지 수동 큐레이션 → 레퍼런스 가이드 생성
  → 보고: 트렌드 데이터와 사후 엮어서 정당화
  → 사용 조건: Plan A 결과물 퀄리티가 부족할 때만
```

## 3단계 파이프라인 (레퍼런스 가이드 방식)

```
[1] VLM 초정밀 분석 — 추구미 레퍼런스(AI 셀렉 or 수동)를 "촬영 감독 지시서"로 변환
[2] DNA 블렌딩 — 분석 결과 + 브랜드 DNA(옷/컬러/소재) 합성
[3] 프롬프트 온리 생성 — 텍스트만으로 Gemini/GPT 동시 생성
```

## 핵심 Anti-AI 기법 (검증 완료)

### 1. "~하는 순간을 포착" (Captured Moment)
```
X: "A woman wearing a jacket standing by a pool"
O: "Capturing the moment she just looked up from her book as golden hour light hit her face"
```
포즈가 아니라 **행동 중간**을 묘사하면 자연스러운 이미지가 나옴.

### 2. 화보 퀄리티 강제 키워드
```
필수 포함:
- "high-end fashion editorial for Vogue Italia / Massimo Dutti campaign"
- "3:4 portrait orientation"
- "professional high-fashion model, angular jawline, high cheekbones, long elegant neck"
- "editorial art direction — intentional negative space, rule of thirds"
```
이것 없으면 "아줌마 사진" 수준으로 떨어짐. 반드시 포함.

### 3. 카메라/필름 스펙 지정
```
필수 포함:
- "Hasselblad 500CM" (중형 필름 카메라 특유의 깊이감)
- "Kodak Portra 400" 또는 "Fuji Pro 400H" (필름 톤)
- "f/2.8 — background softly blurred" (얕은 심도)
- "visible fine grain, organic tonal transitions" (필름 그레인)
```

### 4. 후보정 묘사
```
필수 포함:
- "analog film grain visible throughout"
- "creamy highlight rolloff"
- "professional fashion retouching — skin flawless but visible texture and pores"
- "warm, timeless, unmistakably high-end editorial"
```

### 5. 자연스러운 불완전함
```
필수 포함:
- "wind-displaced strands of hair"
- "fabric caught mid-movement"
- "one shoulder slightly higher than the other"
- "natural skin texture visible"
```

## 비율 설정

| 모델 | 비율 | 설정 |
|------|------|------|
| Gemini | 3:4 세로 | `ImageConfig(aspect_ratio="3:4")` |
| GPT | 3:4 세로 | `aspect_ratio="3:4", resolution="2K"` → 1024x1536 |

가로형 절대 금지 — 패션 화보는 무조건 세로.

## VLM 분석 항목 (촬영 감독 지시서)

| 항목 | 추출 내용 |
|------|----------|
| moment | 포착된 순간 (행동 묘사) |
| camera | 렌즈, 필름, 조리개, 앵글, 프레이밍 |
| lighting | 광원 위치/방향, 품질, 색온도, 그림자, 하이라이트 |
| color_grading | 전체 톤, 피부톤, 그림자 색, 하이라이트 색, 채도 |
| subject | 바디 포지션, 손, 표정, 머리카락, 피부 |
| clothing | 아이템, 착용 방식, 패브릭 거동, 악세서리 |
| background | 세팅, 깊이 레이어, 텍스처, 컬러, 분위기 |
| imperfections | 자연스러운 불완전함 |

## 실패한 접근법 (반복 금지)

| 접근 | 결과 | 원인 |
|------|------|------|
| 한국 스튜디오 제품사진을 레퍼런스로 | 카탈로그 느낌 | 스튜디오 배경이 전이됨 |
| "fashion photo" 한 줄 지시 | AI 느낌 강함 | 화보 퀄리티 키워드 부재 |
| 모델 스펙 미지정 | 아줌마 사진 | "model" 만으로는 부족 |
| 가로형 비율 | 패션 느낌 없음 | 화보는 무조건 세로 |
| 레퍼런스를 그대로 복사 | 너무 똑같음 | 새로운 구도 필요 |

## 검증된 전체 흐름 (역설계 구조)

```
라이프스타일 비전 (이미 확정된 무드보드)
    ↓
VLM 초정밀 분석 → "촬영 감독 지시서"
    ↓
브랜드 DNA 블렌딩 (옷/컬러/소재 교체)
    ↓
Anti-AI 키워드 주입 (화보 퀄리티 + 순간 포착 + 필름 스펙)
    ↓
프롬프트 온리 생성 (Gemini + GPT 동시)
    ↓
결과 비교 → 베스트 셀렉
```

## 파일 위치

| 파일 | 역할 |
|------|------|
| `scripts/strategy_cut_builder/generate_duvetica_prompt_only.py` | 프롬프트 온리 생성 스크립트 |
| `brand-dna/duvetica.json` | 듀베티카 DNA (가드레일 + 마케팅 DNA) |
| `db/strategy-cut-builder/duvetica/_dna/detailed_dna_report.json` | 상세 DNA 추출 결과 |
