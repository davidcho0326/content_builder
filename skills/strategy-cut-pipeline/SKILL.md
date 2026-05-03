---
name: strategy-cut-pipeline
description: marketing_builder의 imc_plan.json 한 파일을 인풋으로 받아 → 페르소나별 인플루언서 ref 자동 셀렉 → 씬-aware 캠페인 제안서 → 씬 × ref별 moment 자동 추출 → 3-model 병렬 이미지 생성 → 한판 갤러리(라이트박스) 자동 오픈. F&F 마케팅컷 빌더 v3.1 IMC-driven.
user-invocable: true
trigger-keywords:
  - "캠페인 만들어"
  - "전략컷 파이프라인"
  - "imc 캠페인"
  - "마케팅컷 만들어"
  - "캠페인 갤러리"
  - "strategy cut pipeline"
  - "auto campaign"
  - "DUVETICA 캠페인"
  - "MLB 캠페인"
  - "Discovery 캠페인"
---

# Strategy-Cut Pipeline (마케팅컷 자동 빌더, v3.1 IMC-driven)

> **`imc_plan.json` 한 파일만 받아** persona별 ref 셀렉 → IMC-aware 제안서 → 씬×ref moment 추출 → **3-model 병렬 이미지 생성** → scene-grouped 갤러리(라이트박스) 자동 오픈까지 완전 자동화.
>
> 검증 완료 (2026-05-03): MLB 27SS Feminine_Sportive × 18 refs × 3 models = 표준 산출물.

```
imc_plan.json
   ↓ Step A) Per-scene reference selection           (selector_v3, persona+pose anchor)
   ↓ Step B) IMC proposal                            (campaign + scenes + influencer_categories)
   ↓ Step B.5) THE MOMENT extraction                 (gemini-3.1-flash-lite, IMC-aware moments)  ★
   ↓ Step C) 3-model image generation                (GPT-image-2 Direct + HF GPT-image 2 + HF Marketing Studio)
   ↓ Step C+) Virtual try-on (hero product swap)     (Gemini-3-pro-image + GPT-image-2 두 엔진)  ★ v3.2
   ↓ Step D) Scene-grouped gallery + lightbox        (자동 오픈)
```

---

## 🚨 사용 모델 — 3개로 표준화 (2026-05-03 결정)

| 채널 | 모델 | 비고 |
|---|---|---|
| Direct | **GPT-image-2** (OpenAI `gpt-image-2`, via `client.images.edit`) | 메인 Direct 산출물 |
| HF MCP | **GPT-image 2** (`gpt_image_2`) | high-resolution editing |
| HF MCP | **Marketing Studio** (`marketing_studio_image`) | 커머셜/제품/광고 톤에 최적 |

**드롭된 모델** (사용 안 함):
- ~~Gemini-3-pro-image-preview (Direct)~~ — 활용도 대비 불필요
- ~~HF Soul 2.0 (`soul_2`)~~ — `enhance_prompt: true`로 캠페인 의도 무시 (off-brief)
- ~~HF Nano-Banana Pro (`nano_banana_2`)~~ — 위 3모델 외 보류

표준 산출물: 3 scenes × N variants × 3 models = **3 × 6 × 3 = 54장** (variants=6 기본).

---

## Quick Start

```bash
cd /d/ralph_kaphacy/ST\)MKT_builder_for_fnf

# v3.1 IMC-driven (default)
python st_cut-dev/scripts/run_campaign_pipeline.py \
  --imc-plan marketing_builder/output/20260503_MLB_27SS/05_marketing/output/imc_plan.json \
  --variants-per-scene 6 \
  --providers gpt \
  --max-workers 4
# (Direct = GPT-image-2 only. HF는 Step C 후 Claude agent가 MCP로 자동 실행)

# Step C+ : Claude agent가 HF MCP 시퀀스 자동 실행
#   ① 18 ref 일괄 업로드 (media_upload + PUT + media_confirm)
#   ② 4-concurrent batch로 18 refs × 2 models (gpt + mkt) = 36 jobs
#   ③ rawUrl 다운로드 → {scene_slug}_R{NN}_hf_gpt.png / _hf_mkt.png
#   ④ build_run_gallery.py --imc 재실행 → gallery.html 갱신
```

레거시 정적 모드 (회귀/비교 전용):
```bash
python st_cut-dev/scripts/run_campaign_pipeline.py \
  --legacy-static --brand mlb --season-category "27SS TEE" --k 6 \
  --brand-filter mlb --providers gpt --selector v2 --mood-mode product
```

