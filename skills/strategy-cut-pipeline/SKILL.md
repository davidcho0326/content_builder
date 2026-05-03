---
name: strategy-cut-pipeline
description: brand-dna + 시즌/카테고리 → 추구미 자동 셀렉 → 캠페인 제안서 → moment LLM 추출 → 5-provider 병렬 이미지 생성 → HTML 갤러리 자동 오픈. F&F 마케팅컷 빌더 엔드투엔드.
user-invocable: true
trigger-keywords:
  - "캠페인 만들어"
  - "전략컷 파이프라인"
  - "추구미 자동"
  - "마케팅컷 만들어"
  - "캠페인 갤러리"
  - "strategy cut pipeline"
  - "auto campaign"
  - "DUVETICA 캠페인"
  - "MLB 캠페인"
  - "Discovery 캠페인"
---

# Strategy-Cut Pipeline (마케팅컷 자동 빌더, v2)

> **brand-dna + 시즌/카테고리 두 개만 받아** 추구미 셀렉 → 캠페인 제안서 → 씬별 moment 자동 추출 → 5-provider 병렬 이미지 생성 → 한판 갤러리 오픈까지 완전 자동화.
> 검증 완료 (2026-05-02): DUVETICA 27SS WJ × 5 providers × 6 scenes = 30장 자동 생성, HF MCP 통합 동작.

```
brand_dna + season/category
   ↓ Step A) Mood reference auto-select          (deterministic Python)
   ↓ Step B) Influencer campaign proposal        (JSON + MD)
   ↓ Step B.5) THE MOMENT extraction             (gemini-3.1-flash-lite-preview, ref → 1줄)  ★
   ↓ Step C) 5-provider image generation         (Gemini-3-pro + GPT-image-2 + HF Soul/Nano/GPT)
   ↓ Step D) Gallery HTML build + auto-open      (file:// 자동 실행)
```

---

## 🚨 프로젝트 default — Higgsfield MCP는 항상 실행

**모든 캠페인 run은 Direct(Gemini+GPT) 12장 + Higgsfield(Soul+Nano+GPT) 18장 = 30장이 표준 산출물.**

- `run_campaign_pipeline.py` `--providers` default = `gemini gpt higgsfield` (이제부터 모두 포함)
- Python은 12장 + `higgsfield_manual_guide.md` 트리거 문서를 떨어뜨리고 종료
- **Claude agent는 종료 후 즉시 §"Higgsfield MCP 자동화 흐름"의 8-step 시퀀스를 실행해야 함**
- 사용자가 명시적으로 `"HF 빼고"` 또는 `--providers gemini gpt`를 지정한 경우에만 스킵
- HF MCP 서버가 disconnect 상태면: 트리거 문서를 만들고 사용자에게 1줄 안내만 남기고 종료 (다음 세션이 connect되면 그때 18장 채움)

## Quick Start (사용자가 다시 호출하면 그대로 실행)

```bash
# DUVETICA 27SS WJ — 표준 (product-aware mode, 5 providers, k=6)
cd /d/ralph_kaphacy/ST\)MKT_builder_for_fnf

# Step 1: Python 파이프라인 — Direct 12장 + HF 트리거 + 갤러리 v1
python st_cut-dev/scripts/run_campaign_pipeline.py \
  --brand duvetica --season-category "27SS WJ" --k 6 \
  --brand-filter duvetica \
  --max-workers 4 --mood-mode product \
  --selector v2
# (--providers default = gemini gpt higgsfield)

# Step 2: Claude agent가 8-step HF MCP 시퀀스 자동 실행 (default 동작)
#   ① 6 ref 업로드 (media_upload + PUT + media_confirm)
#   ② 4-concurrent로 5 batch (soul_2, nano_banana_2, gpt_image_2 × 6 = 18 jobs)
#   ③ rawUrl 다운로드 → {SCENE}_hf_soul.png / _hf_nano.png / _hf_gpt.png
#   ④ build_run_gallery.py 재실행 → gallery.html 갱신 + 자동 오픈
```

