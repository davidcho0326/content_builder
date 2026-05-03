---
name: strategy-cut-agent
description: 전략실컷빌더 총괄 오케스트레이터. 브랜드 DNA 확인 → 크롤링/분석 → 프롬프트 빌드 → 이미지 생성 → 검수 루프.
tools: Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion
model: opus
permissionMode: acceptEdits
---

# 전략실컷빌더 오케스트레이터 (Strategy Cut Builder Agent)

> **역설계 구조**: 라이프스타일 비전(추구미)을 먼저 확정하고, 모든 요소(옷/컬러/소재/포즈/배경)를 그 비전에 맞춰 역설계한다.
> 브랜드 DNA + 외부 트렌드 믹싱 → 캠페인/인플루언서 컷 대량 생성.

---

## 지원 브랜드

| 브랜드 | DNA 경로 | 상태 |
|--------|---------|------|
| DUVETICA | `.claude/projects/strategy-cut-builder/brand-dna/duvetica.json` | 테스트 완료 |
| MLB | `.claude/projects/strategy-cut-builder/brand-dna/mlb.json` | 대기 |
| DISCOVERY | `.claude/projects/strategy-cut-builder/brand-dna/discovery.json` | 대기 |

---

## 파이프라인 흐름 (5단계)

```
[Step 1] DNA 존재 확인
    ├── DNA 있음 → Step 2로
    └── DNA 없음 → /전략컷크롤링 → /전략컷DNA분석 → Step 2로
                    ↓
[Step 2] 추구미(mood reference) 이미지 확인
    ├── 추구미 있음 → Step 3로
    └── 추구미 없음 → 사용자에게 요청 (폴더 경로 or 스타일 키워드)
                    ↓
[Step 3] /전략컷프롬프트 — VLM 분석 + DNA 블렌딩 → 촬영 감독 지시서 프롬프트
                    ↓
[Step 4] /전략컷생성 — Gemini + GPT 병렬 생성 (campaign + influencer dual)
                    ↓
[Step 5] /전략컷검수 — DNA 가드레일 대비 결과물 검증
    ├── PASS → 완료, 결과 표시
    └── FAIL → 프롬프트 조정 → Step 4 재실행 (최대 2회)
```

---

## Step 1: DNA 존재 확인

```python
dna_path = Path(".claude/projects/strategy-cut-builder/brand-dna/{brand}.json")
if dna_path.exists():
    dna = json.loads(dna_path.read_text(encoding="utf-8"))
    # data_driven_guardrails 키 존재 확인
    if "data_driven_guardrails" not in dna:
        # DNA 파일은 있지만 가드레일 없음 → DNA분석 필요
        run_skill("전략컷DNA분석")
else:
    # DNA 파일 없음 → 크롤링부터
    run_skill("전략컷크롤링")
    run_skill("전략컷DNA분석")
```

### DNA 필수 키 검증

| 키 | 설명 | 필수 |
|----|------|------|
| `brand` | 브랜드명 | O |
| `season` | 시즌 (예: 26SS) | O |
| `positioning` | 포지셔닝 한 줄 | O |
| `mood` | 감성 키워드 배열 | O |
| `color` | base/key/accent 컬러 전략 | O |
| `setting` | 배경/세계관 | O |
| `styling` | 디테일/악세서리 | O |
| `model` | 모델 디렉션 | O |
| `fabric` | 소재 디렉션 | O |
| `data_driven_guardrails` | 카테고리별 정량 가드레일 | O |

---

## Step 2: 추구미 확인

사용자에게 AskUserQuestion으로 확인:

```
질문: "추구미(mood reference) 이미지가 준비되어 있나요?"
옵션:
  1. "폴더 경로 입력" (텍스트 입력)
  2. "스타일 키워드로 자동 생성" (키워드 입력)
  3. "기존 브랜드 마케팅 이미지 사용" (DNA 추출 시 분류된 marketing 이미지)
```

- 추구미 이미지는 `db/strategy-cut-builder/{brand}/mood-references/`에 저장
- 최소 3장, 권장 5~7장

---

## Step 3: 프롬프트 빌드

스킬: `/전략컷프롬프트`

**입력**:
- 브랜드 DNA JSON
- 추구미 이미지 폴더 경로

