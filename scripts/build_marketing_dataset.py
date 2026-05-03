"""Project `labels_adapted/` -> `labels_marketing/` (marketing context only).

Reads:
    source/sns-influencer-output/{BRAND}/labels_adapted/*.json    (per-record)
    source/sns-influencer-output/labels_adapted_index.jsonl        (unified)

Writes:
    source/sns-influencer-output/{BRAND}/labels_marketing/{post_id}.json
    source/sns-influencer-output/{BRAND}/labels_marketing/index.jsonl
    source/sns-influencer-output/{BRAND}/labels_marketing/index.csv
    source/sns-influencer-output/{BRAND}/labels_marketing/_run.json
    source/sns-influencer-output/labels_marketing_index.jsonl
    source/sns-influencer-output/labels_marketing_index.csv

Strict projection — `items` / `detected_categories` / `common` / `errors`
are NEVER carried over (see marketing_schema.project_to_marketing).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
from collections import Counter
from pathlib import Path

_THIS = Path(__file__).resolve()
_SCRIPTS = _THIS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from sns_labeling.marketing_schema import (
    CSV_COLUMNS,
    project_to_marketing,
    to_csv_row,
)

PROJECT_ROOT = _THIS.parents[2]
SRC_ROOT = PROJECT_ROOT / "source" / "sns-influencer-output"
BRANDS = ("DV", "DX", "MLB")


def _now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _summarize(rec: dict, agg: dict) -> None:
    agg["records"] += 1
    for bin_name in ("model", "background", "styling"):
        for k, v in (rec.get(bin_name) or {}).items():
            if v is None or v == [] or v == "":
                agg[f"{bin_name}_null"][k] += 1
            else:
                agg[f"{bin_name}_filled"][k] += 1
    if (rec.get("free_text") or {}).get("_confidence") is not None:
        agg["confidence_count"] += 1
        agg["confidence_sum"] += rec["free_text"]["_confidence"]


def _new_agg() -> dict:
    return {
        "records": 0,
        "model_filled": Counter(), "model_null": Counter(),
        "background_filled": Counter(), "background_null": Counter(),
        "styling_filled": Counter(), "styling_null": Counter(),
        "confidence_sum": 0.0, "confidence_count": 0,
    }


def _ratio_block(agg: dict, bin_name: str) -> dict:
    keys = set(agg[f"{bin_name}_filled"].keys()) | set(agg[f"{bin_name}_null"].keys())
    out = {}
    for k in keys:
        f = agg[f"{bin_name}_filled"].get(k, 0)
        n = agg[f"{bin_name}_null"].get(k, 0)
        out[k] = round(f / max(1, f + n), 3)
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Build marketing-only dataset")
    ap.add_argument("--brand", default="all", help="DV, DX, MLB, or all")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    brands = list(BRANDS) if args.brand == "all" else [args.brand]

    unified_jsonl = (SRC_ROOT / "labels_marketing_index.jsonl").open("w", encoding="utf-8")
    unified_csv_path = SRC_ROOT / "labels_marketing_index.csv"
    # UTF-8 BOM so Excel detects encoding correctly with Korean text
    unified_csv_f = unified_csv_path.open("w", encoding="utf-8-sig", newline="")
    unified_csv = csv.DictWriter(unified_csv_f, fieldnames=CSV_COLUMNS)
    unified_csv.writeheader()

    grand = _new_agg()
    started_global = _now_iso()

    for brand in brands:
        bdir = SRC_ROOT / brand
        in_dir = bdir / "labels_adapted"
        out_dir = bdir / "labels_marketing"
        if not in_dir.is_dir():
            print(f"[skip] {in_dir} missing")
            continue
        out_dir.mkdir(parents=True, exist_ok=True)

        files = sorted(
            f for f in os.listdir(in_dir)
            if f.endswith(".json")
            and not f.startswith("_")
            and f != "index.jsonl"
        )
        if args.limit:
            files = files[: args.limit]

        agg = _new_agg()
        per_jsonl = (out_dir / "index.jsonl").open("w", encoding="utf-8")
        per_csv_f = (out_dir / "index.csv").open("w", encoding="utf-8-sig", newline="")
        per_csv = csv.DictWriter(per_csv_f, fieldnames=CSV_COLUMNS)
        per_csv.writeheader()

        print(f"\n[INFO] {brand}: {len(files)} adapted records → {out_dir}")
        for i, fname in enumerate(files, 1):
            try:
                src = json.loads((in_dir / fname).read_text(encoding="utf-8"))
            except Exception as e:
                print(f"  [skip] {fname}: {e}")
                continue
            rec = project_to_marketing(src)
            post_id = (rec["account"] or {}).get("post_id") or os.path.splitext(fname)[0]
            (out_dir / f"{post_id}.json").write_text(
                json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            line = json.dumps(rec, ensure_ascii=False)
            per_jsonl.write(line + "\n")
            unified_jsonl.write(line + "\n")
            row = to_csv_row(rec)
            per_csv.writerow(row)
            unified_csv.writerow(row)
            _summarize(rec, agg)
            _summarize(rec, grand)
            if not args.quiet and i % 500 == 0:
                print(f"  [{i}/{len(files)}] {brand} records={agg['records']}")

        per_jsonl.close()
        per_csv_f.close()

        run = {
            "brand": brand,
            "started_at": started_global,
            "finished_at": _now_iso(),
            "input_dir": str(in_dir).replace("\\", "/"),
            "output_dir": str(out_dir).replace("\\", "/"),
            "records": agg["records"],
            "csv_columns": list(CSV_COLUMNS),
            "fill_ratio": {
                "model": _ratio_block(agg, "model"),
                "background": _ratio_block(agg, "background"),
                "styling": _ratio_block(agg, "styling"),
            },
            "confidence_avg": (
                round(agg["confidence_sum"] / agg["confidence_count"], 3)
                if agg["confidence_count"] else None
            ),
            "schema_dropped": ["items", "detected_categories", "common",
                                "errors", "_extra.items"],
        }
        (out_dir / "_run.json").write_text(
            json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  [OK] {brand}: {agg['records']} records written")

    unified_jsonl.close()
    unified_csv_f.close()

    print(f"\n=== GRAND TOTAL ===")
    print(f"  records          : {grand['records']:,}")
    print(f"  unified jsonl    : {SRC_ROOT / 'labels_marketing_index.jsonl'}")
    print(f"  unified csv      : {unified_csv_path}")
    print(f"  confidence avg   : "
          f"{round(grand['confidence_sum']/grand['confidence_count'],3) if grand['confidence_count'] else None}")
    for bin_name in ("model", "background", "styling"):
        ratios = _ratio_block(grand, bin_name)
        if not ratios:
            continue
        avg = sum(ratios.values()) / len(ratios) if ratios else 0
        top = ", ".join(f"{k}={int(v*100)}%"
                        for k, v in sorted(ratios.items(), key=lambda x: -x[1]))
        print(f"  {bin_name:<11} avg fill {avg*100:.1f}% | {top}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
