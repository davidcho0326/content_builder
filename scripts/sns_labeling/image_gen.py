"""Image generation: scene brief + reference image -> Gemini campaign cut.

Uses Gemini 2.5 Flash Image (multimodal in/out). Builds the prompt from a
scene_plan entry produced by `campaign_proposal.build_campaign_proposal`.
"""
from __future__ import annotations

import io
import os
import time
from pathlib import Path
from typing import Optional

from PIL import Image
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

DEFAULT_IMAGE_MODEL = os.getenv("F_AND_F_IMAGE_MODEL", "gemini-3-pro-image-preview")

# Brand-locked model keywords (project-docs/prompt-strategy.md §2 — verified)
BRAND_MODEL_KEYWORDS = {
    "duvetica": ("young beautiful Caucasian / Western European model (any gender) — "
                  "fair porcelain skin, light eyes (blue / green / hazel), "
                  "natural blonde or chestnut-brown hair, refined European features, "
                  "angular jawline, high cheekbones, slim editorial proportions, "
                  "editorial-grade beauty. NO Asian / NO Korean facial features — "
                  "use the reference ONLY for pose and composition, replace the face "
                  "with a Caucasian European face"),
    "mlb": ("K-pop girl group member on her day off — tiny small face, "
            "sharp V-line jaw, big double-eyelid eyes, flawless dewy glass skin, "
            "long silky straight black hair, ultra slim with long legs"),
    "discovery": ("stunningly beautiful Korean fitness influencer — tiny face, "
                   "sharp jawline, toned but feminine athletic build, "
                   "sun-kissed glowing skin"),
}


# ---------- prompt build --------------------------------------------------

PROMPT_TEMPLATE = """You are given a REFERENCE photograph. Generate a NEW high-end fashion editorial image that closely matches the REFERENCE in:
- POSE and BODY POSITION (replicate the exact pose, limb positions, head angle)
- COMPOSITION and FRAMING (same camera angle, distance, crop, rule-of-thirds placement)
- LIGHTING DIRECTION and QUALITY (same light source direction and mood)

But CHANGE the following based on the brand brief below:

BRAND: {brand}  ({season} — category: {category_key})
POSITIONING: {positioning}

THE MOMENT: {moment}

THE MODEL: {brand_model_keyword}. Age range: {age_range}, {demographics}.
EXPRESSION: {expression} (gaze: {gaze}).
SIGNATURE POSE: {pose}.

SHE IS WEARING: {garment_items}{garment_keypoints}

SETTING: {location}. {architecture}
LIGHTING: {lighting}.
MOOD: {mood}.

STYLING: {fashion_style} style with {coordination} coordination, {color_tone} tone.
ACCESSORIES: {accessories}.
FOOTWEAR: {footwear}.

PHOTOGRAPHY:
- Camera: {camera}, {lens}.
- Film: {film} — visible fine grain, organic tonal transitions.
- Aspect ratio: {aspect_ratio}.

POST-PRODUCTION: rich tonal depth, creamy highlight rolloff, neutral white balance,
visible skin pores and natural skin texture, fine fabric grain.

ANTI-AI DETAILS: {anti_ai}.

NEGATIVE: no Y2K poses, no mirror selfies, no exaggerated cute gestures, no plastic skin, no AI-symmetric features.

CRITICAL: Match the reference photograph's POSE, COMPOSITION, and CAMERA ANGLE as closely as possible. The model should be in the same position and the framing should be nearly identical. Only the garment, styling, and minor setting details should differ."""


def build_prompt_from_scene(scene: dict, campaign: dict) -> str:
    m = scene["model_direction"]
    g = scene["garment_brief"]
    s = scene["setting_direction"]
    st = scene["styling_direction"]
    p = scene["photography_brief"]

    brand_lower_for_fallback = (campaign.get("brand") or "").strip().lower()
    items = ", ".join((g.get("items") or [])[:4]) or f"{(campaign.get('brand') or 'brand').upper()}-style {g.get('category_key') or 'item'}"
    keypoints = f" — {g['key_points']}" if g.get("key_points") else ""
    accessories = ", ".join((st.get("accessories") or [])[:3]) or "minimal"
    footwear = ", ".join((st.get("footwear") or [])[:2]) or "minimal leather"
    anti_ai = ", ".join(p.get("anti_ai") or [])

    brand_lower = (campaign.get("brand") or "").strip().lower()
    brand_kw = BRAND_MODEL_KEYWORDS.get(
        brand_lower,
        f"{m.get('beauty', 'natural minimal makeup')} model, editorial proportions",
    )

    moment = scene.get("moment") or "a natural editorial moment captured candidly mid-flow"

    # season: prefer user-input season-category over brand-dna's stored season
    season_input = (campaign.get("season_category_input") or "").upper()
    season_token = next((tok for tok in season_input.split() if tok and tok[:2].isdigit()),
                        campaign.get("season", ""))

    return PROMPT_TEMPLATE.format(
        brand=campaign.get("brand", ""),
        brand_model_keyword=brand_kw,
        moment=moment,
        season=season_token,
        category_key=g.get("category_key", "") or "",
        positioning=campaign.get("positioning", ""),
        age_range=m.get("age_range", "20s-30s"),
        demographics=m.get("demographics", "Asian"),
        expression=m.get("expression", "expressionless"),
        gaze=m.get("gaze", "camera"),
        pose=m.get("pose", "stand"),
        garment_items=items,
        garment_keypoints=keypoints,
        location=s.get("location", "studio"),
        architecture=s.get("architecture", "") or "",
        lighting=s.get("lighting", "natural soft daylight"),
        mood=s.get("mood") or "chic",
        fashion_style=st.get("fashion_style") or "casual",
        coordination=st.get("coordination") or "tone-on-tone",
        color_tone=st.get("color_tone") or "neutral tone",
        accessories=accessories,
        footwear=footwear,
        camera=p.get("camera", "Hasselblad 500CM"),
        lens=p.get("lens", "85mm f/1.8"),
        film=p.get("film", "Kodak Portra 400"),
        aspect_ratio=p.get("aspect_ratio", "3:4 portrait"),
        anti_ai=anti_ai,
    )


