"""End-to-end Strategy-Cut pipeline:

    brand_dna + season/category
        -> [Step A] mood reference auto-select
        -> [Step B] influencer campaign proposal (intermediate human-readable)
        -> [Step C] Gemini image generation (3:4 campaign cuts)

CLI:
    python st_cut-dev/scripts/run_campaign_pipeline.py \\
        --brand duvetica --season-category "27SS WJ" --k 6 \\
        [--brand-filter duvetica] [--no-images] [--max-workers 3]

Outputs go to:  st_cut-dev/results/{brand}/{timestamp}_auto_pipeline/
    01_references/        K refs + selection.json
    02_proposal/          campaign_proposal.json + .md
    03_images/            {scene}_gemini.png + _prompt.txt + _00_reference.jpg + _summary.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

_THIS = Path(__file__).resolve()
_SCRIPTS = _THIS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from sns_labeling.campaign_proposal import (
    build_campaign_proposal,
    proposal_to_markdown,
)
from sns_labeling.mood_query import query_marketing_pool, query_marketing_pool_v2
from sns_labeling.mood_query_product import (
    query_marketing_pool_product,
    query_marketing_pool_product_v2,
)
from sns_labeling.image_providers import generate_campaign_multi
from sns_labeling.moment_extractor import extract_moments_for_scenes

from build_run_gallery import render as render_gallery

PROJECT_ROOT = _THIS.parents[2]
BRAND_DNA_DIR = PROJECT_ROOT / "st_cut-dev" / "brand-dna"
RESULTS_DIR = PROJECT_ROOT / "st_cut-dev" / "results"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Run strategy-cut auto pipeline")
    ap.add_argument("--brand", required=True,
                    help="duvetica | mlb | discovery (matches brand-dna/{brand}.json)")
    ap.add_argument("--season-category", required=True,
                    help='e.g. "27SS WJ", "27SS SETUP", "26FW WINDBREAKER"')
    ap.add_argument("--k", type=int, default=6, help="number of refs / scenes")
    ap.add_argument("--brand-filter", action="append", default=None,
                    help="restrict ref pool to this account.brand (can repeat)")
    ap.add_argument("--confidence-floor", type=float, default=0.7)
    ap.add_argument("--no-images", action="store_true",
                    help="skip Step C (image generation), only build refs+proposal")
    ap.add_argument("--providers", nargs="+",
                    default=["gemini", "gpt", "higgsfield"],
                    choices=["gemini", "gpt", "higgsfield"],
                    help="image-gen providers (default: all three). "
                         "higgsfield emits a manual guide + per-scene prompts "
                         "and then must be executed via Claude HF MCP — see SKILL.md")
    ap.add_argument("--max-workers", type=int, default=4)
    ap.add_argument("--model", default=None, help="image model override (gemini)")
    ap.add_argument("--no-gallery", action="store_true",
                    help="skip HTML gallery generation + auto-open")
    ap.add_argument("--no-open", action="store_true",
                    help="generate gallery but don't auto-open browser")
    ap.add_argument("--mood-mode", choices=["marketing", "product"], default="marketing",
                    help="reference-pool selector: marketing-only (default) or product-aware")
    ap.add_argument("--selector", choices=["v1", "v2"], default="v2",
                    help="selector algorithm: v1 (legacy top-K) or v2 "
                         "(embedding + stratified + diversity, default)")
    args = ap.parse_args()

    dna_path = BRAND_DNA_DIR / f"{args.brand}.json"
    if not dna_path.exists():
        print(f"[ERROR] brand-dna not found: {dna_path}", file=sys.stderr)
        return 1
    brand_dna = json.loads(dna_path.read_text(encoding="utf-8"))

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    mode_dir = "marketing_only" if args.mood_mode == "marketing" else "product_aware"
    run_dir = RESULTS_DIR / args.brand / mode_dir / f"{ts}_auto_pipeline"
    refs_dir = run_dir / "01_references"
    prop_dir = run_dir / "02_proposal"
    imgs_dir = run_dir / "03_images"
    for d in (refs_dir, prop_dir, imgs_dir):
        d.mkdir(parents=True, exist_ok=True)

    print(f"[run] {run_dir}")
    print(f"[run] mode={args.mood_mode} brand={args.brand} "
          f"season-category={args.season_category!r} k={args.k} "
          f"brand-filter={args.brand_filter}")

    # ---- Step A: mood references ----
    if args.selector == "v2":
        selector = (query_marketing_pool_product_v2
                     if args.mood_mode == "product"
                     else query_marketing_pool_v2)
    else:
        selector = (query_marketing_pool_product
                     if args.mood_mode == "product"
                     else query_marketing_pool)
    print(f"\n[Step A] Mood reference auto-select  "
          f"({args.mood_mode}-mode, selector={args.selector})")
    refs = selector(
        brand_dna,
        args.season_category,
        k=args.k,
        brand_filter=args.brand_filter,
        confidence_floor=args.confidence_floor,
    )
    print(f"  selected {len(refs)} refs")
    selection = {
        "brand": args.brand,
        "season_category": args.season_category,
        "mood_mode": args.mood_mode,
        "selector": args.selector,
        "k": args.k,
        "brand_filter": args.brand_filter,
        "selected": refs,
    }
    (refs_dir / "selection.json").write_text(
        json.dumps(selection, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Copy reference images for traceability
    for r in refs:
        src = Path(r["image"]) if r.get("image") else None
        if src and src.exists():
            try:
                shutil.copy2(src, refs_dir / f"ref_{r['rank']:02d}_{r['post_id']}.jpg")
            except Exception as e:
                print(f"  [warn] cannot copy {src}: {e}")
        print(f"  #{r['rank']} @{r['handle']} score={r['score']}"
              f" pose={r['model'].get('pose')} mood={r['background'].get('mood')}")

    if not refs:
        print("[ERROR] no refs found. Check brand-filter / confidence-floor / DNA marketing_dna",
              file=sys.stderr)
        return 2

    # ---- Step B: campaign proposal ----
    print("\n[Step B] Influencer campaign proposal")
    proposal = build_campaign_proposal(
        brand_dna, args.season_category, refs, n_scenes=args.k
    )
    (prop_dir / "campaign_proposal.json").write_text(
        json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md = proposal_to_markdown(proposal)
    (prop_dir / "campaign_proposal.md").write_text(md, encoding="utf-8")
    print(f"  wrote campaign_proposal.json + .md ({len(md):,} chars)")

    # ---- Step B.5: LLM moment extraction (gemini-3.1-flash-lite-preview) ----
    print("\n[Step B.5] Moment extraction (per-scene THE MOMENT line)")
    try:
        moments = extract_moments_for_scenes(proposal["scene_plan"], brand_dna)
        for s in proposal["scene_plan"]:
            s["moment"] = moments.get(s["scene_id"]) or s.get("moment")
        # Re-write proposal with moments injected
        (prop_dir / "campaign_proposal.json").write_text(
            json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        md2 = proposal_to_markdown(proposal)
        (prop_dir / "campaign_proposal.md").write_text(md2, encoding="utf-8")
        print(f"  filled {sum(1 for s in proposal['scene_plan'] if s.get('moment'))}/"
              f"{len(proposal['scene_plan'])} scenes with moments")
    except Exception as e:
        print(f"  [warn] moment extraction failed: {type(e).__name__}: {e}")

    # ---- Step C: image generation ----
    if args.no_images:
        print("\n[Step C] skipped (--no-images)")
        if not args.no_gallery:
            print("\n[Step D] Gallery (refs + proposal only)")
            try:
                gallery = render_gallery(run_dir)
                print(f"  gallery → {gallery}")
                if not args.no_open:
                    import webbrowser
                    webbrowser.open(gallery.as_uri())
            except Exception as e:
                print(f"  [warn] gallery render failed: {e}")
        print(f"\n[OK] refs + proposal at {run_dir}")
        return 0

    print(f"\n[Step C] Image generation (providers: {', '.join(args.providers)})")
    summary = generate_campaign_multi(
        proposal, imgs_dir, providers=args.providers, max_workers=args.max_workers
    )
    (imgs_dir / "_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for p, s in summary["by_provider"].items():
        print(f"  {p:<11} ok={s['ok']} fail={s['fail']} skip={s['skip']}")

    if "higgsfield" in args.providers:
        # MANDATORY follow-up step (per SKILL.md): Claude must run HF MCP for
        # 3 models × 6 scenes = 18 jobs after this Python pipeline finishes.
        # The .md below is a one-shot trigger doc Claude reads to execute.
        scene_ids = [s["scene_id"] for s in proposal["scene_plan"]]
        guide_lines = [
            "# Higgsfield MCP — Auto Trigger (Claude reads this)",
            "",
            "**STATUS**: pending. After Python pipeline finishes, the controlling",
            "Claude session MUST execute the 8-step HF MCP sequence below.",
            "This is a project default — do not skip unless user explicitly says so.",
            "",
            "## 8-step standard sequence",
            "1. `media_upload` — register all 6 reference images",
            "2. `curl PUT` — upload bytes to returned signed URLs",
            "3. `media_confirm` — confirm all 6 media_ids",
            "4. `generate_image` × 18 — Soul 2.0, Nano-Banana Pro, GPT-image 2 × 6 scenes",
            "   - Models: `soul_2`, `nano_banana_2`, `gpt_image_2`",
            "   - aspect_ratio: `3:4`, ref via `medias=[{role:'image', value: media_id}]`",
            "   - Max 4 concurrent jobs (Pro plan rate limit) → submit in 5 batches",
            "5. `job_status` — poll each with `sync=true` until all `completed`",
            "6. Retry failed jobs with shorter prompt (nano_banana_2 fails on long prompts)",
            "7. `curl GET` — download 18 PNGs to `03_images/{scene}_hf_{soul,nano,gpt}.png`",
            "8. `python build_run_gallery.py --run-dir <run> --no-open`  +  open gallery",
            "",
            f"## Scenes for this run ({len(scene_ids)})",
        ]
        for s in proposal["scene_plan"]:
            guide_lines.append(
                f"- **{s['scene_id']}**: prompt=`{s['scene_id']}_prompt.txt`, "
                f"ref=`{s['scene_id']}_00_reference.jpg`"
            )
        guide_lines += [
            "",
            "## Run dir",
            f"- `{imgs_dir}`",
            "",
            "## Compact prompt template (use for nano_banana_2 to avoid failures)",
            "```",
            "{BRAND} {SEASON} {CATEGORY} editorial. {PERSONA short}. ",
            "{EXPRESSION} expression, {GAZE} gaze, full body shot. ",
            "Wearing {GARMENT short}. Setting: {LOCATION short}. ",
            "{LIGHTING short}, {MOOD} mood. Match reference pose/framing.",
            "```",
        ]
        (imgs_dir / "higgsfield_manual_guide.md").write_text(
            "\n".join(guide_lines), encoding="utf-8"
        )
        print("  higgsfield: pending → Claude MCP follow-up required")
        print(f"               trigger doc: {imgs_dir / 'higgsfield_manual_guide.md'}")

    # ---- Step D: HTML gallery ----
    if not args.no_gallery:
        print("\n[Step D] Render gallery + auto-open")
        try:
            gallery = render_gallery(run_dir)
            print(f"  gallery → {gallery}")
            if not args.no_open:
                import webbrowser
                webbrowser.open(gallery.as_uri())
        except Exception as e:
            print(f"  [warn] gallery render failed: {e}")

    print(f"\n[OK] complete: {run_dir}")
    total_ok = sum(s["ok"] for s in summary["by_provider"].values())
    return 0 if total_ok > 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
