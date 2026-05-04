"""Fetch pipeline inputs from a single shared Google Drive folder.

Drive folder layout expected (mirrors `_drive_upload_staging/`):

    {GDRIVE_FOLDER_ID}/
      ├── influencer_pool/
      │     ├── _pool_embeddings.npz
      │     ├── labels_adapted_index.jsonl
      │     └── _pool_taxonomy.json
      ├── imc_plans/
      │     ├── 20260503_DV_27SS_imc_plan.json
      │     ├── 20260503_DX_26FW_imc_plan.json
      │     └── 20260503_MLB_27SS_imc_plan.json
      └── products_resource/
            ├── DV.zip
            ├── DX.zip
            └── MLB.zip

The script uses `gdown` to download the whole folder into a tmp staging dir,
then moves each file to its final location and extracts the brand zips.

Usage:
    pip install gdown
    python st_cut-dev/scripts/_download_inputs.py            # dry-run, lists missing
    python st_cut-dev/scripts/_download_inputs.py --apply    # actually download + place
"""
from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Public Drive folder share. Anyone with the link can view. Sharing as folder
# means a single ID covers all 9 inputs.
GDRIVE_FOLDER_ID = "1VQF_Qldg3JhZJRi5DUYNWiyu6R6qdPzN"


# (relative path inside the Drive folder, dest relative to PROJECT_ROOT, brand, kind, size_estimate)
# kind: "file" copies; "zip" extracts contents into dest dir.
PLAN: list[tuple[str, str, str | None, str, int]] = [
    ("influencer_pool/_pool_embeddings.npz",
     "source/sns-influencer-output/_pool_embeddings.npz", None, "file", 65_000_000),
    ("influencer_pool/labels_adapted_index.jsonl",
     "source/sns-influencer-output/labels_adapted_index.jsonl", None, "file", 20_000_000),
    ("influencer_pool/_pool_taxonomy.json",
     "source/sns-influencer-output/_pool_taxonomy.json", None, "file", 4_000),
    ("imc_plans/20260503_DV_27SS_imc_plan.json",
     "marketing_builder/samples/20260503_DV_27SS/05_marketing/output/imc_plan.json",
     "DV", "file", 100_000),
    ("imc_plans/20260503_DX_26FW_imc_plan.json",
     "marketing_builder/output/20260503_DX_26FW/05_marketing/output/imc_plan.json",
     "DX", "file", 100_000),
    ("imc_plans/20260503_MLB_27SS_imc_plan.json",
     "marketing_builder/output/20260503_MLB_27SS/05_marketing/output/imc_plan.json",
     "MLB", "file", 100_000),
    ("products_resource/DV.zip", "products_resource/DV", "DV", "zip", 80_000_000),
    ("products_resource/DX.zip", "products_resource/DX", "DX", "zip", 42_000_000),
    ("products_resource/MLB.zip", "products_resource/MLB", "MLB", "zip", 76_000_000),
]


STAGING = PROJECT_ROOT / "_drive_staging_tmp"  # where gdown drops the folder


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def _exists(plan_entry) -> bool:
    _, dst_rel, _, kind, _ = plan_entry
    p = PROJECT_ROOT / dst_rel
    if kind == "zip":
        return p.is_dir() and any(p.iterdir())
    return p.exists()


def _filter(brands):
    if not brands:
        return list(PLAN)
    bset = set(brands)
    return [e for e in PLAN if e[2] is None or e[2] in bset]


def _fetch_folder():
    """Run gdown once for the entire folder. Returns the local path."""
    import gdown
    if STAGING.exists():
        print(f"  [reuse] existing {STAGING} (delete it manually for a fresh fetch)")
        return STAGING
    STAGING.mkdir(parents=True, exist_ok=True)
    url = f"https://drive.google.com/drive/folders/{GDRIVE_FOLDER_ID}"
    gdown.download_folder(url=url, output=str(STAGING), quiet=False, use_cookies=False)
    return STAGING


def _place(plan_entries) -> int:
    fail = 0
    for src_rel, dst_rel, _brand, kind, _size in plan_entries:
        src = STAGING / src_rel
        if not src.exists():
            print(f"  [MISS] {src_rel} not in staging")
            fail += 1
            continue
        dst = PROJECT_ROOT / dst_rel
        if kind == "file":
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            print(f"  [OK  ] {dst_rel}")
        elif kind == "zip":
            dst.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(src) as zf:
                zf.extractall(dst)
            count = sum(1 for _ in dst.rglob("*") if _.is_file())
            print(f"  [OK  ] {dst_rel}/  ({count} files extracted)")
        else:
            print(f"  [ERR ] unknown kind={kind!r}")
            fail += 1
    return fail


def report(items, *, apply: bool) -> int:
    have = [e for e in items if _exists(e)]
    missing = [e for e in items if not _exists(e)]

    print(f"PROJECT_ROOT = {PROJECT_ROOT}")
    print(f"Drive folder = https://drive.google.com/drive/folders/{GDRIVE_FOLDER_ID}")
    print(f"Plan items: {len(items)}  (have {len(have)}, missing {len(missing)})\n")

    if have:
        print("[present]")
        for src_rel, dst_rel, brand, kind, size in have:
            print(f"  {brand or 'ALL':4} {_human(size):>10}  {dst_rel}")

    if missing:
        print("\n[missing]")
        total = 0
        for src_rel, dst_rel, brand, kind, size in missing:
            print(f"  {brand or 'ALL':4} {_human(size):>10}  {dst_rel}")
            total += size
        print(f"\nTotal to fetch: {_human(total)}")

    if not apply:
        if missing:
            print("\n(dry-run — pass --apply to download)")
        return 0

    if not missing:
        print("\nNothing to do.")
        return 0

    try:
        import gdown  # noqa: F401
    except ImportError:
        print("\n[ERROR] gdown not installed.  pip install gdown", file=sys.stderr)
        return 2

    print("\n=== fetching folder ===")
    _fetch_folder()
    print("\n=== placing files ===")
    fail = _place(missing)
    if fail:
        print(f"\n[done] {fail} entries failed")
        return 1
    print("\n[done] all good")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--brand", action="append",
                    help="Limit to one or more brands (DV/DX/MLB). Repeatable.")
    ap.add_argument("--apply", action="store_true",
                    help="Actually download + place (requires gdown).")
    args = ap.parse_args()
    items = _filter(args.brand)
    return report(items, apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