다른 브랜드/카테고리:
```bash
# MLB 27SS TEE — K-pop 키워드 자동 적용
python st_cut-dev/scripts/run_campaign_pipeline.py \
  --brand mlb --season-category "27SS TEE" --k 6 \
  --providers gemini gpt --mood-mode product

# Discovery 26FW WB — fitness 키워드 자동
python st_cut-dev/scripts/run_campaign_pipeline.py \
  --brand discovery --season-category "26FW WB" --k 6 \
  --providers gemini gpt --mood-mode product
```

---

## CLI 인자 (전체)

| 인자 | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `--brand` | ✓ | - | `duvetica` / `mlb` / `discovery` (`brand-dna/{brand}.json`) |
| `--season-category` | ✓ | - | `"27SS WJ"`, `"27SS TEE"`, `"26FW WB"` 등 |
| `--mood-mode` | | `marketing` | `marketing` (옷 정보 무시) / `product` (DNA 컬러+카테고리 가중) |
| `--k` | | 6 | 씬·레퍼런스 개수 |
| `--brand-filter` | | None | SNS 풀을 특정 account.brand로 제한 (예: duvetica) |
| `--confidence-floor` | | 0.7 | VLM 라벨 신뢰도 최소값 |
| `--providers` | | `gemini gpt higgsfield` | HF는 stub — Python은 트리거 문서만 떨어뜨리고, **Claude agent가 §"Higgsfield MCP 자동화"의 8-step를 즉시 실행하는 것이 default**. HF 빼려면 명시적으로 `--providers gemini gpt` |
| `--max-workers` | | 4 | ThreadPoolExecutor 병렬 수 |
| `--model` | | None | Gemini 이미지 모델 오버라이드 |
| `--no-images` | | False | Step A+B+B.5+갤러리만, 이미지 생성 건너뜀 |
| `--no-gallery` | | False | 갤러리 빌드 건너뜀 |
| `--no-open` | | False | 갤러리는 만들되 브라우저 자동 오픈 안 함 |
| `--selector` | | `v2` | `v2` (embedding + stratified + diversity, default) / `v1` (legacy top-K) |

**환경변수**:
- `GEMINI_API_KEY` (필수, `d:/ralph_kaphacy/.env`)
- `OPENAI_API_KEY` (gpt provider 사용 시 필수)
- `F_AND_F_IMAGE_MODEL` (Gemini 이미지, 기본 `gemini-3-pro-image-preview`)
- `F_AND_F_GPT_IMAGE_MODEL` (OpenAI, 기본 `gpt-image-2`)
- `F_AND_F_MOMENT_MODEL` (Step B.5, 기본 `gemini-3.1-flash-lite-preview`)
- `F_AND_F_VISION_MODEL` (라벨링용, 기본 `gemini-2.5-flash`)
- `F_AND_F_EMBEDDING_MODEL` (v2 셀렉터 임베딩, 기본 `gemini-embedding-2`)
- `F_AND_F_ALIGNMENT_MODEL` (alignment.json 빌더, 기본 `gemini-3.1-flash-lite-preview`)

---

## 출력 디렉토리 구조

```
st_cut-dev/results/{brand}/{mood-mode}/{timestamp}_auto_pipeline/
├── 01_references/                      Step A — 자동 셀렉된 추구미 K장
│   ├── ref_01_{post_id}.jpg
│   ├── ...
│   └── selection.json                  (점수 + 매칭 axes + mood_mode)
├── 02_proposal/                        Step B — 인플루언서 캠페인 제안서
│   ├── campaign_proposal.json          (Step B.5 후 moment 필드 포함)
│   └── campaign_proposal.md
├── 03_images/                          Step C — 5-provider 결과 + ref 사본 + 프롬프트
│   ├── {SCENE}_00_reference.jpg        ← Higgsfield 업로드용 ref
│   ├── {SCENE}_prompt.txt              ← THE MOMENT 라인 포함
│   ├── {SCENE}_gemini.png              (Direct Gemini-3-pro)
│   ├── {SCENE}_gpt.png                 (Direct GPT-image-2)
│   ├── {SCENE}_hf_soul.png             (HF Soul 2.0)
│   ├── {SCENE}_hf_nano.png             (HF Nano-Banana Pro)
│   ├── {SCENE}_hf_gpt.png              (HF GPT-image 2)
│   ├── _summary.json                   (Direct providers 통계)
│   ├── _hf_inputs.json                 (HF 호출용: scene_id → media_id + prompt)
│   └── higgsfield_manual_guide.md      (MCP 미연결 시 fallback)
└── gallery.html                        Step D — self-contained 한판 갤러리 (자동 오픈)
```

