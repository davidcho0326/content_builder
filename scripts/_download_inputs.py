"""Fetch pipeline inputs from Google Drive public links.

Each entry in MANIFEST has either a file ID (single file) or a folder ID
(small folder, <= 50 items). For large directories like products_resource/,
zip the brand folder once and ship as a single file — far more reliable than
folder downloads.

How to obtain a Drive ID:
- Right-click the file/folder in Drive → "Get link" → "Anyone with the link"
- The ID is the segment between /d/ and /view (file) or after /folders/ (folder)
  https://drive.google.com/file/d/<FILE_ID>/view
  https://drive.google.com/drive/folders/<FOLDER_ID>

Usage:
    pip install gdown
    python st_cut-dev/scripts/_download_inputs.py            # dry-run, lists missing
    python st_cut-dev/scripts/_download_inputs.py --apply    # actually download
    python st_cut-dev/scripts/_download_inputs.py --brand MLB --apply
"""
from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Iterable, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# Fill in IDs once the Drive shares are created. Set value to None to keep an
# entry in the manifest as a placeholder until its share is published.
#
# kind:
#   "file"        — single file, lands at dest_path
#   "zip"         — single zip archive, extracted into dest_path (parent dir)
#   "folder"      — small Drive folder (<=50 items), mirrored into dest_path
MANIFEST: list[dict] = [
    # influencer pool
    {
        "kind": "file",
        "id": None,  # TODO: paste Drive file ID for _pool_embeddings.npz
        "dest": "source/sns-influencer-output/_pool_embeddings.npz",
        "size": 65_000_000,
        "brand": None,
    },
    {
        "kind": "file",
        "id": None,  # labels_adapted_index.jsonl
        "dest": "source/sns-influencer-output/labels_adapted_index.jsonl",
        "size": 20_000_000,
        "brand": None,
    },
    {
        "kind": "file",
        "id": None,  # _pool_taxonomy.json
        "dest": "source/sns-influencer-output/_pool_taxonomy.json",
        "size": 4_000,
        "brand": None,
    },
    # imc_plan per brand (DV currently lives under samples/, others under output/)
    {
        "kind": "file",
        "id": None,  # DV imc_plan.json
        "dest": "marketing_builder/samples/20260503_DV_27SS/05_marketing/output/imc_plan.json",
        "size": 100_000,
        "brand": "DV",
    },
    {
        "kind": "file",
        "id": None,  # DX imc_plan.json
        "dest": "marketing_builder/output/20260503_DX_26FW/05_marketing/output/imc_plan.json",
        "size": 100_000,
        "brand": "DX",
    },
    {
        "kind": "file",
        "id": None,  # MLB imc_plan.json
        "dest": "marketing_builder/output/20260503_MLB_27SS/05_marketing/output/imc_plan.json",
        "size": 100_000,
        "brand": "MLB",
    },
    # products_resource — ship as one zip per brand
    {
        "kind": "zip",
        "id": None,  # DV/ zipped
        "dest": "products_resource/DV",
        "size": 80_000_000,
        "brand": "DV",
    },
    {
        "kind": "zip",
        "id": None,  # DX/ zipped
        "dest": "products_resource/DX",
        "size": 42_000_000,
        "brand": "DX",
    },
    {
        "kind": "zip",
        "id": None,  # MLB/ zipped
        "dest": "products_resource/MLB",
        "size": 76_000_000,
        "brand": "MLB",
    },
]


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def _abs(rel: str) -> Path:
    return PROJECT_ROOT / rel


def _exists(entry: dict) -> bool:
    p = _abs(entry["dest"])
    if entry["kind"] == "zip" or entry["kind"] == "folder":
        return p.is_dir() and any(p.iterdir())
    return p.exists()


def _filter(brands: Optional[Iterable[str]]) -> list[dict]:
    if not brands:
        return list(MANIFEST)
    bset = set(brands)
    return [e for e in MANIFEST if e.get("brand") is None or e["brand"] in bset]


def _download_one(entry: dict) -> bool:
    import gdown  # imported here so dry-run works without the dep

    fid = entry["id"]
    if not fid:
        print(f"  [SKIP] no Drive ID configured for {entry['dest']}")
        return False

    dest = _abs(entry["dest"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    kind = entry["kind"]

    if kind == "file":
        gdown.download(id=fid, output=str(dest), quiet=False)
        return dest.exists()

    if kind == "zip":
        # land the zip in a tmp file next to dest, extract, delete
        tmp = dest.parent / (dest.name + ".gdown.zip")
        gdown.download(id=fid, output=str(tmp), quiet=False)
        if not tmp.exists():
            return False
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(tmp) as zf:
            zf.extractall(dest)
        tmp.unlink()
        return any(dest.iterdir())

    if kind == "folder":
        dest.mkdir(parents=True, exist_ok=True)
        gdown.download_folder(id=fid, output=str(dest), quiet=False, use_cookies=False)
        return any(dest.iterdir())

    print(f"  [ERROR] unknown kind={kind!r} for {entry['dest']}")
    return False


def report(items: list[dict], *, apply: bool) -> int:
    have = [e for e in items if _exists(e)]
    missing = [e for e in items if not _exists(e)]

    print(f"PROJECT_ROOT = {PROJECT_ROOT}")
    print(f"Manifest items: {len(items)}  (have {len(have)}, missing {len(missing)})\n")

    if have:
        print("[present]")
        for e in have:
            tag = e.get("brand") or "ALL"
            print(f"  {tag:4} {_human(e['size']):>10}  {e['dest']}")

    if missing:
        print("\n[missing]")
        total = 0
        unconfigured = 0
        for e in missing:
            tag = e.get("brand") or "ALL"
            mark = "  " if e["id"] else "??"
            print(f"  {tag:4} {_human(e['size']):>10}  {mark}  {e['dest']}")
            total += e["size"]
            if not e["id"]:
                unconfigured += 1
        print(f"\nTotal to fetch: {_human(total)}")
        if unconfigured:
            print(f"({unconfigured} entries have no Drive ID set — paste them in scripts/_download_inputs.py)")

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

    print("\n=== applying ===")
    fail = 0
    for e in missing:
        if not e["id"]:
            print(f"  [SKIP] {e['dest']} — no Drive ID")
            fail += 1
            continue
        print(f"  [GET ] {e['dest']}")
        ok = _download_one(e)
        if not ok:
            print(f"  [FAIL] {e['dest']}")
            fail += 1
    return 1 if fail else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--brand", action="append",
                    help="Limit to one or more brands (DV/DX/MLB). Repeatable.")
    ap.add_argument("--apply", action="store_true",
                    help="Actually download (requires gdown + Drive IDs filled in).")
    args = ap.parse_args()
    items = _filter(args.brand)
    return report(items, apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