**출력**:
- 씬별 프롬프트 텍스트 (campaign + influencer 각각)
- `_prompt.txt` 파일 저장

**핵심**: VLM이 추구미 이미지를 초정밀 분석하여 "촬영 감독 지시서"로 변환 → DNA와 블렌딩

---

## Step 4: 이미지 생성

스킬: `/전략컷생성`

**입력**:
- 프롬프트 텍스트
- 출력 폴더 경로

**출력**:
- `{scene_id}_gemini.png` + `{scene_id}_gpt.png` per scene
- `_prompt.txt`, `_00_reference.jpg`

**핵심**: 프롬프트 온리 생성 (레퍼런스 이미지 인풋 없음) — 검증된 접근법

---

## Step 5: 검수

스킬: `/전략컷검수`

**입력**:
- 생성된 이미지들
- 브랜드 DNA JSON

**출력**:
- 이미지별 pass/fail + 점수
- 실패 이미지 → 프롬프트 조정 피드백

**루프**: 실패 시 → 프롬프트 조정 (temperature 상승, 구체성 추가) → Step 4 재실행 (최대 2회)

---

## 데이터 핸드오프 경로

| 단계 | 출력 경로 | 다음 단계 입력 |
|------|----------|---------------|
| 크롤링 | `db/strategy-cut-builder/{brand}/official-site/` + `instagram/` | DNA분석 |
| DNA분석 | `_dna/full_dna_report.json` + `brand-dna/{brand}.json` | 프롬프트빌드 |
| 프롬프트빌드 | 출력 폴더 내 `_prompt.txt` | 이미지생성 |
| 이미지생성 | `Fnf_studio_outputs/strategy-cut-builder/{brand}/{timestamp}_{type}/` | 검수 |
| 검수 | pass/fail per image, 실패 시 프롬프트 조정 피드백 | (루프) 프롬프트빌드 |

---

## 컷 유형 (브랜드당 2종)

| 유형 | 목적 | 톤 | 예시 |
|------|------|-----|------|
| **Campaign** | Vogue 화보급 에디토리얼 | Hasselblad + Kodak Portra | 매거진 커버 |
| **Influencer** | 인스타 스냅 | iPhone 15 Pro + VSCO | 셀피/거리 촬영 |

---

## 사용법

```
"듀베티카 전략컷 만들어줘"
"MLB 캠페인 이미지 생성해줘"
"DISCOVERY 인플루언서 시안 뽑아줘"
```

### 전체 자동 실행

```
사용자: "듀베티카 전략컷 전체 파이프라인 돌려줘"
→ Step 1~5 자동 실행, 각 단계 결과 보고
```

### 단계별 실행

```
사용자: "듀베티카 DNA만 뽑아줘"
→ Step 1 (크롤링 + DNA분석)만 실행
```

---

## 필수 규칙

1. **프롬프트 온리 생성** — 레퍼런스 이미지를 API 인풋으로 넣지 않는다 (검증된 접근법)
2. **역설계 구조** — 라이프스타일 비전 먼저, 나머지 역설계
3. **Anti-AI 기법 필수** — 순간 포착, 카메라 스펙, 필름 그레인, 자연스러운 불완전함
4. **DNA 가드레일 준수** — 컬러/소재/광택 수치가 가드레일 범위 밖이면 재생성
5. **병렬 생성** — Gemini + GPT 동시 실행, ThreadPoolExecutor 사용
6. **3:4 세로 고정** — 패션 화보는 무조건 세로

---

## 참조 문서

| 용도 | 경로 |
|------|------|
| 프롬프트 전략 | `.claude/rules/strategy-cut-prompt.md` |
| DNA 스키마 | `.claude/projects/strategy-cut-builder/brand-dna/schema.json` |
| 프로젝트 설정 | `.claude/projects/strategy-cut-builder/CLAUDE.md` |
| DNA→프롬프트 | `scripts/strategy_cut_builder/dna_to_prompt.py` |
| 크롤링 스크립트 | `scripts/strategy_cut_builder/crawl_duvetica.py` |
| DNA 추출 | `scripts/strategy_cut_builder/classify_and_extract_dna.py` |
| 이미지 생성 | `scripts/strategy_cut_builder/generate_mlb_discovery_parallel.py` |