# ---------- Gemini call ---------------------------------------------------

def _client() -> "genai.Client":
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    return genai.Client(api_key=key)


def _image_part(path: Path) -> types.Part:
    img = Image.open(path).convert("RGB")
    if max(img.size) > 1024:
        img.thumbnail((1024, 1024), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=buf.getvalue()))


def generate_scene(
    scene: dict,
    campaign: dict,
    out_dir: Path,
    *,
    model: Optional[str] = None,
    retries: int = 2,
) -> dict:
    """Generate one campaign cut. Returns metadata dict."""
    out_dir.mkdir(parents=True, exist_ok=True)
    sid = scene["scene_id"]
    ref_path = Path(scene["reference"]["image"]) if scene["reference"].get("image") else None
    if not (ref_path and ref_path.exists()):
        return {"scene_id": sid, "provider": "gemini", "status": "skip",
                "error": f"reference image missing: {ref_path}"}

    prompt = build_prompt_from_scene(scene, campaign)
    (out_dir / f"{sid}_prompt.txt").write_text(prompt, encoding="utf-8")
    # Save a copy of the reference for traceability
    try:
        ref_img = Image.open(ref_path).convert("RGB")
        ref_img.thumbnail((1024, 1024), Image.LANCZOS)
        ref_img.save(out_dir / f"{sid}_00_reference.jpg", quality=92)
    except Exception:
        pass

    model_name = model or DEFAULT_IMAGE_MODEL
    client = _client()
    contents = [
        types.Content(
            role="user",
            parts=[types.Part(text=prompt), _image_part(ref_path)],
        )
    ]
    cfg = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        # temperature affects diversity but image API may not honour
    )

    last_err: Optional[BaseException] = None
    t0 = time.time()
    for attempt in range(1, retries + 1):
        try:
            resp = client.models.generate_content(
                model=model_name, contents=contents, config=cfg
            )
            for part in (resp.candidates[0].content.parts or []):
                if hasattr(part, "inline_data") and part.inline_data:
                    img = Image.open(io.BytesIO(part.inline_data.data)).convert("RGB")
                    out = out_dir / f"{sid}_gemini.png"
                    img.save(out)
                    elapsed = time.time() - t0
                    return {
                        "scene_id": sid,
                        "provider": "gemini",
                        "status": "ok",
                        "model": model_name,
                        "image": str(out).replace("\\", "/"),
                        "reference": str(ref_path).replace("\\", "/"),
                        "elapsed_sec": round(elapsed, 2),
                    }
            last_err = RuntimeError("no image part in response")
        except Exception as e:
            last_err = e
            wait = 5 * attempt
            if attempt < retries:
                time.sleep(wait)
                continue
    return {
        "scene_id": sid,
        "provider": "gemini",
        "status": "fail",
        "model": model_name,
        "error": f"{type(last_err).__name__ if last_err else 'unknown'}: {last_err}",
        "reference": str(ref_path).replace("\\", "/"),
    }


def generate_campaign(
    proposal: dict,
    out_dir: Path,
    *,
    model: Optional[str] = None,
    max_workers: int = 3,
) -> dict:
    """Generate all scenes from a proposal in parallel."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    campaign = proposal["campaign"]
    scenes = proposal["scene_plan"]
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(generate_scene, s, campaign, out_dir, model=model): s for s in scenes}
        for fu in as_completed(futs):
            r = fu.result()
            results.append(r)
            print(f"  [{r['status'].upper()}] {r['scene_id']}"
                   + (f" -> {r.get('image')}" if r.get('image') else f" :: {r.get('error','')}"))
    return {
        "model": model or DEFAULT_IMAGE_MODEL,
        "n_scenes": len(scenes),
        "ok": sum(1 for r in results if r["status"] == "ok"),
        "fail": sum(1 for r in results if r["status"] == "fail"),
        "skip": sum(1 for r in results if r["status"] == "skip"),
        "results": results,
    }


__all__ = [
    "DEFAULT_IMAGE_MODEL",
    "build_prompt_from_scene",
    "generate_scene",
    "generate_campaign",
]
