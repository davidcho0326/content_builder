"""Build a brand-DNA ↔ pool-taxonomy alignment table via VLM (text-only).

Per brand: read brand_dna distributions (location/mood/pose/expression/gaze),
ask Gemini to align each DNA token to our pool's closed taxonomy with
weighted 1:N distribution. Cache result next to brand-dna json.

Output: st_cut-dev/brand-dna/_{brand}_alignment.json

Schema:
{
  "brand": "discovery",
  "model": "gemini-3.1-flash-lite-preview",
  "generated_at": "...",
  "alignments": {
    "location": {
      "studio": [{"target": "café", "weight": 0.4, "rationale": "..."}],
      ...
    },
    "mood": {...}, "pose": {...}, "expression": {...}, "gaze": {...}
  }
}

CLI:
    python st_cut-dev/scripts/sns_labeling/build_alignment.py \
        --brand discovery [--model gemini-3.1-flash-lite-preview] [--force]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from project_paths import BRAND_DNA_DIR, SOURCE_DIR

load_dotenv()

POOL_TAXONOMY = SOURCE_DIR / "_pool_taxonomy.json"

DEFAULT_MODEL = os.getenv("F_AND_F_ALIGNMENT_MODEL", "gemini-3.1-flash-lite-preview")

ALIGN_PROMPT = """You are aligning two fashion-marketing vocabularies for a strategy-cut pipeline.

INPUT:
- brand_dna axis distribution: a dict {{token: probability}}, with tokens written by a marketing planner
- pool_taxonomy: a CLOSED list of values our SNS image labeler emits

YOUR JOB (per axis):
For EACH brand_dna token, distribute its probability mass across one or more
pool_taxonomy values according to semantic match. Weights on each token's
targets MUST sum to 1.0 (this preserves the original distribution).

CONSTRAINTS:
- Output ONLY targets from the provided pool_taxonomy list. Do NOT invent values.
- A token may map 1:1 (one target with weight 1.0) or 1:N (multiple targets,
  weights summing to 1.0). Use 1:N when the brand_dna token is broader than any
  single pool value.
- Be principled: "studio" is a controlled indoor neutral space, closer to
  shopping/store than café. "Urban city" includes both city skylines AND
  street-level scenes. Apply this kind of reasoning.
- One short rationale per target (≤80 chars).

AXIS being aligned: {axis}

brand_dna distribution:
{dna_dist}

pool_taxonomy (allowed targets):
{pool_values}

brand context (for tie-breaking):
{brand_context}