---

## CLI 인자

| 인자 | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `--imc-plan` | ✓ (default 모드) | None | `marketing_builder/output/{campaign}/05_marketing/output/imc_plan.json` 경로. v3.1 IMC-driven 모드 트리거 |
| `--variants-per-scene` | | 6 | 씬당 ref 개수 (3 scenes × N = 총 ref 수) |
| `--providers` | | `gpt` | Direct providers (현재 표준은 `gpt`). HF는 별도 MCP 단계 |
| `--max-workers` | | 4 | ThreadPoolExecutor 병렬 수 |
| `--no-images` | | False | Step C 건너뜀 (Step A/B/B.5/D만) |
| `--no-gallery` | | False | 갤러리 빌드 건너뜀 |
| `--no-open` | | False | 갤러리 만들고 자동 오픈 안 함 |
| `--confidence-floor` | | 0.7 | VLM 라벨 신뢰도 최소값 |
| `--legacy-static` | | False | 옛 brand-DNA + season-category 모드로 fallback |
| `--brand` | (legacy) | - | `--legacy-static` 필요 |
| `--season-category` | (legacy) | - | `--legacy-static` 필요 |
| `--k` | (legacy) | 6 | 레거시 모드 씬 개수 |
| `--mood-mode` | (legacy) | `marketing` | `marketing` / `product` |
| `--selector` | (legacy) | `v2` | `v1` / `v2` |
| `--brand-filter` | (legacy) | None | account.brand 필터 |

**환경변수**:
- `OPENAI_API_KEY` (필수, GPT-image-2 호출용. `.env`에 보관)
- `GEMINI_API_KEY` (Step B.5 moment + 임베딩에 필요)
- `F_AND_F_GPT_IMAGE_MODEL` (기본 `gpt-image-2`)
- `F_AND_F_MOMENT_MODEL` (기본 `gemini-3.1-flash-lite-preview`)
- `F_AND_F_VISION_MODEL` (라벨링용, 기본 `gemini-2.5-flash`)
- `F_AND_F_EMBEDDING_MODEL` (selector v3 임베딩, 기본 `gemini-embedding-2`)
- `F_AND_F_ALIGNMENT_MODEL` (alignment.json 빌더, 기본 `gemini-3.1-flash-lite-preview`)

---

## imc_plan.json 활용 매트릭스

`marketing_builder`가 산출한 imc_plan.json에서 추출 → 어디에 반영되는지:

| imc_plan 필드 | Selector v3 | Moment LLM | Image Prompt | Proposal/Gallery |
|---|:---:|:---:|:---:|:---:|
| `brand`, `season`, `lifestyle` | — | ✅ | ✅ | ✅ |
| `headline.{en_main, ko_sub}` | — | ✅ | ✅ | ✅ |
| `keywords_3[]` | — | ✅ | ✅ (CSV anchor) | ✅ |
| `campaign_context.categories.{hero, sub}` | — | — | ✅ ("WEARING") | ✅ |
| `persona_groups[].demo` (age/gender) | ✅ ★ 핵심 | ✅ | ✅ ("THE MODEL") | ✅ |
| `persona_groups[].jtbd` | ✅ (lifestyle hint, 0.15) | — | — | ✅ |
| `scenes[].{tone, mood, visual, location, title}` | — | ✅ | ✅ ("SCENE/TONE/MOOD/...") | ✅ |
| `scenes[]` 키워드 → `persona_match` 추론 | ✅ (G1/G2/G3 라우팅) | ✅ | ✅ | ✅ |
| **`influencer_tiers[*].categories`** (14개 평탄화) | — | ✅ | ✅ ("TARGET INFLUENCER PROFILE") | ✅ |

**의도적 제외** (셀럽/운영 영역, 우리 책임 아님):
`celeb_matrix`, `narrative_arc`, `content_layers_3`, `media_split`, `promotions`, `outcome_funnel`, `outcome_kpi_6`, `core_kpi`, `strategic_position`, `global_sub_module`, `risks`, `ai_final_decision`, `campaign_context.{period, ooh, budget_included}`.

---

## 출력 디렉토리 구조 (v3.1 IMC-driven)

