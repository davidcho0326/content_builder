"""Convert external labels (`source/sns-influencer-output/{BRAND}/labels_raw/*.json`)
into our schema (`schemas.empty_label_record`).

Output layout:
    source/sns-influencer-output/{BRAND}/labels_adapted/{post_id}.json
    source/sns-influencer-output/{BRAND}/labels_adapted/index.jsonl
    source/sns-influencer-output/{BRAND}/labels_adapted/_run.json

Plus a unified, ingestion-friendly:
    source/sns-influencer-output/labels_adapted_index.jsonl

CLI:
    python st_cut-dev/scripts/adapt_external_labels.py [--brand DV|DX|MLB|all] [--limit N] [--quiet]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

_THIS = Path(__file__).resolve()
_SCRIPTS = _THIS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from sns_labeling.adapter import (
    BRAND_CODE_TO_FULL,
    adapt_record,
    build_inverse_index,
)
from sns_labeling.taxonomy_loader import load_taxonomy

PROJECT_ROOT = _THIS.parents[2]
SRC_ROOT = PROJECT_ROOT / "source" / "sns-influencer-output"
TAX_PATH = PROJECT_ROOT / "st_cut-dev" / "taxonomy" / "labeling_taxonomy.json"

IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def _index_images(brand_dir: Path) -> dict[str, str]:
    """{post_id: absolute_path_string}."""
    out: dict[str, str] = {}
    for dp, _, fs in os.walk(brand_dir):
        for f in fs:
            stem, ext = os.path.splitext(f)
            if ext.lower() in IMG_EXTS and stem not in out:
                out[stem] = (Path(dp) / f).as_posix()
    return out


def _now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _summarize(rec: dict, agg: dict) -> None:
    """Update aggregate stats with one record."""
    agg["records"] += 1
    items = rec.get("items") or []
    agg["items_kept"] += len(items)
    extras_items = (rec.get("_extra") or {}).get("items") or []
    agg["items_seen"] += len(extras_items)
    for ex in extras_items:
        if ex.get("_dropped_reason"):
            agg["items_dropped"][ex["_dropped_reason"]] += 1
        for d in ex.get("leftover_details") or []:
            agg["leftover_details"][d] += 1
    for it in items:
        for k, v in (it.get("attributes") or {}).items():
            if v is not None:
                agg["attr_filled"] += 1
            agg["attr_total"] += 1
    for bin_name in ("common", "model", "background", "styling"):
        for k, v in (rec.get(bin_name) or {}).items():
            if v is None or v == [] or v == "":
                agg[f"{bin_name}_null"][k] += 1
            else:
                agg[f"{bin_name}_filled"][k] += 1
    if not rec.get("detected_categories"):
        agg["records_no_items"] += 1


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Adapt external labels into our schema")
    ap.add_argument("--brand", default="all", help="DV, DX, MLB, or all")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    brands = list(BRAND_CODE_TO_FULL.keys()) if args.brand == "all" else [args.brand]
    tax = load_taxonomy(TAX_PATH)
    inv = build_inverse_index(tax)
    print(f"[INFO] taxonomy v{tax.get('version')} | inverse index size: {len(inv)}")

    unified_path = SRC_ROOT / "labels_adapted_index.jsonl"
    unified_f = unified_path.open("w", encoding="utf-8")
    grand_started = _now_iso()
    grand_agg = {
        "records": 0, "items_seen": 0, "items_kept": 0,
        "attr_filled": 0, "attr_total": 0, "records_no_items": 0,
        "items_dropped": Counter(),
        "leftover_details": Counter(),
        "common_filled": Counter(), "common_null": Counter(),
        "model_filled": Counter(), "model_null": Counter(),
        "background_filled": Counter(), "background_null": Counter(),
        "styling_filled": Counter(), "styling_null": Counter(),
    }

    for brand in brands:
        bdir = SRC_ROOT / brand
        if not bdir.is_dir():
            print(f"[skip] {bdir} missing")
            continue
        labels_in = bdir / "labels_raw"
        labels_out = bdir / "labels_adapted"
        labels_out.mkdir(parents=True, exist_ok=True)

        files = sorted(f for f in os.listdir(labels_in)
                       if f.endswith(".json") and not f.startswith("_"))
        if args.limit:
            files = files[: args.limit]
        img_idx = _index_images(bdir)

        print(f"\n[INFO] {brand}: {len(files)} files | image index: {len(img_idx)} files")
        agg = {
            "records": 0, "items_seen": 0, "items_kept": 0,
            "attr_filled": 0, "attr_total": 0, "records_no_items": 0,
            "items_dropped": Counter(),
            "leftover_details": Counter(),
            "common_filled": Counter(), "common_null": Counter(),
            "model_filled": Counter(), "model_null": Counter(),
            "background_filled": Counter(), "background_null": Counter(),
            "styling_filled": Counter(), "styling_null": Counter(),
        }
        per_brand_index = labels_out / "index.jsonl"
        with per_brand_index.open("w", encoding="utf-8") as bf:
            for i, fname in enumerate(files, 1):
                try:
                    src = json.loads((labels_in / fname).read_text(encoding="utf-8"))
                except Exception as e:
                    print(f"  [skip] {fname}: {type(e).__name__}: {e}")
                    continue
                post_id = src.get("post_id") or os.path.splitext(fname)[0]
                img_abs = img_idx.get(post_id)
                rec = adapt_record(
                    src, tax, inv,
                    image_path=img_abs,
                    brand_full=BRAND_CODE_TO_FULL[brand],
                )
                # write per-record sidecar
                (labels_out / f"{post_id}.json").write_text(
                    json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                # append to per-brand jsonl + unified
                line = json.dumps(rec, ensure_ascii=False)
                bf.write(line + "\n")
                unified_f.write(line + "\n")
                _summarize(rec, agg)
                _summarize(rec, grand_agg)
                if not args.quiet and i % 200 == 0:
                    cov = (agg["attr_filled"] / agg["attr_total"] * 100
                           if agg["attr_total"] else 0.0)
                    print(f"  [{i}/{len(files)}] {brand} attr-cov={cov:.1f}%  records={agg['records']}")

        # write per-brand _run.json
        run = {
            "brand": brand,
            "brand_full": BRAND_CODE_TO_FULL[brand],
            "started_at": grand_started,
            "finished_at": _now_iso(),
            "input_dir": str(labels_in).replace("\\", "/"),
            "output_dir": str(labels_out).replace("\\", "/"),
            "records": agg["records"],
            "items_seen": agg["items_seen"],
            "items_kept": agg["items_kept"],
            "items_dropped": dict(agg["items_dropped"]),
            "records_no_items": agg["records_no_items"],
            "attribute_coverage": {
                "filled": agg["attr_filled"],
                "total": agg["attr_total"],
                "ratio": (agg["attr_filled"] / agg["attr_total"]) if agg["attr_total"] else None,
            },
            "shared_filled_ratio": {
                bin_name: {
                    k: agg[f"{bin_name}_filled"].get(k, 0)
                       / max(1, agg[f"{bin_name}_filled"].get(k, 0)
                                + agg[f"{bin_name}_null"].get(k, 0))
                    for k in (
                        list(agg[f"{bin_name}_filled"].keys())
                        + list(agg[f"{bin_name}_null"].keys())
                    )
                }
                for bin_name in ("common", "model", "background", "styling")
            },
            "top_leftover_details": agg["leftover_details"].most_common(40),
            "taxonomy_version": tax.get("version"),
        }
        # dedupe shared_filled_ratio key set
        for bin_name in run["shared_filled_ratio"]:
            run["shared_filled_ratio"][bin_name] = {
                k: round(v, 3)
                for k, v in run["shared_filled_ratio"][bin_name].items()
            }
        (labels_out / "_run.json").write_text(
            json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  [OK] {brand}: wrote {agg['records']} records → {labels_out}")
        cov = (agg["attr_filled"] / agg["attr_total"] * 100
               if agg["attr_total"] else 0.0)
        print(f"        items kept {agg['items_kept']}/{agg['items_seen']}  "
              f"attr-coverage {cov:.1f}%  no-items records {agg['records_no_items']}")

    unified_f.close()

    # global summary
    cov = (grand_agg["attr_filled"] / grand_agg["attr_total"] * 100
           if grand_agg["attr_total"] else 0.0)
    print("\n=== GRAND TOTAL ===")
    print(f"  records         : {grand_agg['records']:,}")
    print(f"  items kept/seen : {grand_agg['items_kept']:,}/{grand_agg['items_seen']:,}")
    print(f"  items dropped   : {dict(grand_agg['items_dropped'])}")
    print(f"  attr coverage   : {cov:.1f}%  ({grand_agg['attr_filled']:,}/{grand_agg['attr_total']:,})")
    print(f"  records w/o items: {grand_agg['records_no_items']}")
    print(f"  unified jsonl   : {unified_path}")
    print(f"  top leftover details (top 15):")
    for term, cnt in grand_agg["leftover_details"].most_common(15):
        print(f"    {cnt:>5}  {term}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