Return JSON in this EXACT shape (no fences, no prose):
{{
  "alignment": {{
    "<dna_token>": [
      {{"target": "<pool_value>", "weight": 0.6, "rationale": "..."}},
      {{"target": "<pool_value>", "weight": 0.4, "rationale": "..."}}
    ],
    ...
  }}
}}
"""


def _client():
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    return genai.Client(api_key=key)


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        first_nl = t.find("\n")
        if first_nl >= 0:
            t = t[first_nl + 1:]
    if t.endswith("```"):
        t = t[:-3]
    return t.strip()


def _call_text_json(prompt: str, *, model: str, retries: int = 3,
                    temperature: float = 0.1) -> dict:
    client = _client()
    contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
    cfg = types.GenerateContentConfig(
        temperature=temperature, response_modalities=["TEXT"],
    )
    last_err = None
    last_text = ""
    for attempt in range(1, retries + 1):
        try:
            resp = client.models.generate_content(
                model=model, contents=contents, config=cfg
            )
            last_text = resp.text or ""
            data = json.loads(_strip_fences(last_text))
            u = getattr(resp, "usage_metadata", None)
            usage = {
                "input_tokens": getattr(u, "prompt_token_count", None) if u else None,
                "output_tokens": getattr(u, "candidates_token_count", None) if u else None,
            }
            return {"data": data, "usage": usage, "raw_text": last_text}
        except json.JSONDecodeError as e:
            last_err = e
            if attempt < retries:
                time.sleep(2 * attempt)
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            wait = 5 * attempt if any(x in msg for x in ("429", "rate", "503", "500")) else 2 * attempt
            if attempt < retries:
                time.sleep(wait)
    raise RuntimeError(f"VLM text call failed after {retries} attempts: {last_err}\n"
                       f"raw[:400]: {last_text[:400]}")


# ----- DNA distribution extraction -----

def _extract_dna_dists(brand_dna: dict) -> dict[str, dict]:
    """Pull raw {token: prob} dicts per axis from marketing_dna."""
    md = brand_dna.get("marketing_dna") or {}
    pose = (md.get("pose") or {}).get("stance_distribution") or {}
    expr = (md.get("expression") or {}).get("base_distribution") or {}
    gaze = (md.get("expression") or {}).get("gaze_distribution") or {}
    bg = md.get("background") or {}
    mood = bg.get("mood_distribution") or {}
    loc = bg.get("location_distribution") or {}
    return {"pose": pose, "expression": expr, "gaze": gaze,
            "mood": mood, "location": loc}


def _validate_alignment(align: dict, axis: str, allowed: set, tokens: set) -> dict:
    """Drop unknown targets; renormalise per-token weights to sum=1.0."""
    out = {}
    for tok, lst in (align or {}).items():
        if tok not in tokens:
            continue
        cleaned = []
        wsum = 0.0
        for t in lst or []:
            tg = (t.get("target") or "").strip()
            w = float(t.get("weight") or 0)
            if tg in allowed and w > 0:
                cleaned.append({"target": tg, "weight": w,
                                 "rationale": (t.get("rationale") or "")[:120]})
                wsum += w
        if not cleaned:
            continue
        if abs(wsum - 1.0) > 0.01:
            for c in cleaned:
                c["weight"] = round(c["weight"] / wsum, 4)
        out[tok] = cleaned
    return out


def _brand_context(brand_dna: dict) -> str:
    bits = []
    for k in ("brand", "season", "positioning", "design_coordinate"):
        v = brand_dna.get(k)
        if isinstance(v, str) and v:
            bits.append(f"{k}: {v}")
    return "\n".join(bits[:5])


def build_alignment(brand_dna: dict, pool_taxonomy: dict, *,
                    model: str = DEFAULT_MODEL) -> dict:
    """Run one VLM call per axis, return full alignment dict."""
    dna = _extract_dna_dists(brand_dna)
    ctx = _brand_context(brand_dna)
    out = {
        "brand": (brand_dna.get("brand") or "").lower().split()[0],
        "model": model,
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "alignments": {},
        "_usage": {},
    }
    for axis in ("location", "mood", "pose", "expression", "gaze"):
        dist = dna.get(axis) or {}
        if not dist:
            print(f"  [skip] {axis}: empty in brand_dna")
            continue
        allowed = set(pool_taxonomy.get(axis) or [])
        if not allowed:
            print(f"  [skip] {axis}: empty pool taxonomy")
            continue
        prompt = ALIGN_PROMPT.format(
            axis=axis,
            dna_dist=json.dumps(dist, ensure_ascii=False, indent=2),
            pool_values=json.dumps(sorted(allowed), ensure_ascii=False),
            brand_context=ctx,
        )
        print(f"  [call] {axis}: {len(dist)} tokens → {len(allowed)} candidates")
        result = _call_text_json(prompt, model=model)
        align_raw = (result["data"] or {}).get("alignment") or {}
        align_clean = _validate_alignment(align_raw, axis, allowed, set(dist.keys()))
        out["alignments"][axis] = align_clean
        out["_usage"][axis] = result["usage"]
        kept = sum(len(v) for v in align_clean.values())
        print(f"    → {len(align_clean)} tokens aligned, {kept} target rows")
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", required=True, help="duvetica | mlb | discovery")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--force", action="store_true",
                    help="overwrite existing alignment.json")
    ap.add_argument("--pool-taxonomy", default=str(POOL_TAXONOMY))
    args = ap.parse_args()

    dna_path = BRAND_DNA_DIR / f"{args.brand}.json"
    if not dna_path.exists():
        print(f"[ERROR] {dna_path} not found", file=sys.stderr)
        return 1
    out_path = BRAND_DNA_DIR / f"_{args.brand}_alignment.json"
    if out_path.exists() and not args.force:
        print(f"[SKIP] {out_path} already exists. Use --force to overwrite.")
        return 0

    brand_dna = json.loads(dna_path.read_text(encoding="utf-8"))
    pool_taxonomy = json.loads(Path(args.pool_taxonomy).read_text(encoding="utf-8"))

    print(f"[align] brand={args.brand} model={args.model}")
    out = build_alignment(brand_dna, pool_taxonomy, model=args.model)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"[OK] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
