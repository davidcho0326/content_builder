# 전략실컷빌더 핸드오프 가이드

> 이 폴더는 "마케팅컷 생성 에이전트"의 전체 시스템을 담고 있습니다.
> PM(김효은)의 Claude Code가 이 폴더를 읽고 다른 에이전트들과 연결합니다.

## 폴더 구조

```
_handoff/
├── GUIDE.md              ← 이 파일 (사용 가이드)
├── agents/               ← 파이프라인 오케스트레이터
│   └── strategy-cut-agent.md
├── skills/               ← 5단계 스킬 + Higgsfield
│   ├── 전략컷크롤링_strategy-crawl/        Step 1
│   ├── 전략컷DNA분석_strategy-dna-extract/  Step 2
│   ├── 전략컷프롬프트_strategy-prompt-build/ Step 3
│   ├── 전략컷생성_strategy-generate/        Step 4
│   ├── 전략컷검수_strategy-inspect/         Step 5
│   └── 힉스필드_higgsfield/                Higgsfield MCP
├── scripts/              ← Python 실행 코드 (뒷단)
├── rules/                ← 프롬프트 전략 5대 규칙
├── hooks/                ← DNA JSON 필수 필드 검증
├── brand-dna/            ← 3브랜드 DNA JSON
│   ├── duvetica.json
│   ├── mlb.json
│   ├── discovery.json
│   └── schema.json       ← 공통 스키마
├── project-docs/         ← README + 전략 문서
│   ├── README.md          ← 프로젝트 히스토리 + 연결 구조
│   ├── prompt-strategy.md ← 프롬프트 전략 상세
│   └── CLAUDE.md          ← 프로젝트 컨텍스트
└── results/              ← 생성 결과물 (154장)
    ├── duvetica/          4개 테스트
    ├── mlb/               1개 테스트
    ├── discovery/         2개 테스트
    └── _higgsfield/       3브랜드 비교 6장
```

## PM이 이 폴더를 쓰는 방법

### 1. 자기 프로젝트에 복사

```bash
# agents, skills, rules, hooks → .claude/ 아래로
cp agents/* .claude/agents/
cp -r skills/* .claude/skills/
cp rules/* .claude/rules/
cp hooks/* .claude/hooks/

# scripts → 프로젝트 루트
cp -r scripts/ scripts/strategy_cut_builder/

# brand-dna → 프로젝트 설정
cp -r brand-dna/ .claude/projects/strategy-cut-builder/brand-dna/
```

### 2. 다른 에이전트와 연결

이 에이전트의 **입력/출력 계약**:

```
[앞단 에이전트가 줘야 하는 것]
├── brand-dna/{brand}.json     ← 브랜드 DNA (없으면 자체 생성)
├── 추구미 이미지 폴더         ← AI 자동 셀렉 or 수동 큐레이션
└── 시즌/카테고리 지정          ← "27SS WJ" 등

[이 에이전트가 만드는 것]
├── 캠페인컷 이미지 (PNG 3:4)   ← Gemini + GPT + Higgsfield 3모델
├── 인플컷 이미지 (PNG 3:4)
├── 프롬프트 텍스트 (_prompt.txt)
└── 검수 결과 (validation.json)

[뒷단 에이전트가 받는 것]
├── 이미지 → 컨텐츠 기획안 PPTX
├── 이미지 → 채널별 배너
├── 이미지 → SNS Grid 피드 등록
└── 이미지 → 매장 VMD 시뮬레이션
```

### 3. 직접 실행

```bash
# 듀베티카 전체 파이프라인
PYTHONPATH=. .venv/Scripts/python scripts/generate_duvetica_dna_auto.py

# MLB + Discovery 병렬
PYTHONPATH=. .venv/Scripts/python scripts/generate_mlb_dx_tuned.py

# 검수
PYTHONPATH=. .venv/Scripts/python scripts/inspect_results.py \
    --folder Fnf_studio_outputs/strategy-cut-builder/duvetica/{폴더} \
    --brand duvetica
```

## 5대 절대 규칙 (요약)

| # | 규칙 | 위반 시 |
|---|------|--------|
| 1 | DNA 분석은 **JSON 스키마 기반** (dna_schema.py) | 자유형 분석 → 디테일 부족 |
| 2 | 브랜드별 **모델 키워드 고정** (K-pop/editorial/fitness) | "model" 만 쓰면 아줌마 사진 |
| 3 | 이미지 생성은 **항상 3모델 병렬** (Gemini+GPT+Higgsfield) | 단일 모델 → 비교 불가 |
| 4 | 추구미는 **AI 자동 셀렉이 기본** (A등급 자동 선별) | 수동 큐레이션은 Plan B |
| 5 | **레퍼런스 가이드 방식** (추구미 이미지 직접 첨부) | 프롬프트 온리 → 포즈/구도 다름 |

## 이중 전략

```
Plan A (기본): AI 자동
  경쟁사 크롤링 → 5속성 분석 → A등급 자동 셀렉 → 레퍼런스 가이드 생성

Plan B (폴백): 수동 역설계
  사람이 추구미 수동 큐레이션 → 레퍼런스 가이드 생성 → 트렌드와 사후 엮기
```

## results/ 폴더 가이드

| 폴더 | 방식 | 퀄리티 | 비고 |
|------|------|:---:|------|
| `duvetica/dna_auto` | DNA 자동 블렌딩 (프롬프트 온리) | B+ | 화보 감도 OK, 포즈 다양 |
| `duvetica/dna_ref_guided` | **레퍼런스 가이드** | **A** | **최고 퀄리티 — 이 방식 사용** |
| `duvetica/dna_auto_cool` | 쿨톤 테스트 | B | 톤 변형 실험 |
| `duvetica/bulk_test` | 대량 50장 (Gemini만) | C | 3모델 미적용, 참고용만 |
| `mlb/tuned` | VLM 추구미 분석 기반 | B | K-pop 키워드 적용 |
| `discovery/tuned` | VLM 추구미 분석 기반 | B | 웰니스 키워드 적용 |
| `_higgsfield/` | Higgsfield soul_2 | B+ | 3모델 비교용 |

**권장**: `dna_ref_guided` 방식을 기본으로 사용. 추구미 이미지를 참조로 직접 첨부하되 옷/스타일링만 DNA로 교체.

## 새 브랜드 추가

1. `brand-dna/{brand}.json` 생성 (schema.json 참고)
2. 필수 필드: brand, season, positioning, mood, color, setting, styling, model, fabric, data_driven_guardrails
3. 추구미 이미지 7~15장 폴더 준비
4. 파이프라인 실행 → 끝
