"""Batch labeling runner for a folder of images + folder-level _meta.csv.

Output layout (default; --output overrides root):
    <input>/_labeled/{img_stem}.json    # per-image sidecar
    <input>/_labeled/index.jsonl         # one record per line
    <input>/_labeled/_run.json           # run statistics

CLI:
    python -m sns_labeling.batch_runner \\
        --input    st_cut-dev/data/duvetica/instagram \\
        --meta     st_cut-dev/data/duvetica/instagram/_meta.csv \\
        --taxonomy st_cut-dev/taxonomy/labeling_taxonomy.json \\
        --workers  5 \\
        [--limit N] [--brand duvetica] [--source instagram] \\
        [--output PATH] [--model gemini-2.5-flash] [--overwrite]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR.parent))

from sns_labeling.label_image import label_image
from sns_labeling.schemas import META_COLUMNS, META_NUMERIC
from sns_labeling.taxonomy_loader import load_taxonomy

IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def _now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def parse_meta(meta_path: Optional[Path]) -> dict[str, dict]:
    """Load _meta.csv into a {filename: account_dict} map. Empty if missing."""
    if not meta_path or not meta_path.exists():
        return {}
    out: dict[str, dict] = {}
    with meta_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fname = (row.get("file") or "").strip()
            if not fname:
                continue
            metrics = {}
            for k in META_NUMERIC:
                v = (row.get(k) or "").strip()
                if v == "":
                    metrics[k] = None
                else:
                    try:
                        metrics[k] = int(float(v))
                    except ValueError:
                        metrics[k] = None
            hashtags_raw = (row.get("hashtags") or "").strip()
            tags: list[str] = []
            if hashtags_raw:
                for tok in hashtags_raw.replace(",", " ").split():
                    tok = tok.strip().lstrip("#")
                    if tok:
                        tags.append(tok)
            out[fname] = {
                "post_url": (row.get("post_url") or "").strip() or None,
                "posted_at": (row.get("posted_at") or "").strip() or None,
                "metrics": metrics,
                "caption": (row.get("caption") or "").strip() or None,
                "hashtags": tags,
            }
    return out


def collect_images(folder: Path) -> list[Path]:
    return sorted(
        p
        for p in folder.iterdir()
        if p.is_file()
        and p.suffix.lower() in IMG_EXTS
        and not p.name.startswith("_")
    )


def process_one(
    img: Path,
    *,
    taxonomy: dict,
    account: Optional[dict],
    out_dir: Path,
    model: Optional[str],
    overwrite: bool,
) -> tuple[Path, dict, bool, float]:
    """Label one image, save sidecar, return (path, record, success, elapsed)."""
    side = out_dir / f"{img.stem}.json"
    if side.exists() and not overwrite:
        rec = json.loads(side.read_text(encoding="utf-8"))
        return img, rec, not rec.get("errors"), 0.0
    t0 = time.time()
    rec = label_image(img, taxonomy=taxonomy, account=account, model=model)
    elapsed = time.time() - t0
    side.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return img, rec, not rec.get("errors"), elapsed


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Batch SNS image labeling")
    ap.add_argument("--input", required=True, help="Input image folder")
    ap.add_argument("--taxonomy", required=True)
    ap.add_argument("--meta", default=None, help="Folder-level _meta.csv (optional)")
    ap.add_argument("--output", default=None, help="Output dir (default: <input>/_labeled)")
    ap.add_argument("--brand", default=None, help="Account brand label (e.g., duvetica)")
    ap.add_argument("--source", default=None, help="Account source (e.g., instagram)")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--limit", type=int, default=None, help="Process at most N images")
    ap.add_argument("--model", default=None, help="VLM model override")
    ap.add_argument("--overwrite", action="store_true", help="Re-label even if sidecar exists")
    args = ap.parse_args()

    in_dir = Path(args.input).resolve()
    if not in_dir.is_dir():
        print(f"[ERROR] not a directory: {in_dir}", file=sys.stderr)
        return 1
    out_dir = Path(args.output).resolve() if args.output else in_dir / "_labeled"
    out_dir.mkdir(parents=True, exist_ok=True)

    taxonomy = load_taxonomy(args.taxonomy)
    meta_path = Path(args.meta) if args.meta else (in_dir / "_meta.csv")
    meta_map = parse_meta(meta_path)

    images = collect_images(in_dir)
    if args.limit:
        images = images[: args.limit]
    if not images:
        print(f"[WARN] no images found in {in_dir}")
        return 0

    print(f"[INFO] input  : {in_dir}")
    print(f"[INFO] output : {out_dir}")
    print(f"[INFO] meta   : {meta_path if meta_path.exists() else '(none)'}  ({len(meta_map)} rows)")
    print(f"[INFO] images : {len(images)} | workers={args.workers}")

    started = _now_iso()
    t_run = time.time()
    ok = fail = 0
    in_tok = out_tok = 0
    records: list[dict] = []

    def make_account(img: Path) -> Optional[dict]:
        row = meta_map.get(img.name)
        if not row and not (args.brand or args.source):
            return None
        acct = dict(row or {})
        if args.brand:
            acct["brand"] = args.brand
        if args.source:
            acct["source"] = args.source
        return acct

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {
            ex.submit(
                process_one,
                img,
                taxonomy=taxonomy,
                account=make_account(img),
                out_dir=out_dir,
                model=args.model,
                overwrite=args.overwrite,
            ): img
            for img in images
        }
        for i, fut in enumerate(as_completed(futures), 1):
            img = futures[fut]
            try:
                _, rec, success, elapsed = fut.result()
            except Exception as e:
                fail += 1
                err_rec = {
                    "image": {"file": img.name, "path": str(img).replace("\\", "/")},
                    "errors": [f"runner failure: {type(e).__name__}: {e}"],
                }
                records.append(err_rec)
                print(f"  [{i}/{len(images)}] FAIL {img.name}: {e}")
                continue
            records.append(rec)
            if success:
                ok += 1
            else:
                fail += 1
            in_tok += rec.get("vlm", {}).get("input_tokens") or 0
            out_tok += rec.get("vlm", {}).get("output_tokens") or 0
            status = "OK " if success else "ERR"
            cats = ",".join(rec.get("detected_categories") or []) or "-"
            print(f"  [{i}/{len(images)}] {status} {img.name} ({elapsed:.1f}s) cats=[{cats}]")

    # Write index.jsonl in original input order
    by_name = {r["image"]["file"]: r for r in records}
    index_path = out_dir / "index.jsonl"
    with index_path.open("w", encoding="utf-8") as f:
        for img in images:
            rec = by_name.get(img.name)
            if rec:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    elapsed = time.time() - t_run
    run_meta = {
        "started_at": started,
        "finished_at": _now_iso(),
        "elapsed_sec": round(elapsed, 2),
        "input_dir": str(in_dir).replace("\\", "/"),
        "output_dir": str(out_dir).replace("\\", "/"),
        "meta_csv": str(meta_path).replace("\\", "/") if meta_path.exists() else None,
        "taxonomy_version": taxonomy.get("version"),
        "model": args.model or None,
        "workers": args.workers,
        "image_count": len(images),
        "succeeded": ok,
        "failed": fail,
        "input_tokens_total": in_tok or None,
        "output_tokens_total": out_tok or None,
    }
    (out_dir / "_run.json").write_text(
        json.dumps(run_meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n[DONE] ok={ok} fail={fail} elapsed={elapsed:.1f}s")
    print(f"       index : {index_path}")
    print(f"       stats : {out_dir / '_run.json'}")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