```
st_cut-dev/results/{brand}/imc_driven/{campaign_id}_{ts}/
├── 00_imc_snapshot.json               (입력 imc_plan.json 사본 — 재현성)
├── 01_references/                     Step A — persona별 18 refs (3 scenes × 6 variants)
│   ├── {scene_slug}_R{NN}_{post_id}.jpg
│   └── selection.json
├── 02_proposal/                       Step B — IMC-aware 제안서
│   ├── campaign_proposal.json         (schema_version: imc-1.0)
│   └── campaign_proposal.md
├── 03_images/                         Step C — 3 모델 산출물 + 프롬프트
│   ├── {scene_slug}_R{NN}_gpt.png         (Direct GPT-image-2)
│   ├── {scene_slug}_R{NN}_hf_gpt.png      (HF GPT-image 2)
│   ├── {scene_slug}_R{NN}_hf_mkt.png      (HF Marketing Studio)
│   ├── {scene_slug}_R{NN}_prompt.txt      (full prompt with TARGET INFLUENCER 포함)
│   └── _summary.json                      (Direct 통계)
└── gallery.html                       Step D — scene-grouped 3-row + 라이트박스
```

`{scene_slug}` = `S01_cheer_line` / `S02_daylight_wave` / `S03_dugout_backstage` 등 (imc_plan.scenes의 title slugify).

---

## 핵심 코어 모듈

| Step | 파일 | 역할 |
|---|---|---|
| 0 | `scripts/sns_labeling/imc_plan_loader.py` | imc_plan.json → CampaignSpec / Scene / Persona dataclass. SCENE_PERSONA_HINTS + INFLUENCER_CATEGORY_TO_PERSONA 정적 라우팅 |
| A | `scripts/sns_labeling/selector_v3.py` ★ | **Option α** persona+pose anchor 셀렉터. weight: persona_demo 0.50 + pose_quality 0.35 + lifestyle_hint 0.15. setting/mood/tone은 0% (LLM 합성에 위임) |
| A.6 | `scripts/sns_labeling/embedder.py` + `embed_pool.py` | gemini-embedding-2 임베딩 + 5,774장 1회 캐시 (`_pool_embeddings.npz`) |
| B | `scripts/sns_labeling/campaign_proposal.py` `build_imc_proposal` | CampaignSpec + refs → 3-scene 제안서 (schema imc-1.0) |
| B.5 | `scripts/sns_labeling/moment_extractor.py` `extract_moments_for_imc` ★ | scene + ref → moment 1줄 (캠페인/씬/인플루언서 컨텍스트 주입) |
| C | `scripts/sns_labeling/image_providers.py` `generate_campaign_imc` | Direct (gpt 표준) ThreadPoolExecutor 병렬. HF는 별도 MCP. |
| C+ | `scripts/sns_labeling/image_gen.py` `build_prompt_from_imc_scene` | IMC PROMPT_TEMPLATE: CAMPAIGN/HEADLINE/SCENE/TONE/MOOD/LOCATION/VISUAL/**TARGET INFLUENCER PROFILE**/MOMENT/MODEL/WEARING |
| D | `scripts/build_run_gallery.py` `render_imc` | 3-scene 그룹 레이아웃 + 라이트박스 (클릭 확대, ESC/화살표) |
| 통합 | `scripts/run_campaign_pipeline.py` `_run_imc_pipeline` | `--imc-plan` flag → loader → selector_v3 → moment → proposal → image_providers → gallery |

데이터 의존:
- 추구미 풀: `source/sns-influencer-output/labels_marketing_index.jsonl` (5,774 marketing-context 라벨)
- 임베딩 캐시: `source/sns-influencer-output/_pool_embeddings.npz` (5,774 × 3072 float32)
- imc_plan: `marketing_builder/output/{campaign_id}/05_marketing/output/imc_plan.json`
- (legacy 모드 한정) brand DNA: `st_cut-dev/brand-dna/{brand}.json`

---

## Step C+ Virtual Try-On (v3.2, 2026-05-03 도입)

이미지 생성(Step C) 결과 위에 한 단계 더 — `products_resource/{brand}/{season} {code}/{lifestyle}/` 의 **실제 자사 제품 이미지**를 가져와 **모델·포즈·배경은 그대로 두고 옷만** 실제 제품으로 swap.

### 두 엔진 dual-run

| 엔진 | 모델 | 호출 방식 | 출력 명명 |
|---|---|---|---|
| A | **Gemini-3-pro-image-preview** | 외부 `c:/python/venv/fnf-image-gen-mcp-deploy/core/virtual_tryon` 모듈 import (검증된 prompt 5단계 + ABSOLUTE PRESERVATION) | `{unit}_{provider}_tryon_gemini.png` |
| B | **GPT-image-2** | OpenAI `images.edit` 신규 호출, `image=[model, product]` 멀티 이미지 첨부 | `{unit}_{provider}_tryon_gpt.png` |

