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


# ---------- IMC-driven moment (v3, Option α) ------------------------------

IMC_MOMENT_PROMPT = """You are a fashion editorial creative director writing the "THE MOMENT" line for a campaign brief.

Look at the reference photograph for POSE and BODY POSITION cues only. The actual setting, lighting, and styling will be replaced — your moment must describe an action that fits the SCENE BRIEF below, NOT the reference's original setting.

CAMPAIGN: {brand} {season} — {lifestyle}
HEADLINE: "{headline_en}" / "{headline_ko}"
KEYWORDS: {keywords_csv}

SCENE {scene_num}: {scene_title}
- Tone & Color: {scene_tone}
- Mood: {scene_mood}
- Location: {scene_location}
- Visual: {scene_visual}
- Target influencer profile: {scene_influencer_profile}

PERSONA (for voice): {persona_name} ({persona_demo})

Style requirements:
- ONE natural English sentence, 18~30 words.
- Describe the subject mid-action in the SCENE's location — light stick raised at Jamsil cheer line, a soft pause on the Songridan café terrace, a backstage glance through the Dugout Lounge curtain, etc.
- Anchor at least one sensory detail from the scene's TONE & COLOR (e.g. mint accent, golden afternoon, fluorescent green).
- Match the body posture visible in the reference, but place it inside the SCENE.
- Editorial, candid, present-progressive feel — NOT posed.
- DO NOT translate into Korean — keep the moment in English even when scene fields are Korean.

Return strictly this JSON, nothing else:
{{"moment": "<your one-line sentence in English>"}}"""


def _format_imc_context(scene, spec) -> dict:
    keywords_csv = ", ".join(k.get("kw", "") for k in (spec.keywords or [])[:5]) or "(none)"
    persona = spec.persona_by_id(scene.persona_match) or (spec.personas[0] if spec.personas else None)
    cats = getattr(scene, "influencer_categories_match", None) or []
    influencer_profile = ", ".join(cats[:6]) if cats else "(unspecified)"
    return {
        "brand": spec.brand or "",
        "season": spec.season or "",
        "lifestyle": spec.lifestyle_display or spec.lifestyle or "",
        "headline_en": spec.headline_en or "",
        "headline_ko": spec.headline_ko or "",
        "keywords_csv": keywords_csv,
        "scene_num": scene.num,
        "scene_title": scene.title,
        "scene_tone": scene.tone or "(unspecified)",
        "scene_mood": scene.mood or "(unspecified)",
        "scene_location": scene.location or "(unspecified)",
        "scene_visual": scene.visual or "(unspecified)",
        "scene_influencer_profile": influencer_profile,
        "persona_name": (persona.name if persona else ""),
        "persona_demo": (persona.demo if persona else ""),
    }


def _extract_one_imc(scene, ref: dict, spec, model: str) -> tuple[str, Optional[str]]:
    """ref: selector_v3 output dict (has 'image', 'post_id', etc.).
    Returns (key, moment) where key = '{scene.slug}__{post_id}'."""
    pid = ref.get("post_id") or "noid"
    key = f"{scene.slug}__{pid}"
    ref_path_str = ref.get("image")
    if not ref_path_str:
        return key, None
    ref_path = Path(ref_path_str)
    if not ref_path.exists():
        return key, None
    ctx = _format_imc_context(scene, spec)
    prompt = IMC_MOMENT_PROMPT.format(**ctx)
    try:
        img = preprocess(ref_path)
        res = call_vlm_json(prompt, img, model=model, temperature=0.5, retries=2)
        moment = (res.get("data") or {}).get("moment")
        if isinstance(moment, str):
            moment = moment.strip().strip('"').strip()
            if moment:
                return key, moment
    except Exception as e:
        print(f"  [imc-moment-fail] {key}: {type(e).__name__}: {e}")
    return key, None


def extract_moments_for_imc(
    spec,                         # CampaignSpec
    refs_by_scene: dict[str, list[dict]],
    *,
    max_workers: int = 6,
    model: Optional[str] = None,
) -> dict[str, str]:
    """Generate one moment per (scene, ref) pair.

    Returns {f"{scene.slug}__{post_id}": moment_str}.
    Caller looks up by that compound key when building per-image prompts.
    """
    model_name = model or DEFAULT_MOMENT_MODEL
    out: dict[str, str] = {}
    jobs: list[tuple] = []
    for scene in spec.scenes:
        for ref in refs_by_scene.get(scene.slug, []) or []:
            jobs.append((scene, ref))
    if not jobs:
        return out
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_extract_one_imc, s, r, spec, model_name): (s, r) for s, r in jobs}
        for fu in as_completed(futs):
            key, moment = fu.result()
            if moment:
                out[key] = moment
                print(f"  [imc-moment] {key}: {moment[:90]}{'…' if len(moment) > 90 else ''}")
            else:
                print(f"  [imc-moment] {key}: (none — fallback)")
    return out


__all__ = [
    "DEFAULT_MOMENT_MODEL",
    "FALLBACK_MOMENT",
    "MOMENT_PROMPT",
    "IMC_MOMENT_PROMPT",
    "extract_moments_for_scenes",
    "extract_moments_for_imc",
]
