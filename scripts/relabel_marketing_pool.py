"""Re-label the 5,774 SNS marketing pool with our sns-labeling-agent.

Source : labels_marketing_index.jsonl   (image.path + account info preserved)
Output : labels_marketing_v2/{post_id}.json   (per-record sidecar)
         labels_marketing_v2_index.jsonl       (unified)
         labels_marketing_v2_index.csv         (flat tabular)
         _run.json                             (stats + errors)

Goal: fill the 5 dimensions the external labeler missed
       (gaze direction / hair style / skin tone / shooting composition / color tone-filter)
      using gemini-3.1-flash-lite-preview.

CLI:
    python st_cut-dev/scripts/relabel_marketing_pool.py [--limit N] [--workers 8] [--brand DV|DX|MLB|all]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

_THIS = Path(__file__).resolve()
_SCRIPTS = _THIS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from sns_labeling.label_image import label_image
from sns_labeling.marketing_schema import CSV_COLUMNS, project_to_marketing, to_csv_row
from sns_labeling.taxonomy_loader import load_taxonomy

PROJECT_ROOT = _THIS.parents[2]
SRC_ROOT = PROJECT_ROOT / "source" / "sns-influencer-output"
SRC_JSONL = SRC_ROOT / "labels_marketing_index.jsonl"
TAX_PATH = PROJECT_ROOT / "st_cut-dev" / "taxonomy" / "labeling_taxonomy.json"

DEFAULT_MODEL = os.getenv("F_AND_F_RELABEL_MODEL", "gemini-3.1-flash-lite-preview")


def _now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _process_one(rec_in: dict, taxonomy: dict, model: str) -> dict:
    """Re-label one image; preserve account + image meta from input record."""
    img_path = (rec_in.get("image") or {}).get("path")
    account = rec_in.get("account") or {}
    if not img_path or not Path(img_path).exists():
        return {
            "_status": "skip",
            "post_id": account.get("post_id"),
            "error": f"image not found: {img_path}",
        }
    try:
        new_rec = label_image(img_path, taxonomy=taxonomy, account=account, model=model)
        # Preserve original account fields that label_image may have overwritten
        new_rec["account"] = {**(new_rec.get("account") or {}), **account}
        new_rec["_status"] = "ok" if not new_rec.get("errors") else "partial"
        return new_rec
    except Exception as e:
        return {
            "_status": "fail",
            "post_id": account.get("post_id"),
            "error": f"{type(e).__name__}: {e}",
        }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Re-label marketing pool with our agent")
    ap.add_argument("--limit", type=int, default=None,
                    help="Process at most N records (test mode)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--brand", default="all",
                    help="Filter by account.brand: duvetica/discovery/mlb/all")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--out-suffix", default="v2",
                    help="Output dir suffix (e.g. labels_marketing_v2)")
    args = ap.parse_args()

    out_root = SRC_ROOT
    sidecar_dir = out_root / f"labels_marketing_{args.out_suffix}"
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    unified_jsonl_path = out_root / f"labels_marketing_{args.out_suffix}_index.jsonl"
    unified_csv_path = out_root / f"labels_marketing_{args.out_suffix}_index.csv"
    run_json_path = sidecar_dir / "_run.json"

    taxonomy = load_taxonomy(TAX_PATH)

    # Load all input records
    if not SRC_JSONL.exists():
        print(f"[ERROR] {SRC_JSONL} not found", file=sys.stderr)
        return 1
    records: list[dict] = []
    for line in SRC_JSONL.open(encoding="utf-8"):
        rec = json.loads(line)
        if args.brand != "all":
            if (rec.get("account") or {}).get("brand") != args.brand:
                continue
        records.append(rec)
    if args.limit:
        records = records[: args.limit]
    print(f"[INFO] input records: {len(records)} | model: {args.model} | workers: {args.workers}")
    print(f"[INFO] sidecar dir: {sidecar_dir}")
    print(f"[INFO] unified  : {unified_jsonl_path}")

    started = _now_iso()
    t0 = time.time()
    ok = fail = skip = 0
    in_tok = out_tok = 0
    errors: list[dict] = []

    with unified_jsonl_path.open("w", encoding="utf-8") as f_jsonl, \
         unified_csv_path.open("w", encoding="utf-8-sig", newline="") as f_csv:
        csv_w = csv.DictWriter(f_csv, fieldnames=CSV_COLUMNS)
        csv_w.writeheader()

        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(_process_one, rec, taxonomy, args.model): rec for rec in records}
            done = 0
            for fut in as_completed(futs):
                rec_out = fut.result()
                done += 1
                status = rec_out.pop("_status", "?")
                if status == "skip":
                    skip += 1
                    errors.append(rec_out)
                elif status == "fail":
                    fail += 1
                    errors.append(rec_out)
                else:
                    ok += 1
                    pid = (rec_out.get("account") or {}).get("post_id") or "unknown"
                    (sidecar_dir / f"{pid}.json").write_text(
                        json.dumps(rec_out, ensure_ascii=False, indent=2),
                        encoding="utf-8")
                    # marketing projection for index/csv (drop items/common/...)
                    mkt = project_to_marketing(rec_out)
                    f_jsonl.write(json.dumps(mkt, ensure_ascii=False) + "\n")
                    csv_w.writerow(to_csv_row(mkt))
                    in_tok += rec_out.get("vlm", {}).get("input_tokens") or 0
                    out_tok += rec_out.get("vlm", {}).get("output_tokens") or 0
                if done % 50 == 0:
                    elapsed = time.time() - t0
                    rate = done / max(elapsed, 1e-3)
                    eta = (len(records) - done) / max(rate, 1e-3)
                    print(f"  [{done}/{len(records)}] ok={ok} fail={fail} skip={skip}"
                          f" | rate={rate:.1f}/s | ETA={eta/60:.1f}min")

    summary = {
        "started_at": started,
        "finished_at": _now_iso(),
        "elapsed_sec": round(time.time() - t0, 2),
        "model": args.model,
        "input_total": len(records),
        "ok": ok, "fail": fail, "skip": skip,
        "in_tokens_total": in_tok or None,
        "out_tokens_total": out_tok or None,
        "errors_first_20": errors[:20],
        "outputs": {
            "sidecar_dir": str(sidecar_dir).replace("\\", "/"),
            "unified_jsonl": str(unified_jsonl_path).replace("\\", "/"),
            "unified_csv": str(unified_csv_path).replace("\\", "/"),
        },
    }
    run_json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== DONE ===")
    print(f"  ok={ok}  fail={fail}  skip={skip}  elapsed={summary['elapsed_sec']:.0f}s")
    print(f"  tokens : in={in_tok:,}  out={out_tok:,}")
    print(f"  outputs: {sidecar_dir} + {unified_jsonl_path.name}")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
