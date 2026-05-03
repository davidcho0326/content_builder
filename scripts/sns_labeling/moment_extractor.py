"""LLM-generated `THE MOMENT` line per scene.

Looks at the reference image of each selected scene and asks Gemini to write
a single editorial-director sentence describing the action mid-flow. The
sentence is injected into the image-generation prompt under `THE MOMENT:`
to give per-scene variation that brand-dna single-string fields cannot.

Public API:
    extract_moments_for_scenes(scenes, brand_dna, *, max_workers=6, model=None)
        -> dict[scene_id, moment_string]
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from sns_labeling.vlm_client import call_vlm_json, preprocess

DEFAULT_MOMENT_MODEL = os.getenv(
    "F_AND_F_MOMENT_MODEL", "gemini-3.1-flash-lite-preview"
)
FALLBACK_MOMENT = "a natural editorial moment captured candidly mid-flow"

MOMENT_PROMPT = """You are a fashion editorial creative director writing the "THE MOMENT" line for a campaign brief.

Look at the reference photograph and write ONE single sentence describing the SPECIFIC ACTION + EMOTIONAL MOMENT the model is in. This sentence will be injected into a campaign prompt under the field `THE MOMENT:`.

Brand context: {brand} {season} — category: {category}.
Brand mood: {moods}.
Brand positioning: {positioning}.

Style requirements:
- ONE natural English sentence, 15~30 words.
- Describe an action mid-flow (NOT a static pose). Examples:
    "she just turned her head from gazing at the harbor",
    "she paused mid-step to adjust her scarf",
    "she set down her espresso and looked out toward the cobblestone alley".
- Include a sensory detail (light, fabric, body, surroundings).
- Match the model's actual pose and the surroundings visible in the reference.
- Tone: editorial, candid — NOT posed, NOT generic.

Return strictly this JSON, nothing else:
{{"moment": "<your one-line sentence>"}}"""


def _format_brand_context(brand_dna: dict, category: Optional[str]) -> dict:
    moods = brand_dna.get("mood") or []
    if isinstance(moods, list):
        moods_str = ", ".join(str(m) for m in moods[:5])
    else:
        moods_str = str(moods)
    return {
        "brand": brand_dna.get("brand") or "",
        "season": brand_dna.get("season") or "",
        "category": category or "",
        "moods": moods_str or "(unspecified)",
        "positioning": brand_dna.get("positioning") or "",
    }


def _extract_one(
    scene: dict, brand_dna: dict, model: str
) -> tuple[str, Optional[str]]:
    sid = scene.get("scene_id") or "?"
    ref_path_str = (scene.get("reference") or {}).get("image")
    if not ref_path_str:
        return sid, None
    ref_path = Path(ref_path_str)
    if not ref_path.exists():
        return sid, None
    category = (scene.get("garment_brief") or {}).get("category_key")
    ctx = _format_brand_context(brand_dna, category)
    prompt = MOMENT_PROMPT.format(**ctx)
    try:
        img = preprocess(ref_path)
        res = call_vlm_json(prompt, img, model=model, temperature=0.4, retries=2)
        moment = (res.get("data") or {}).get("moment")
        if isinstance(moment, str):
            moment = moment.strip().strip('"').strip()
            if moment:
                return sid, moment
    except Exception as e:
        print(f"  [moment-fail] {sid}: {type(e).__name__}: {e}")
    return sid, None


def extract_moments_for_scenes(
    scenes: list[dict],
    brand_dna: dict,
    *,
    max_workers: int = 6,
    model: Optional[str] = None,
) -> dict[str, str]:
    """Returns {scene_id: moment_str}. Failures are simply omitted (caller falls back)."""
    model_name = model or DEFAULT_MOMENT_MODEL
    out: dict[str, str] = {}
    if not scenes:
        return out
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_extract_one, s, brand_dna, model_name): s for s in scenes}
        for fu in as_completed(futs):
            sid, moment = fu.result()
            if moment:
                out[sid] = moment
                print(f"  [moment] {sid}: {moment[:90]}{'…' if len(moment) > 90 else ''}")
            else:
                print(f"  [moment] {sid}: (none — fallback will be used)")
    return out


__all__ = [
    "DEFAULT_MOMENT_MODEL",
    "FALLBACK_MOMENT",
    "MOMENT_PROMPT",
    "extract_moments_for_scenes",
]