같은 (model_image, product_image, prompt) 입력으로 두 엔진 동시 실행 → 갤러리에서 cell 2개로 나란히 비교 가능.

### 제품 라우팅 (`product_router.py`)

imc_plan의 `brand` + `season` + `lifestyle` + `hero_garment.code` → products_resource 폴더/파일 deterministic 매핑:

| 매핑 단계 | 룰 |
|---|---|
| brand | `mlb`/`MLB` → `MLB`, `duvetica` → `DV`, `discovery` → `DX` |
| season | imc_plan.season 그대로 (`27SS`, `26FW`) |
| code | imc 코드 → 폴더 코드. **alias**: `WP→PT` (와이드팬츠≈Pants), `TS/SH/WJ/DJ/SET` 그대로 |
| lifestyle | exact slug → substring → word overlap → first folder fallback |
| hero file | `representative_*.png` → `V1_src01_*.png` → `V1_src02_*.png` → first `*.png` |

매칭 결과는 `04_products/hero_product.json` 으로 영구화 (재현성).

### CLI flag

| 인자 | 기본값 | 설명 |
|---|---|---|
| `--apply-tryon` / `--no-tryon` | `True` | Step C+ 실행 여부 (default ON) |
| `--tryon-engines` | `gemini gpt` | 두 엔진 동시 실행 (default). 단독 실행 가능 |
| `--tryon-target` | `gpt` | 어느 raw provider 결과에 try-on 적용. `gpt` (Direct GPT-image-2 18장만, 권장) / `hf_gpt` / `hf_mkt` / `all` |

### 비용 견적 (default `gpt` target × 2 engines)

- 18 generated × 2 엔진 = 36 try-on
- Gemini-3-pro-image: ~$0.05 × 18 = ~$0.9
- GPT-image-2: ~$0.05 × 18 = ~$0.9
- VLM analyze_product/model: ~$0.1
- **Total: ~$1.9/run**

`--tryon-target all` 로 확장 시 54×2 = 108 try-on (~$5.7).

### 출력 디렉터리 (Step C+ 추가)

```
results/{brand}/imc_driven/{campaign_id}_{ts}/
├── 03_images/
│   ├── {unit}_gpt.png                       (raw Step C)
│   ├── {unit}_gpt_tryon_gemini.png          (Step C+ Engine A)
│   ├── {unit}_gpt_tryon_gpt.png             (Step C+ Engine B)
│   ├── {unit}_hf_gpt.png / {unit}_hf_mkt.png (raw Step C)
│   └── _tryon_summary.json                  (engine별 ok/fail/elapsed)
├── 04_products/                              (Step C+ 신규)
│   ├── hero_product.json                    (resolved 매니페스트)
│   └── hero_product_used.png                (선택된 제품 이미지 사본)
└── gallery.html                              (variant row에 try-on cell 추가, hero thumb)
```

### 갤러리 레이아웃 변화

variant row가 **4 cell → 6 cell**:
```
[ref] [gpt] [gpt-tryon-Gemini] [gpt-tryon-GPT] [hf_gpt] [hf_mkt]
```
- try-on 셀은 `.cell.tryon` 클래스로 accent 보더 강조
- 헤더에 hero product 썸네일 + 매니페스트 정보 (TRY-ON HERO 배지)
- 라이트박스 좌우 화살표가 6 cell 모두 순회

### 의존성

- **외부 모듈**: `c:/python/venv/fnf-image-gen-mcp-deploy/core/virtual_tryon` (sys.path 주입). env override: `F_AND_F_VTON_ROOT`
- **API 키**: `GEMINI_API_KEY` (Engine A), `OPENAI_API_KEY` (Engine B)
- **graceful skip**: virtual_tryon import 실패 → Engine A skip, Engine B만 실행

---

## Higgsfield MCP 자동화 (Claude agent 직접 실행 — 2 모델만)

**전제**: 사용자 Settings → Connectors에 `https://mcp.higgsfield.ai/mcp` 등록.

**도구 목록**:
- `mcp__higgsfield__balance` (credit 확인)
- `mcp__higgsfield__select_workspace` / `list_workspaces`
- `mcp__higgsfield__media_upload` (presigned URL 발급, files: [{filename, content_type}])
- `mcp__higgsfield__media_confirm` (type="image", media_ids: [...])
- `mcp__higgsfield__generate_image` (params: {model, prompt, aspect_ratio, medias: [{role:"image", value: media_id}]})
- `mcp__higgsfield__job_status` (sync=true 권장)

