# Strategy-Cut Builder — Input Data Inventory

Code in this repo (`st_cut-dev/`) depends on several input artifacts that are **NOT tracked** here due to size and source-of-truth ownership. To reproduce a run, populate the layout below before invoking `run_campaign_pipeline.py`.

## Required layout (parent directory of this repo)

```
ST)MKT_builder_for_fnf/                 ← PROJECT_ROOT in code
├── st_cut-dev/                         ← THIS REPO (code + brand-dna)
├── marketing_builder/                  ← outside repo, holds imc_plan.json
│   ├── output/
│   │   ├── 20260503_DX_26FW/05_marketing/output/imc_plan.json
│   │   └── 20260503_MLB_27SS/05_marketing/output/imc_plan.json
│   └── samples/
│       └── 20260503_DV_27SS/05_marketing/output/imc_plan.json
├── products_resource/                  ← outside repo, ~200MB total
│   ├── DV/27SS WJ/, DV/27SS SET/
│   ├── DX/26FW WJ/, DX/26FW DJ/, DX/26FW SH/
│   └── MLB/27SS TS/, MLB/27SS PT/, MLB/27SS SH/
└── source/                             ← outside repo, influencer pool
    └── sns-influencer-output/
        ├── _pool_embeddings.npz        # 63MB — gemini-3-flash embeddings
        ├── labels_adapted_index.jsonl  # 20MB — per-image marketing labels
        └── _pool_taxonomy.json         # 4KB — label vocabulary
```

`PROJECT_ROOT` in code is computed as `Path(__file__).resolve().parents[3]` from `st_cut-dev/scripts/sns_labeling/...` and resolves to `ST)MKT_builder_for_fnf/`. All external paths in `_download_inputs.py` and selector_v3 are relative to that root.

## Input groups

### 1. influencer DB (selector_v3 input) — `~85MB`

| File | Purpose | Size |
|---|---|---|
| `source/sns-influencer-output/_pool_embeddings.npz` | precomputed gemini-3-flash embeddings for ~5,800 marketing-context Instagram posts | 63MB |
| `source/sns-influencer-output/labels_adapted_index.jsonl` | per-post metadata (handle, image path, age/gender, score axes, taxonomy labels) | 20MB |
| `source/sns-influencer-output/_pool_taxonomy.json` | controlled vocabulary used by the labeler | 4KB |
| `source/sns-influencer-output/{BRAND}/crawl_raw/thumbnails/{handle}/{post_id}.jpg` | actual Instagram thumbnail jpgs — referenced by absolute path in `labels_adapted_index.jsonl["image"]["path"]` | 991MB total (5,832 files across DV/DX/MLB) |

`selector_v3.py:DEFAULT_POOL` resolves to `source/sns-influencer-output/labels_marketing_index.jsonl` — make sure that file exists (or symlink to `labels_adapted_index.jsonl`).

**Known limitation — absolute thumbnail paths**: each label record has `image.path` baked as `D:/ralph_kaphacy/ST)MKT_builder_for_fnf/source/...`. To keep that working, either (a) clone the repo to that exact location on your machine, or (b) patch `selector_v3` and `run_campaign_pipeline` to derive `image.path` from `image.file` + `account.handle` + `account.brand` against `PROJECT_ROOT/source/...`. The Drive zips already restore the correct subtree under `source/sns-influencer-output/{BRAND}/crawl_raw/thumbnails/`, so option (a) just works as long as `PROJECT_ROOT` matches.

### 2. imc_plan.json (campaign brief) — `~5MB × N brands`

Output of the upstream `marketing_builder` agent (separate repo). Each campaign produces:

```
marketing_builder/output/{YYYYMMDD}_{BRAND}_{SEASON}/05_marketing/output/imc_plan.json
```

Contains: `brand`, `season`, `lifestyle`, `headline`, `keywords_3`, `categories.{hero,sub}`, `persona_groups`, `scenes`, `dna_grid`, `_meta`.

