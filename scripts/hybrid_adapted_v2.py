"""Hybrid join: external labels_adapted (items + common preserved) + v2 marketing dimensions.

For each post_id present in both:
  - take labels_adapted record as base (keeps items[], common, detected_categories)
  - overwrite model / background / styling / free_text with v2 (re-labeled, has gaze/hair/skin/...)
  - vlm + image fields prefer v2 (newer)

Output:
  source/sns-influencer-output/labels_adapted_v2_index.jsonl

CLI:
    python st_cut-dev/scripts/hybrid_adapted_v2.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC = PROJECT_ROOT / "source" / "sns-influencer-output"
ADAPTED = SRC / "labels_adapted_index.jsonl"
V2_MKT = SRC / "labels_marketing_v2_index.jsonl"
OUT = SRC / "labels_adapted_v2_index.jsonl"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")

    # index v2 by post_id
    v2_by_id = {}
    for line in V2_MKT.open(encoding="utf-8"):
        rec = json.loads(line)
        pid = (rec.get("account") or {}).get("post_id")
        if pid:
            v2_by_id[pid] = rec
    print(f"[INFO] v2 marketing records indexed: {len(v2_by_id):,}")

    n_in = n_joined = n_no_v2 = 0
    with OUT.open("w", encoding="utf-8") as f:
        for line in ADAPTED.open(encoding="utf-8"):
            rec = json.loads(line)
            n_in += 1
            pid = (rec.get("account") or {}).get("post_id")
            if pid and pid in v2_by_id:
                v2 = v2_by_id[pid]
                # Overwrite marketing dimensions with v2 (rich)
                rec["model"] = v2.get("model", rec.get("model"))
                rec["background"] = v2.get("background", rec.get("background"))
                rec["styling"] = v2.get("styling", rec.get("styling"))
                rec["free_text"] = v2.get("free_text", rec.get("free_text"))
                # Prefer v2 image meta (sha256/width/height filled by our pipeline)
                if v2.get("image"):
                    img_old = rec.get("image") or {}
                    img_new = v2["image"]
                    # keep adapted's path if v2 path is empty
                    rec["image"] = {**img_old, **{k: v for k, v in img_new.items() if v}}
                rec["vlm"] = v2.get("vlm", rec.get("vlm"))
                n_joined += 1
            else:
                n_no_v2 += 1
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"[OK] adapted records  : {n_in:,}")
    print(f"     joined with v2   : {n_joined:,}")
    print(f"     no v2 match      : {n_no_v2}")
    print(f"     output           : {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
