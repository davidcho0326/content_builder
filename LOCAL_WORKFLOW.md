# Local Workflow

This checkout can run as a standalone Strategy Cut Builder. The code resolves
runtime paths from this repository by default, without requiring a parent
`st_cut-dev` folder.

## Install

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill keys when running real image generation.

## Smoke Test

Runs the IMC workflow through reference selection, proposal creation, and HTML
gallery rendering. It does not call paid image APIs.

```bash
python scripts\run_campaign_pipeline.py ^
  --imc-plan examples\imc_plan.sample.json ^
  --variants-per-scene 2 ^
  --no-images ^
  --no-open
```

Expected output:

- `results/mlb/imc_driven/{campaign_id}_{timestamp}/00_imc_snapshot.json`
- `01_references/selection.json`
- `02_proposal/campaign_proposal.json`
- `02_proposal/campaign_proposal.md`
- `gallery.html`

## Single-Product Image Run

The default IMC flow is now single-product grounded:

1. Resolve exactly one selected product: either a top or a bottom.
2. Attach the influencer reference + selected product only to GPT-image-2.
3. Treat the influencer reference as the pose/composition authority.
4. Treat the product image as fit/length/detail guidance only, ignoring any
   person, pose, background, or styling in the product photo.
5. Generate the remaining garment, bag, shoes, accessories, and props from the
   campaign tone.

Virtual try-on is no longer the default post-process.

```bash
python scripts\run_campaign_pipeline.py ^
  --imc-plan path\to\imc_plan.json ^
  --variants-per-scene 6 ^
  --providers gpt hf_gpt hf_mkt ^
  --no-open
```

Outputs include:

- `04_products/outfit_manifest.json`
- `04_products/selected_product_used.png`
- `04_products/hero_product_used.png` or `bottom_product_used.png`, depending
  on the selected role
- `03_images/{scene}_R{rank}_gpt.png`
- `03_images/higgsfield_mcp_plan.json` and `.md` when `hf_gpt` or `hf_mkt`
  are requested. Run that plan in a session with Higgsfield MCP connected to
  fill `{scene}_R{rank}_hf_gpt.png` and `{scene}_R{rank}_hf_mkt.png`.

Required:

- `OPENAI_API_KEY` for GPT-image-2 image generation.
- `GEMINI_API_KEY` for Gemini-based moment extraction or embeddings.
- `products_resource/` if you want Step C+ virtual try-on to find real product
  packshots or product-grounded generation to attach product images. Without it,
  the image generation falls back to the written wardrobe brief.

Optional comparison/debug try-on:

```bash
python scripts\run_campaign_pipeline.py ^
  --imc-plan path\to\imc_plan.json ^
  --variants-per-scene 3 ^
  --providers gpt ^
  --apply-tryon ^
  --no-open
```

Optional path overrides:

- `STRATEGY_CUT_SOURCE_DIR`
- `STRATEGY_CUT_BRAND_DNA_DIR`
- `STRATEGY_CUT_PRODUCTS_DIR`
- `STRATEGY_CUT_RESULTS_DIR`