Format varies per brand:
- **MLB-style** (top-level fields): `brand`/`season`/`lifestyle` at root, `categories` inside `campaign_context`, `demo` is string
- **DV-style** (`_meta` envelope): `brand`/`season`/`lifestyle` inside `_meta`, `categories` at root, `demo` is dict

Both formats are handled by `imc_plan_loader.load_campaign_spec()`.

### 3. products_resource (try-on packshot fallback) — `~200MB`

Real-world product images organized by `BRAND/{SEASON} {CODE}/{LIFESTYLE_FOLDER}/`:

```
products_resource/MLB/27SS TS/Feminine Sportive/
  ├── representative_V1_src01_<color>.png    ← hero, picked first
  ├── V1_src01_<color>.png
  ├── V2_src01_<color>.png
  └── trend_*.jpg
```

`product_router.py:route_hero_product()` resolves the path from `(spec.brand, spec.season, spec.hero_garment.code, spec.lifestyle)`.

### 4. brand-dna (already tracked in repo) — `~1MB`

In-repo at `brand-dna/{discovery,duvetica,mlb}.json` + alignment files. No download needed.

## Producing the inputs

| Input | Producer |
|---|---|
| `_pool_embeddings.npz` + `labels_adapted_index.jsonl` | `st_cut-dev/scripts/sns_labeling/embed_pool.py` (one-off; ingest sns_classified_data → embed → label) |
| `imc_plan.json` | `marketing_builder` repo (`imc-plan` skill, run on a campaign brief) |
| `products_resource/{brand}/...` | F&F internal asset library (manual sync) |

## Distribution: Google Drive public link

All 12 inputs (~1.27 GB) live in a single shared Drive folder. `scripts/_download_inputs.py` fetches the folder once via `gdown.download_folder`, then places each artifact at the path the pipeline expects.

**Public folder**: https://drive.google.com/drive/folders/1VQF_Qldg3JhZJRi5DUYNWiyu6R6qdPzN

Folder layout (mirrors `_drive_upload_staging/`):

```
fnf-strategy-cut/  (Drive — "Anyone with the link can view")
  ├── influencer_pool/
  │     ├── _pool_embeddings.npz
  │     ├── labels_adapted_index.jsonl
  │     ├── _pool_taxonomy.json
  │     ├── thumbnails_DV.zip       (~215MB) — 1,354 raw .jpg referenced by absolute path in jsonl
  │     ├── thumbnails_DX.zip       (~390MB) — 2,323 jpg
  │     └── thumbnails_MLB.zip      (~369MB) — 2,155 jpg
  ├── imc_plans/
  │     ├── 20260503_DV_27SS_imc_plan.json
  │     ├── 20260503_DX_26FW_imc_plan.json
  │     └── 20260503_MLB_27SS_imc_plan.json
  └── products_resource/         (one zip per brand — gdown folder-mode caps
        ├── DV.zip                 at ~50 items, so brand zips beat raw folders)
        ├── DX.zip
        └── MLB.zip
```

### Bootstrap

```bash
pip install gdown
python st_cut-dev/scripts/_download_inputs.py            # dry-run, shows what's missing + sizes
python st_cut-dev/scripts/_download_inputs.py --apply    # download + place files
python st_cut-dev/scripts/_download_inputs.py --brand MLB --apply   # one brand only (still fetches the full folder, places only MLB)
```

The folder is fetched into `_drive_staging_tmp/` (sibling to st_cut-dev). Re-running with `--apply` reuses the existing staging — delete `_drive_staging_tmp/` for a fresh pull.

## Quick verification

After populating, sanity-check from the repo root:

```bash
python st_cut-dev/scripts/sns_labeling/imc_plan_loader.py \
    marketing_builder/output/20260503_MLB_27SS/05_marketing/output/imc_plan.json
```

Expected: brand/season/lifestyle parsed, 3 personas, 3 scenes with persona matches.