mood-mode 분리: `marketing_only/` (상품 무시) vs `product_aware/` (DNA 컬러+카테고리 가중).

---

## 핵심 코어 모듈

| Step | 파일 | 역할 |
|---|---|---|
| A | `scripts/sns_labeling/mood_query.py` | v1 (top-K 가중합) + **v2 (embedding + stratified + diversity)** |
| A' | `scripts/sns_labeling/mood_query_product.py` | product-aware 변형 (v1/v2 모두) |
| A.5 | `scripts/sns_labeling/build_alignment.py` | brand_dna ↔ pool taxonomy 1:N VLM 정렬 (`_{brand}_alignment.json`) |
| A.6 | `scripts/sns_labeling/embedder.py` + `embed_pool.py` | Gemini 임베딩 헬퍼 + 5,774장 1회 인코딩 (`_pool_embeddings.npz`) |
| A.7 | `scripts/sns_labeling/selector_v2.py` | v2 3-stage filter (handle dedup → stratified slot → axis-clash) |
| B | `scripts/sns_labeling/campaign_proposal.py` | 페르소나 / 씬 플랜 / 컬러 디렉션 빌더 |
| B.5 | `scripts/sns_labeling/moment_extractor.py` ★ | Gemini Vision으로 ref → moment 1줄 (병렬, fallback graceful) |
| C | `scripts/sns_labeling/image_providers.py` | Gemini + GPT + Higgsfield(stub) ThreadPoolExecutor 병렬 |
| C+ | `scripts/sns_labeling/image_gen.py` | Gemini 호출 + PROMPT_TEMPLATE (THE MOMENT 포함) + 브랜드 키워드 |
| D | `scripts/build_run_gallery.py` | self-contained HTML (refs + proposal + Brand DNA + Marketing DNA + 6-칼럼 씬 그리드) |
| 통합 | `scripts/run_campaign_pipeline.py` | A → B → B.5 → C → D 단일 CLI |

데이터 의존:
- 추구미 풀: `source/sns-influencer-output/labels_marketing_index.jsonl` (5,774 marketing-context 라벨)
  - product 모드는 `labels_adapted_index.jsonl` (items + common 포함) 사용
- brand DNA: `st_cut-dev/brand-dna/{brand}.json`
- 자사 제품 (참고용): `st_cut-dev/data/{brand}/official-site/` (현재 갤러리에 표시 X — 사용자 결정)

---

## Higgsfield MCP 자동화 흐름 (Claude Code agent 가 직접 실행)

**전제**: 사용자가 Claude Settings → Connectors에 `https://mcp.higgsfield.ai/mcp` 등록 완료.

**도구 목록** (자동 노출되는 deferred tools):
- `mcp__higgsfield__balance` (credit 확인)
- `mcp__higgsfield__list_workspaces` / `mcp__higgsfield__select_workspace`
- `mcp__higgsfield__media_upload` (presigned URL 발급, files: [{filename, content_type}])
- `mcp__higgsfield__media_confirm` (type="image", media_ids: [...])
- `mcp__higgsfield__generate_image` (params: {model, prompt, aspect_ratio, medias: [{role:"image", value: media_id}]})
- `mcp__higgsfield__job_status` (sync=true 권장)

**모델 ID** (`models_explore` action="recommend" 결과):
- `soul_2` — Higgsfield Soul 2.0 (UGC, fashion editorial, character)
- `nano_banana_2` — Google Nano Banana Pro (4K 가능, 고퀄리티)
- `gpt_image_2` — OpenAI GPT Image 2 (high-resolution editing)

**🚨 Pro 플랜 제약**: `max 4 concurrent jobs`. 18 generation은 **5 batch (4+4+4+4+2)** 로 분할.