**모델 ID** (현 표준 — 2개만):
- `gpt_image_2` — OpenAI GPT Image 2 (high-resolution editing)
- `marketing_studio_image` — Higgsfield Marketing Studio (commercial/product/ads tone)

**🚨 Pro 플랜 제약**:
- `max 4 concurrent jobs` — 18 refs × 2 models = 36 jobs를 9 batch (4+4+4+4+4+4+4+4+4)로 분할
- credits 잔량 미리 확인 (`mcp__higgsfield__balance`). 36 jobs ≈ 100~120 credits

**표준 호출 시퀀스**:
```
1. mcp__higgsfield__balance  (credits 확인)
2. mcp__higgsfield__media_upload(files=[18 ref])
3. urllib PUT × 18 (parallel)
4. mcp__higgsfield__media_confirm(type="image", media_ids=[18])
5. for batch in 9 batches of 4:
     - mcp__higgsfield__generate_image × ≤4
       (model: gpt_image_2 or marketing_studio_image,
        aspect_ratio: "3:4",
        medias: [{role:"image", value: media_id}],
        prompt: 03_images/{unit}_prompt.txt 내용)
     - mcp__higgsfield__job_status(sync=true) × ≤4
6. urlretrieve rawUrl × 36 → 03_images/{scene_slug}_R{NN}_hf_{gpt|mkt}.png
7. python st_cut-dev/scripts/build_run_gallery.py --run-dir <run_dir> --imc
8. powershell.exe Start-Process <gallery.html>
```

**프롬프트는 condensed 버전 권장** (~800 chars):
```
MLB 27SS Feminine Sportive editorial. SCENE: {scene.location}.
TARGET INFLUENCER: {scene.influencer_categories_match}.
THE MOMENT: {moment}
TONE: {scene.tone}.  MOOD: {scene.mood}.
VISUAL: {scene.visual}.
WEARING: {hero_garment.desc} + {sub_garments[*]}.
Adult fashion model, full body shot, 3:4 portrait. Match REFERENCE pose only — replace setting/clothing.
```

**NSFW 회피**: GPT-image-2가 가끔 "Korean female 20-24" 같은 조합에서 false-positive NSFW. neutral 표현(`adult fashion model`)으로 재시도하면 통과.

---

## 갤러리 (gallery.html) — Scene-Grouped + 라이트박스

3 scene-card 세로 스택. 각 scene-card:
- 헤더: SCENE n · Title + persona G1/G2/G3 정보
- 메타 그리드: Tone / Mood / Location / Visual / **Target Influencer**
- variant rows: REF 이미지 + 3 model 셀 (`GPT-image-2 / HF GPT-image 2 / HF Marketing Studio`)
  - 각 row 헤더에 prompt.txt 링크
  - REF 셀에 moment 인용 표시

**라이트박스**: 모든 이미지 클릭 → 화면 가득 확대 (~1400px / 96vw). 좌우 화살표/← →로 이전/다음 이미지 순회. ESC / 배경클릭 / 확대 이미지 재클릭 / × 버튼으로 닫기. 상단 카운터 + Scene·Variant·Provider 캡션 자동 표시.

---

## Architecture Decision (Option α — 확정)

**Selector 역할**: 포즈/구도/페르소나 외형(연령·성별)만 anchor. setting/mood/tone은 LLM 프롬프트 합성에 위임.

| 책임 | 담당 | 비고 |
|---|---|---|
| 포즈, 구도, 카메라 앵글 | Selector → ref image | 풀의 `pose`, `gaze direction`, `shooting composition` 라벨 + 임베딩 |
| 페르소나 외형 (연령·성별) | Selector → ref image | persona.demo (age range + gender) 매칭 |
| Setting/Mood/Tone/Visual | Image gen 프롬프트 → LLM | imc_plan.scenes[i] 텍스트를 그대로 LLM에 전달 |
| 캠페인 의도 (Headline/Keywords/Garment/Influencer profile) | Image gen 프롬프트 → LLM | imc_plan에서 추출 |

**ref attachment 지시문** (프롬프트 CRITICAL):
> "Match REFERENCE's POSE / COMPOSITION / CAMERA ANGLE precisely. The model's SETTING, COLOR PALETTE, CLOTHING, and ACCESSORIES must match the SCENE BRIEF — NOT the reference image."

