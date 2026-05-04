# Strategy-Cut Builder (`st_cut-dev`)

F&F 마케팅컷 빌더 — IMC plan + 인플루언서 추구미 → 3 모델 AI 컷 + 실제 제품 try-on.

## Quick start (새 머신)

```bash
# 1. 클론 (반드시 D:\ralph_kaphacy\ST)MKT_builder_for_fnf\st_cut-dev 경로로 — 라벨 절대경로 호환)
git clone -b feature/hf-3model-orchestration \
  https://github.com/davidcho0326/content_builder.git \
  "D:\ralph_kaphacy\ST)MKT_builder_for_fnf\st_cut-dev"

cd "D:\ralph_kaphacy\ST)MKT_builder_for_fnf\st_cut-dev"

# 2. 의존성
pip install -r requirements.txt   # (없으면 핵심: gdown, pillow, requests, openai, google-genai, python-dotenv, playwright)
pip install gdown                 # 입력 자동 다운로드용

# 3. 환경변수 (.env at parent or st_cut-dev/)
#   OPENAI_API_KEY=sk-...
#   GEMINI_API_KEY=AIza...
#   F_AND_F_VTON_ROOT=c:/python/venv/fnf-image-gen-mcp-deploy   (try-on 외부 모듈)

# 4. 입력 데이터 자동 부트스트랩 (Drive 공개 폴더에서 ~1.27GB)
python scripts/_download_inputs.py            # dry-run, 무엇이 빠졌는지 표시
python scripts/_download_inputs.py --apply    # 실제 다운로드 + 자동 배치

# 5. 한 brand 시연 (예: MLB)
python scripts/run_campaign_pipeline.py \
  --imc-plan ../marketing_builder/output/20260503_MLB_27SS/05_marketing/output/imc_plan.json \
  --variants-per-scene 6 \
  --providers gpt --apply-tryon --tryon-multi --tryon-engines gpt --tryon-target gpt
```

결과는 `results/{brand}/imc_driven/{campaign_id}_{ts}/`에 생성, 마지막에 `gallery.html` 자동 오픈.

## 입력 데이터 (off-repo)

코드 외에 ~1.27GB의 입력 자산이 필요합니다 (인플루언서 임베딩 + 라벨 + thumbnail jpg + imc_plan + 제품 packshot). 모두 단일 Drive 공개 폴더에 들어있고 `scripts/_download_inputs.py`가 한 방에 받아옵니다.

**Drive 폴더**: <https://drive.google.com/drive/folders/1VQF_Qldg3JhZJRi5DUYNWiyu6R6qdPzN>

자세한 입력 명세 / 레이아웃 / 알려진 제약은 [`INPUTS.md`](./INPUTS.md) 참조.

## 브랜치

| 브랜치 | 용도 |
|---|---|
| `main` | v3.3 표준 (Direct GPT-image-2 only, IMC + multi-tryon) |
| `feature/raw-only-no-tryon` | Step C → Step D 직행 변형 (try-on 생략) |
| `feature/product-aware-stepC` | v3.4 product-aware 실험 (보류) |
| `feature/hf-3model-orchestration` | v3.5 PoC — HF 3-model (GPT-image-2 + nano-banana-pro + Marketing Studio) + gpt-image-2 try-on. 본 README가 속한 브랜치 |

## 재현된 결과 (3 brand × 108 image)

`feature/hf-3model-orchestration`에서 검증 완료:

- **DV 27SS Premium_Resort** — Sky Blue WJ hero swap
- **DX 26FW Active_Wellness** — Powder Blue WJ hero swap
- **MLB 27SS Feminine_Sportive** — LA cursive TS hero swap (multi-tryon: TS+WP)

각 brand × (18 ref + 54 HF raw + 54 try-on) = **378 이미지** / 0 fail.

## 더 읽을거리

- [`GUIDE.md`](./GUIDE.md) — 시스템 전체 핸드오프 가이드 (PM 관점)
- [`INPUTS.md`](./INPUTS.md) — 입력 데이터 명세 + Drive 부트스트랩
- `skills/strategy-cut-pipeline/SKILL.md` — 파이프라인 단계별 상세
- `brand-dna/{discovery,duvetica,mlb}.json` — 브랜드 DNA 정의
