"""One-time encode of 5,774 SNS records → _pool_embeddings.npz.

Reads labels_marketing_index.jsonl, builds a label-text per record,
embeds via Gemini API (default gemini-embedding-2, 3072-dim), saves npz cache.

CLI:
    python st_cut-dev/scripts/sns_labeling/embed_pool.py [--model X] [--limit N] [--force]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

_THIS = Path(__file__).resolve()
_SCRIPTS = _THIS.parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from sns_labeling.embedder import (
    DEFAULT_MODEL,
    CACHE_PATH,
    embed_texts,
    save_cache,
)

PROJECT_ROOT = _THIS.parents[3]
POOL_JSONL = PROJECT_ROOT / "source" / "sns-influencer-output" / "labels_marketing_index.jsonl"


def _fmt(v) -> str:
    """Coerce list/str/None into a comma-joined lowercase string."""
    if v is None:
        return "unspecified"
    if isinstance(v, list):
        vals = [str(x).strip() for x in v if x]
        return ", ".join(vals) if vals else "unspecified"
    return str(v).strip() or "unspecified"


def record_text(rec: dict) -> str:
    """5-axis label concat into a natural sentence for embedding."""
    m = rec.get("model") or {}
    bg = rec.get("background") or {}
    st = rec.get("styling") or {}
    parts = [
        f"pose: {_fmt(m.get('pose'))}.",
        f"expression: {_fmt(m.get('expression'))}.",
        f"gaze: {_fmt(m.get('gaze direction'))}.",
        f"mood: {_fmt(bg.get('mood'))}.",
        f"location: {_fmt(bg.get('location'))}.",
        f"style: {_fmt(st.get('fashion style'))}.",
        f"coordination: {_fmt(st.get('coordination method'))}.",
    ]
    return " ".join(parts)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--limit", type=int, default=None,
                    help="encode only first N records (test mode)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite existing cache")
    ap.add_argument("--batch-size", type=int, default=100)
    ap.add_argument("--out", default=str(CACHE_PATH))
    args = ap.parse_args()

    out_path = Path(args.out)
    if out_path.exists() and not args.force:
        print(f"[SKIP] {out_path} exists. Use --force to overwrite.")
        return 0

    if not POOL_JSONL.exists():
        print(f"[ERROR] {POOL_JSONL} not found", file=sys.stderr)
        return 1

    post_ids: list[str] = []
    texts: list[str] = []
    skipped = 0
    for line in POOL_JSONL.open(encoding="utf-8"):
        rec = json.loads(line)
        pid = (rec.get("account") or {}).get("post_id")
        if not pid:
            skipped += 1
            continue
        post_ids.append(pid)
        texts.append(record_text(rec))
        if args.limit and len(post_ids) >= args.limit:
            break

    print(f"[INFO] records to embed: {len(post_ids):,}  (skipped no-post_id: {skipped})")
    print(f"[INFO] model: {args.model}  batch_size: {args.batch_size}")
    if texts:
        print(f"[INFO] sample text: {texts[0][:120]}...")

    t0 = time.time()
    vectors = embed_texts(texts, model=args.model, batch_size=args.batch_size)
    elapsed = time.time() - t0
    print(f"[OK] embedded {len(post_ids):,} records  shape={vectors.shape}"
          f"  elapsed={elapsed:.1f}s  rate={len(post_ids)/max(elapsed,1e-3):.1f}/s")

    save_cache(post_ids, vectors, path=out_path)
    size_mb = out_path.stat().st_size / 1e6
    print(f"[OK] wrote {out_path}  ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