---

## 절대 규칙

1. **DNA 분석은 JSON 스키마 기반** — 자유형 금지
2. **브랜드별 모델 키워드 고정** — `image_gen.BRAND_MODEL_KEYWORDS`
   - DUVETICA: 영국 / 유럽 코카시안 영케이스(any gender), porcelain skin, light eyes
   - MLB: K-pop girl group day off — V-line jaw, dewy glass skin
   - DISCOVERY: Korean fitness influencer — toned but feminine athletic build
3. **3 모델 병렬 생성** (현 표준): GPT-image-2 + HF GPT-image 2 + HF Marketing Studio
4. **추구미는 AI 자동 셀렉** — selector_v3 (persona+pose anchor)
5. **레퍼런스는 포즈 anchor만** — setting/clothing은 SCENE BRIEF로 덮어쓰기
6. **3:4 portrait 강제** — 가로형 금지

---

## 검증된 Run 인벤토리 (v3.1 IMC-driven, 2026-05-03)

| 위치 | mode | refs | models | 비고 |
|---|---|---|---|---|
| `mlb/imc_driven/20260503_MLB_27SS_20260503_174941/` | imc | 6 (3 scenes × 2) | gemini+gpt | v3.0 첫 시연 (variants=2) |
| `mlb/imc_driven/20260503_MLB_27SS_20260503_175528/` | imc | 18 (3 × 6) | gemini+gpt + HF Soul/Nano/GPT/MKT | **v3.0 풀스케일** — 95장 (Soul off-brief 발견) |
| `mlb/imc_driven/20260503_MLB_27SS_20260503_185657/` | imc | 18 (3 × 6) | gemini+gpt + HF GPT/MKT/Nano | **v3.1 풀스케일** — TARGET INFLUENCER 라인 + Soul 제외 + 라이트박스. 71장 |
| `_pool_embeddings.npz` | — | 5,774 × 3072 | gemini-embedding-2 | 1회 인코딩 65MB |

`20260503_185657_*`이 현재 베스트 (v3.1, 3-model 표준 직전 단계). 다음 라운드부터 GPT-image-2 + HF GPT/MKT 3-model 표준.

---

## 트러블슈팅

| 증상 | 원인/대응 |
|---|---|
| `OPENAI_API_KEY not set` | `.env`에 키 추가 후 재실행 |
| `imc-plan not found` | 경로 확인. `marketing_builder/output/{campaign}/05_marketing/output/imc_plan.json` |
| `not an imc-1.0 proposal` | 갤러리 렌더 시 — 레거시 모드 산출물에 `--imc` flag를 쓴 경우. flag 제거하면 legacy gallery로 떨어짐 |
| Higgsfield `Rate limit reached: max 4 concurrent` | Pro 플랜 제약. 9 batch 분할 + 폴링 |
| Higgsfield `Out of credits` | 잔액 0. 다음 라운드 또는 plan upgrade |
| GPT-image-2 NSFW false-positive | neutral 표현으로 재시도 (`adult fashion model` instead of `Korean female 20-24`) |
| 다운로드 `403 Forbidden` | rawUrl signing 만료. 같은 job 재폴링하면 새 URL |
| `cmd.exe start` 갤러리 안 열림 | 경로의 `)` 특수문자. `powershell -c "Start-Process '<path>'"` 사용 |
| ref 0장 셀렉됨 | confidence-floor 너무 높음 또는 imc_plan persona.demo 파싱 실패 |
| moment 생성 실패 | gemini-3.1-flash-lite 응답 X. fallback 문구 자동 적용 |
| 임베딩 캐시 누락 | `python st_cut-dev/scripts/sns_labeling/embed_pool.py` 1회 실행 |

---

## 다음 라운드 후보

- [ ] **3-model default 코드 반영** — `image_providers.IMC_PROVIDER_FUNCS`를 gpt-only로, HF 2-model orchestrator 함수화
- [ ] **검수 자동화 (Step E)** — 7-Gate VLM 검수 + FAIL시 재생성
- [ ] **다른 imc_plan 캠페인 시연** — Discovery / Duvetica / 다른 시즌
- [ ] **Cross-campaign A/B** — 같은 brand 다른 시즌 imc_plan 비교
- [ ] **HF 잔여 model 평가** — `seedance-1`, `flux_kontext_pro` 등 추가 시도 (현재는 gpt+mkt만 표준)
