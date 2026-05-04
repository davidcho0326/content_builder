"""Run gpt-image-2 try-on on all 54 HF DV outputs.

Iterates over every {unit_id}_hf_{model}.png in 03_images/, dispatching
_apply_tryon_gpt for each, using DV WJ Premium_Resort hero product.

Output naming: {unit_id}_hf_{model}_tryon_gpt.png
"""
import sys
import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "st_cut-dev" / "scripts"))

from sns_labeling.imc_plan_loader import load_campaign_spec
from sns_labeling.product_router import route_hero_product
from sns_labeling.tryon import (
    _apply_tryon_gpt,
    _gemini_client,
    _vt_analyze_product,
    _VTON_AVAILABLE,
)
from PIL import Image


if len(sys.argv) > 2:
    SPEC_PATH = Path(sys.argv[1])
    RUN_DIR = Path(sys.argv[2])
else:
    SPEC_PATH = ROOT / "marketing_builder/samples/20260503_DV_27SS/05_marketing/output/imc_plan.json"
    RUN_DIR = ROOT / "st_cut-dev/results/dv/imc_driven/20260503_DV_27SS_20260503_231654"
IMGS_DIR = RUN_DIR / "03_images"


def main():
    spec = load_campaign_spec(SPEC_PATH)
    print(f"[run] {RUN_DIR}")
    print(f"[run] brand={spec.brand} season={spec.season} lifestyle={spec.lifestyle}")

    hero_match = route_hero_product(spec)
    if hero_match is None:
        print("[ERROR] no hero product matched", file=sys.stderr)
        return 2
    print(f"[hero] {hero_match.folder}")
    print(f"[hero] image={hero_match.hero_image.name}")
    product_path = hero_match.hero_image

    # Pre-analyze (best effort; falls back to None)
    top_analysis = None
    if _VTON_AVAILABLE:
        try:
            client = _gemini_client()
            product_pil = Image.open(product_path).convert("RGB")
            top_analysis = _vt_analyze_product(client, product_pil)
            print(f"[analyze] type={getattr(top_analysis, 'garment_type', '')} "
                  f"color={getattr(top_analysis, 'primary_color', '')}")
        except Exception as e:
            print(f"[analyze] skip ({type(e).__name__}: {e})")

    # Find every {unit_id}_hf_{model}.png
    hf_outputs = sorted(IMGS_DIR.glob("*_hf_*.png"))
    # Filter: skip already-tryon files
    hf_outputs = [p for p in hf_outputs if "_tryon_" not in p.name]
    print(f"[targets] {len(hf_outputs)} hf outputs")

    jobs = []
    for raw in hf_outputs:
        out_name = raw.name.replace("_hf_", "_hf_").replace(".png", "_tryon_gpt.png")
        # naming: keep _hf_{model}_ prefix and append _tryon_gpt
        # raw='S01_..._R01_hf_gpt.png' → out='S01_..._R01_hf_gpt_tryon_gpt.png'
        out_path = IMGS_DIR / out_name
        if out_path.exists():
            continue
        jobs.append((raw, out_path))

    print(f"[jobs] {len(jobs)} pending (skipping pre-existing)")

    results = []

    def run_one(job):
        raw, out_path = job
        return _apply_tryon_gpt(
            raw, product_path, out_path,
            product_analysis=top_analysis,
        )

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(run_one, j): j[1].name for j in jobs}
        for fu in as_completed(futs):
            r = fu.result()
            results.append(r)
            tag = "OK" if r.get("status") == "ok" else "FAIL"
            extra = r.get("image") or r.get("error") or ""
            name = futs[fu]
            print(f"  [{tag}] {name} :: {extra}")

    ok = sum(1 for r in results if r.get("status") == "ok")
    fail = sum(1 for r in results if r.get("status") != "ok")
    print(f"[done] {ok} ok / {fail} fail in {time.time()-t0:.0f}s")

    summary = {
        "product": hero_match.to_dict(),
        "n_jobs": len(jobs),
        "ok": ok,
        "fail": fail,
        "results": results,
    }
    (IMGS_DIR / "_dv_hf_tryon_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