**표준 호출 시퀀스** (Claude agent용):
```
1. mcp__higgsfield__select_workspace(workspace_id=<from list>)
2. mcp__higgsfield__media_upload(files=[6개 ref])
   → 6 presigned URL 받음
3. Python: urllib.request.urlopen(PUT) × 6 (실제 바이트 전송)
4. mcp__higgsfield__media_confirm(type="image", media_ids=[6])
5. for batch in [4, 4, 4, 4, 2]:
     - 각 시점에 ≤4 jobs concurrent
     - mcp__higgsfield__generate_image × N  (model: soul_2/nano_banana_2/gpt_image_2)
     - mcp__higgsfield__job_status(sync=true) × N
     - results.rawUrl 추출
6. Python: urllib.request.urlretrieve(rawUrl) → {SCENE}_hf_*.png
7. python st_cut-dev/scripts/build_run_gallery.py --run-dir <run_dir>
8. powershell.exe Start-Process <gallery.html>
```

씬별 prompt는 `03_images/{SCENE}_prompt.txt` 또는 컴팩트 템플릿(setting + moment swap):
```
DUVETICA 27SS WJ — Old Money Sportive. THE MOMENT: <moment>.
MODEL: professional high-fashion model, angular jawline, ... 20s-30s Asian/Western mix.
EXPRESSION: expressionless, gaze to camera. POSE: full body shot.
WEARING: hooded windbreaker, hood mandatory, lightweight technical fabric, beige/black centric.
SETTING: <setting>, earth-toned stone, terracotta, white plaster, rattan furniture. Natural warm golden hour. MOOD: chic.
STYLING: casual layered, neutral tone, sunglasses, straw bag, leather sandals.
PHOTOGRAPHY: Hasselblad 500CM, 85mm, Portra 400, film grain, 3:4 portrait.
Match reference's POSE/COMPOSITION/CAMERA ANGLE closely.
```

**비용**: 18장 ≈ 56 credits (pro 600 보유, 잔여 544+). 호출당 ~3 credits.

---

## 갤러리 (gallery.html) 섹션 구성

1. **헤더** — 브랜드 / 시즌 / 카테고리 / mood-mode / provider별 ok-fail-skip 통계
2. **§1 캠페인 개요** — Core message + Positioning + Brand moods
3. **§2 인플루언서 페르소나** — 연령/시그니처 무드/포즈/표정 + 지향/금지
4. **§3 컬러 디렉션** — BASE/KEY/ACCENT 비율 + 컬러명 (brand-dna 그대로)
5. **§4 카테고리 / 의류** — 매칭 카테고리 + 핵심 아이템 + 경쟁사 ref
6. **§5 Brand DNA** — silhouette / fabric / length / styling / setting / model / photography (7 카드)
7. **§6 Marketing DNA — 분포** — pose / expression / gaze / mood / vibe 분포 막대그래프 + 지향/금지 룰
8. **§7 추구미 풀** — K장 그리드 (rank / handle / 매칭 axes)
9. **§8 씬별 결과 — 6 칼럼**: REF / Gemini-3 / GPT-2 / HF-Soul / HF-Nano / HF-GPT
   - 씬 메타에 💭 _moment_ 한 줄 추가 노출

이미지 클릭 시 새 탭으로 원본 PNG 열림.

---

## 절대 규칙 (project-docs/prompt-strategy.md)

1. **DNA 분석은 JSON 스키마 기반** — `dna_schema.py` 사용, 자유형 금지
2. **브랜드별 모델 키워드 고정** — `image_gen.BRAND_MODEL_KEYWORDS`
   - DUVETICA: "professional high-fashion model, angular jawline, ..."
   - MLB: "K-pop girl group member on her day off — tiny small face, V-line jaw, ..."
   - DISCOVERY: "stunningly beautiful Korean fitness influencer — tiny face, ..."
3. **3모델 이상 병렬 생성** — 단일 모델 금지. 표준 5-provider (위 참고).
4. **추구미는 AI 자동 셀렉** — Plan A. 본 파이프라인이 그것.
5. **레퍼런스 가이드 방식** — `images.edit` 또는 inline_data로 ref 직접 첨부 (포즈/구도 유지).
6. **3:4 portrait 비율 강제** — 가로형 금지.

---

## 검증된 Run 인벤토리 (2026-05-02)

