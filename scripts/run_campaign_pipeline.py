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
    build_imc_proposal,
    imc_proposal_to_markdown,
)
from sns_labeling.mood_query import query_marketing_pool, query_marketing_pool_v2
from sns_labeling.mood_query_product import (
    query_marketing_pool_product,
    query_marketing_pool_product_v2,
)
from sns_labeling.image_providers import (
    generate_campaign_multi,
    generate_campaign_imc,
)
from sns_labeling.moment_extractor import (
    extract_moments_for_scenes,
    extract_moments_for_imc,
)
from sns_labeling.imc_plan_loader import load_campaign_spec
from sns_labeling.selector_v3 import select_for_campaign as select_imc_refs

from build_run_gallery import render as render_gallery

PROJECT_ROOT = _THIS.parents[2]
BRAND_DNA_DIR = PROJECT_ROOT / "st_cut-dev" / "brand-dna"
RESULTS_DIR = PROJECT_ROOT / "st_cut-dev" / "results"


# ============================================================================
# IMC-driven pipeline (v3, Option α)
# ============================================================================

def _run_imc_pipeline(args) -> int:
    """End-to-end imc_plan.json → 3 scenes × N variants × M providers."""
    plan_path = Path(args.imc_plan)
    if not plan_path.exists():
        print(f"[ERROR] imc-plan not found: {plan_path}", file=sys.stderr)
        return 1

    spec = load_campaign_spec(plan_path)
    n_per = max(1, args.variants_per_scene)
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    brand_lower = (spec.brand or "brand").lower()
    run_dir = RESULTS_DIR / brand_lower / "imc_driven" / f"{spec.campaign_id}_{ts}"
    refs_dir = run_dir / "01_references"
    prop_dir = run_dir / "02_proposal"
    imgs_dir = run_dir / "03_images"
    for d in (refs_dir, prop_dir, imgs_dir):
        d.mkdir(parents=True, exist_ok=True)

    # Snapshot the input plan for traceability.
    (run_dir / "00_imc_snapshot.json").write_text(
        plan_path.read_text(encoding="utf-8"), encoding="utf-8"
    )

    print(f"[run] {run_dir}")
    print(f"[run] mode=imc_driven  campaign={spec.campaign_id}  "
          f"brand={spec.brand} season={spec.season} lifestyle={spec.lifestyle}")
    print(f"[run] scenes={len(spec.scenes)} variants_per_scene={n_per} "
          f"providers={args.providers}")

    # ---- Step A: per-scene reference selection ----
    print(f"\n[Step A] Per-scene reference selection (selector v3, persona+pose)")
    refs_by_scene = select_imc_refs(
        spec, n_per_scene=n_per,
        confidence_floor=args.confidence_floor,
    )
    selection_doc = {
        "campaign_id": spec.campaign_id,
        "brand": spec.brand,
        "season": spec.season,
        "selector": "v3",
        "variants_per_scene": n_per,
        "scenes": [
            {
                "scene_id": scene.slug,
                "scene_num": scene.num,
                "title": scene.title,
                "persona_match": scene.persona_match,
                "n_refs": len(refs_by_scene.get(scene.slug, [])),
                "refs": refs_by_scene.get(scene.slug, []),
            }
            for scene in spec.scenes
        ],
    }
    (refs_dir / "selection.json").write_text(
        json.dumps(selection_doc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Copy ref images for traceability.
    for scene in spec.scenes:
        for r in refs_by_scene.get(scene.slug, []):
            src = Path(r.get("image") or "")
            if src.exists():
                try:
                    shutil.copy2(
                        src,
                        refs_dir / f"{scene.slug}_R{r['rank']:02d}_{r['post_id']}.jpg",
                    )
                except Exception as e:
                    print(f"  [warn] copy fail {src}: {e}")
        n = len(refs_by_scene.get(scene.slug, []))
        print(f"  {scene.slug} (persona {scene.persona_match}): {n} refs")
        for r in refs_by_scene.get(scene.slug, []):
            m = r.get("model") or {}
            print(f"    #{r['rank']} @{r['handle']:18s} score={r['score']:.4f} "
                  f"age={m.get('age group')} gender={m.get('gender')}")

    total_refs = sum(len(refs_by_scene.get(s.slug, [])) for s in spec.scenes)
    if total_refs == 0:
        print("[ERROR] no refs selected for any scene", file=sys.stderr)
        return 2

    # ---- Step B.5: per-(scene,ref) moment generation ----
    print(f"\n[Step B.5] Moment extraction "
          f"(per-(scene,ref) IMC-aware THE MOMENT line)")
    try:
        moments_by_key = extract_moments_for_imc(spec, refs_by_scene)
    except Exception as e:
        print(f"  [warn] moment extraction failed: {type(e).__name__}: {e}")
        moments_by_key = {}

    # ---- Step B: campaign proposal ----
    print(f"\n[Step B] IMC proposal")
    proposal = build_imc_proposal(spec, refs_by_scene, moments_by_key=moments_by_key)
    (prop_dir / "campaign_proposal.json").write_text(
        json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md = imc_proposal_to_markdown(proposal)
    (prop_dir / "campaign_proposal.md").write_text(md, encoding="utf-8")
    print(f"  wrote campaign_proposal.json + .md ({len(md):,} chars)")

    # ---- Step C: image generation ----
    if args.no_images:
        print("\n[Step C] skipped (--no-images)")
    else:
        print(f"\n[Step C] Image generation (providers: {', '.join(args.providers)})")
        # Filter providers to those supported by the IMC orchestrator (Direct only).
        from sns_labeling.image_providers import IMC_PROVIDER_FUNCS as _imc_pf
        providers = [p for p in args.providers if p in _imc_pf]
        if not providers:
            print("  [warn] no IMC providers selected; nothing to generate")
        else:
            summary = generate_campaign_imc(
                spec, refs_by_scene, imgs_dir,
                providers=providers,
                moments_by_key=moments_by_key,
                max_workers=args.max_workers,
            )
            (imgs_dir / "_summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            for p, s in summary["by_provider"].items():
                print(f"  {p:<11} ok={s['ok']} fail={s['fail']} skip={s['skip']}")

    # ---- Step C+: virtual try-on (hero product swap, v3.2) ----
    if args.apply_tryon and not args.no_images:
        print(f"\n[Step C+] Virtual try-on "
              f"(engines={args.tryon_engines}, target={args.tryon_target})")
        from sns_labeling.tryon import run_tryon_step
        from sns_labeling.product_router import (
            route_hero_product, route_bottom_product,
            write_manifest as write_product_manifest,
        )
        product_match = route_hero_product(spec)
        if product_match is None:
            print("  [skip] no hero product matched in products_resource")
        else:
            products_dir = run_dir / "04_products"
            products_dir.mkdir(parents=True, exist_ok=True)
            write_product_manifest(product_match, products_dir / "hero_product.json")
            try:
                shutil.copy2(product_match.hero_image,
                             products_dir / f"hero_product_used{product_match.hero_image.suffix}")
            except Exception as e:
                print(f"  [warn] hero copy failed: {e}")
            print(f"  hero: {product_match.brand_folder}/"
                  f"{product_match.season} {product_match.code_folder}/"
                  f"{product_match.lifestyle_folder}/"
                  f"{product_match.hero_image.name} "
                  f"(strategy: {product_match.match_strategy}/{product_match.hero_strategy})")

            # Multi-tryon: auto-route bottom (WP/PT) when --tryon-multi is on
            bottom_match = None
            if args.tryon_multi:
                bottom_match = route_bottom_product(spec)
                if bottom_match is not None:
                    write_product_manifest(bottom_match, products_dir / "bottom_product.json")
                    try:
                        shutil.copy2(
                            bottom_match.hero_image,
                            products_dir / f"bottom_product_used{bottom_match.hero_image.suffix}",
                        )
                    except Exception as e:
                        print(f"  [warn] bottom copy failed: {e}")
                    print(f"  bottom: {bottom_match.brand_folder}/"
                          f"{bottom_match.season} {bottom_match.code_folder}/"
                          f"{bottom_match.lifestyle_folder}/"
                          f"{bottom_match.hero_image.name} "
                          f"(strategy: {bottom_match.match_strategy}/{bottom_match.hero_strategy})")
                else:
                    print("  [info] no bottom product matched — single-garment try-on")

            tryon_results = run_tryon_step(
                spec, refs_by_scene,
                gen_results=summary.get("results", []) if 'summary' in locals() else [],
                out_dir=imgs_dir,
                only_provider=args.tryon_target,
                engines=args.tryon_engines,
                product_match=product_match,
                bottom_match=bottom_match,
            )
            (imgs_dir / "_tryon_summary.json").write_text(
                json.dumps(tryon_results, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"  tryon ok={tryon_results['ok']} "
                  f"fail={tryon_results['fail']} "
                  f"skip={tryon_results['skip']}")

    # ---- Step D: gallery ----
    if not args.no_gallery:
        print("\n[Step D] Render gallery + auto-open")
        try:
            from build_run_gallery import render_imc as render_imc_gallery_fn
            gallery = render_imc_gallery_fn(run_dir)
        except (ImportError, AttributeError):
            # Fallback: use legacy gallery renderer
            print("  [info] render_imc not available; using legacy gallery renderer")
            try:
                gallery = render_gallery(run_dir)
            except Exception as e:
                print(f"  [warn] gallery render failed: {e}")
                gallery = None
        if gallery:
            print(f"  gallery → {gallery}")
            if not args.no_open:
                import webbrowser
                webbrowser.open(gallery.as_uri())

    print(f"\n[OK] complete: {run_dir}")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Run strategy-cut auto pipeline")
    # IMC-driven mode (v3, default since 2026-05) — single source of truth.
    ap.add_argument("--imc-plan", default=None,
                    help="Path to marketing_builder imc_plan.json. When set, runs the "
                         "IMC-driven 3-scene pipeline (selector v3 + scene-aware prompt). "
                         "Mutually exclusive with --legacy-static.")
    ap.add_argument("--variants-per-scene", type=int, default=6,
                    help="Refs per scene in IMC mode (default 6).")
    # Legacy static mode (v1/v2) — preserved for regression / comparison runs.
    ap.add_argument("--legacy-static", action="store_true",
                    help="Run legacy brand_dna + season_category pipeline (v1/v2). "
                         "Requires --brand and --season-category.")
    ap.add_argument("--brand",
                    help="(legacy) duvetica | mlb | discovery (matches brand-dna/{brand}.json)")
    ap.add_argument("--season-category",
                    help='(legacy) e.g. "27SS WJ", "27SS SETUP", "26FW WINDBREAKER"')
    ap.add_argument("--k", type=int, default=6, help="(legacy) number of refs / scenes")
    ap.add_argument("--brand-filter", action="append", default=None,
                    help="restrict ref pool to this account.brand (can repeat)")
    ap.add_argument("--confidence-floor", type=float, default=0.7)
    ap.add_argument("--no-images", action="store_true",
                    help="skip Step C (image generation), only build refs+proposal")
    ap.add_argument("--providers", nargs="+",
                    default=["gpt"],
                    choices=["gpt", "gemini", "higgsfield"],
                    help="Direct image-gen providers (default: gpt only). "
                         "Standard 3-model lineup (2026-05-03 onward): GPT-image-2 "
                         "(Direct) + HF GPT-image 2 + HF Marketing Studio. "
                         "HF half is run separately via Claude HF MCP after Python "
                         "finishes. `gemini` is retained as opt-in for compat only "
                         "— not part of the standard. See SKILL.md")
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
    # Step C+ Virtual Try-On (v3.2, IMC mode only)
    ap.add_argument("--apply-tryon", dest="apply_tryon", action="store_true",
                    default=True,
                    help="Run Step C+ virtual try-on after image generation "
                         "(default true, IMC mode only)")
    ap.add_argument("--no-tryon", dest="apply_tryon", action="store_false",
                    help="Skip Step C+ virtual try-on")
    ap.add_argument("--tryon-engines", nargs="+",
                    default=["gpt"],
                    choices=["gemini", "gpt"],
                    help="Which try-on engines to run. "
                         "Standard (2026-05-03): gpt-image-2 only (default). "
                         "gemini available for opt-in (--tryon-engines gemini gpt).")
    ap.add_argument("--tryon-target", default="gpt",
                    choices=["gpt", "hf_gpt", "hf_mkt", "all"],
                    help="Which raw provider's images to apply try-on to "
                         "(default: gpt — Direct GPT-image-2 18 images only)")
    ap.add_argument("--tryon-multi", dest="tryon_multi", action="store_true",
                    default=True,
                    help="Auto-detect bottom (WP/PT) sub-garment and run "
                         "multi-tryon (top + bottom simultaneous swap) when "
                         "available (default true)")
    ap.add_argument("--no-tryon-multi", dest="tryon_multi",
                    action="store_false",
                    help="Force single-garment (hero only) try-on even if "
                         "bottom asset is available")
    args = ap.parse_args()

    # ---- IMC-driven branch (v3) ----
    if args.imc_plan and not args.legacy_static:
        return _run_imc_pipeline(args)

    if args.legacy_static and not args.brand:
        print("[ERROR] --legacy-static requires --brand", file=sys.stderr)
        return 1
    if not args.brand or not args.season_category:
        print("[ERROR] either --imc-plan PATH or (--legacy-static --brand X --season-category 'YY ZZ') required",
              file=sys.stderr)
        return 1

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