| 위치 | 모드 | scenes | providers | moment | 비고 |
|---|---|---|---|---|---|
| `duvetica/marketing_only/20260502_170317_auto_pipeline/` | marketing | 6 | gemini+gpt | ❌ | 첫 mood-mode 분기 시연 |
| `duvetica/product_aware/20260502_170819_auto_pipeline/` | product | 6 | gemini+gpt+HF×3 | ❌ | 18-image full 시연 (with HF) |
| `duvetica/product_aware/20260502_181610_auto_pipeline/` | product | 6 | gemini+gpt+HF×3 | ✅ | Step B.5 적용 first run (v1 라벨) |
| `mlb/product_aware/20260502_184318_auto_pipeline/` | product | 6 | gemini+gpt+HF×3 | ✅ | MLB 26SS TEE — 26SS season + tee garment fix 검증 |
| `mlb/product_aware/20260502_233312_auto_pipeline/` | product | 6 | gemini+gpt+HF×3 | ✅ | **셀렉터 v1 베이스라인** — 점수 spread 0, handle 중복 |
| `mlb/product_aware/20260503_001539_auto_pipeline/` | product | 6 | gemini+gpt | ✅ | **셀렉터 v2 검증** — spread 0.081, 6 unique handles, 4 mood. HF MCP disconnect로 직 12장만 |
| `discovery/product_aware/20260502_231026_auto_pipeline/` | product | 6 | gemini+gpt+HF×3 | ✅ | alignment.json 도입 후 첫 시연 |
| `labels_marketing_index.jsonl` (default) | — | 5,774 | gemini-3.1-flash-lite-preview | — | ✅ Track 1 적용 v2 (gaze/hair/skin/composition/color tone-filter 87~93% 충전). v1은 `labels_marketing_v1_index.jsonl` 백업. |
| `_pool_embeddings.npz` (v2 셀렉터용) | — | 5,774 × 3072 | gemini-embedding-2 | — | ✅ 1회 인코딩 65MB. 누락 시 v2가 자동으로 discrete-only fallback. |

`20260503_001539_*`이 현재 베스트 (셀렉터 v2). 사용자 비교 검토용으로 모두 보존.

---

## 트러블슈팅

| 증상 | 원인/대응 |
|---|---|
| `GEMINI_API_KEY not set` | `d:/ralph_kaphacy/.env`에 키 추가 후 재실행 |
| `OPENAI_API_KEY not set` | 동일. `--providers gemini` 만 사용도 가능 |
| `ClientError: 404 NOT_FOUND models/...` | `client.models.list()`로 모델 ID 확인 |
| Higgsfield `Rate limit reached: max 4 concurrent` | Pro 플랜 제약. 5 batch 분할 + 폴링 (이미 표준) |
| Higgsfield 다운로드 `403 Forbidden` | URL signing 만료. 같은 job 재폴링하면 새 URL |
| `cmd.exe start` 갤러리 안 열림 | 경로의 `)` 특수문자 이슈. `powershell -c "Start-Process '<path>'"` 사용 |
| 추구미 0장 | brand-filter 잘못, confidence-floor 너무 높음, marketing_dna 누락 |
| moment 생성 실패 | gemini-3.1-flash-lite-preview 응답 못 받음. fallback 문구 자동 적용 |
| v2 셀렉터에서 임베딩 0 | `_pool_embeddings.npz` 누락 → `python st_cut-dev/scripts/sns_labeling/embed_pool.py` 1회 실행 |
| HF MCP disconnect | Python은 `higgsfield_manual_guide.md` 만 떨어뜨림. MCP 연결되면 그 문서 읽고 8-step 자동 재실행 |
| HF 결과 mood가 brand-dna와 안 맞음 | nano_banana_2가 enhance_prompt로 prompt 무시. compact prompt template 사용 (가이드 문서 §"Compact prompt template") |

---

## 다음 라운드 후보 (현재 미적용)

- [ ] **Track 1: 5,774장 재라벨링** — gaze/hair/skin/composition/color tone 0% → 80% 충전
- [ ] **Track 2: brand-dna 어휘 매핑 정교화** — location/mood 매칭 정확도 ↑
- [ ] **검수 자동화 (Step E)** — 7-Gate VLM 검수 + FAIL시 재생성
- [ ] **다른 브랜드 시연** — MLB 27SS TEE / Discovery 26FW WB
- [ ] **scoring 다양성** — 같은 점수 동률 시 handle 다양성 가중치
