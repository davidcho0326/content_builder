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
from sns_labeling.product_grounding import format_product_prompt_section

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


def _flatten_prompt_context(value) -> str:
    """Compact nested label fields into text for prompt-rule detection."""
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(_flatten_prompt_context(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten_prompt_context(v) for v in value)
    return str(value)


def _reference_has_phone_context(ref: dict) -> bool:
    """Detect phone/selfie cues in reference labels."""
    blob = _flatten_prompt_context({
        "model": ref.get("model"),
        "background": ref.get("background"),
        "styling": ref.get("styling"),
        "free_text": ref.get("free_text"),
        "matched_axes": ref.get("matched_axes"),
    }).lower()
    cues = (
        "phone", "smartphone", "iphone", "mobile", "cell phone",
        "handphone", "selfie", "mirror selfie", "phone screen",
        "핸드폰", "휴대폰", "스마트폰", "셀카", "거울셀카",
    )
    return any(cue in blob for cue in cues)


def _phone_context_rule(ref: dict) -> str:
    if _reference_has_phone_context(ref):
        return (
            "PHONE PRESERVATION DETECTED FROM THE REFERENCE LABELS: keep a real "
            "smartphone as a smartphone in the same hand/position/reflection if "
            "Image 1 shows it. Do not remove it and do not transform it into a "
            "bag, cup, light stick, product, IMC prop, or accessory. Other "
            "non-phone items may still be restyled from the campaign tone."
        )
    return (
        "If Image 1 visibly includes a smartphone, selfie capture, mirror-selfie "
        "phone, or phone-held shooting posture, preserve that real smartphone in "
        "the same hand/position/reflection. Treat the phone as pose/capture "
        "context, not as a restylable accessory. If Image 1 does not show a "
        "phone, do not add one."
    )


def _phone_negative_clause(ref: dict) -> str:
    if _reference_has_phone_context(ref):
        return (
            "do not remove or replace the reference phone, no phone-to-bag/cup/"
            "light-stick/prop substitution"
        )
    return "do not add a phone unless Image 1 visibly includes one"


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

PHONE / SELFIE CONTEXT:
- If the reference visibly includes a smartphone, selfie capture, mirror-selfie phone,
  or phone-held shooting posture, preserve a real smartphone as a smartphone in
  the same hand/position/reflection. Do not turn it into another item.
- If the reference does not include a phone, do not add one.

PHOTOGRAPHY:
- Camera: {camera}, {lens}.
- Film: {film} — visible fine grain, organic tonal transitions.
- Aspect ratio: {aspect_ratio}.

POST-PRODUCTION: rich tonal depth, creamy highlight rolloff, neutral white balance,
visible skin pores and natural skin texture, fine fabric grain.

ANTI-AI DETAILS: {anti_ai}.

NEGATIVE: no Y2K poses, do not add a phone unless the reference visibly includes one, no exaggerated cute gestures, no plastic skin, no AI-symmetric features.

CRITICAL: Match the reference photograph's POSE, COMPOSITION, and CAMERA ANGLE as closely as possible. The model should be in the same position and the framing should be nearly identical. Only the garment, styling, and minor setting details should differ."""


# ---------- IMC-driven prompt (v3, Option α) -----------------------------

IMC_PROMPT_TEMPLATE = """You are given input images. Generate a NEW high-end fashion editorial image for the campaign described below.

INPUT IMAGE ROLES:
- Image 1: INFLUENCER REFERENCE. This is the PRIMARY visual authority for the human subject, pose, body position, camera angle, composition, and broad model proportions.
- Image 2: SELECTED PRODUCT. This is NOT a human/pose reference. Use it only for the selected garment's fit, length, silhouette, color, logo/graphic placement, fabric, and construction details.

STRICT INPUT AUTHORITY:
- If Image 2 contains a person, mannequin, model pose, face, hair, body proportions, background, lighting, crop, or styling, ignore all of those completely.
- Never borrow the product-photo model's pose or body. The generated model must follow Image 1.
- Use exactly one fixed product garment from Image 2. Do not force both top and bottom products into the look.
- Generate every non-selected garment, bag, accessory, shoe, and prop from the campaign tone and scene direction.
- A smartphone visible in Image 1 is the exception to accessory restyling: keep it as a real smartphone, because it preserves selfie/phone-held capture logic.

USE THE REFERENCE FOR (anchor):
- POSE and BODY POSITION (replicate the exact pose, limb positions, head angle)
- COMPOSITION and FRAMING (same camera angle, distance, crop, rule-of-thirds placement)
- The MODEL'S age range, gender, and proportions
- Phone/selfie capture context when Image 1 visibly includes a smartphone

IGNORE FROM THE REFERENCE (replace entirely):
- Setting, location, background, architecture
- Lighting and color grading
- Clothing, accessories, footwear, bags, and props, except a smartphone visible in Image 1
- Color palette and styling
- Mirror/selfie/reflection context only when no phone/selfie cue is visible in Image 1

CAMPAIGN: {brand} {season} — {lifestyle}
HEADLINE: "{headline_en}" / "{headline_ko}"
CAMPAIGN KEYWORDS: {keywords_csv}

SCENE {scene_num} · {scene_title}
TONE & COLOR: {scene_tone}
MOOD: {scene_mood}
LOCATION: {scene_location}
VISUAL DIRECTION: {scene_visual}
TARGET INFLUENCER PROFILE: {scene_influencer_profile}

THE MOMENT: {moment}

THE MODEL: {persona_demo}. {brand_model_keyword}.
EXPRESSION: {expression} (gaze: {gaze}).
SIGNATURE POSE: {pose}.

PHONE / SELFIE CONTEXT:
{phone_context_rule}

SINGLE-PRODUCT WARDROBE GROUNDING:
{product_prompt_section}

WEARING BRIEF FROM IMC:
- Hero: {hero_desc}
- Sub: {sub_desc_csv}
ACCESSORIES (scene-appropriate, light): {accessories}
FOOTWEAR: {footwear}

PHOTOGRAPHY:
- Camera: {camera}, {lens}.
- Film: {film} — visible fine grain, organic tonal transitions.
- Aspect ratio: {aspect_ratio}.

POST-PRODUCTION: rich tonal depth, creamy highlight rolloff, neutral white balance,
visible skin pores and natural skin texture, fine fabric grain.

ANTI-AI DETAILS: {anti_ai}.

NEGATIVE: no Y2K poses, no exaggerated cute gestures, no plastic skin, no AI-symmetric features, no team mascots in the foreground, {phone_negative_clause}, do not copy the product-photo model, do not copy the product-photo pose, do not copy the product-photo background.

CRITICAL: Generate the outfit as part of the original editorial shoot, not as a later pasted try-on. Match the INFLUENCER REFERENCE photograph's POSE / COMPOSITION / CAMERA ANGLE precisely. The selected garment must match Image 2's product DNA, but the product image must not influence the model identity, pose, composition, setting, or styling beyond that one garment. The model's SETTING, COLOR PALETTE, complementary wardrobe, bag, accessories, and shoes must match the SCENE BRIEF above. The TONE & COLOR direction ({scene_tone}) must dominate the whole image coherently, including the selected product fabric lighting."""


def build_prompt_from_imc_scene(
    scene,                        # imc_plan_loader.Scene
    spec,                         # imc_plan_loader.CampaignSpec
    ref: dict,                    # selected reference (selector_v3 output)
    *,
    moment: Optional[str] = None,
    accessories: Optional[str] = None,
    footwear: Optional[str] = None,
    outfit_manifest: Optional[dict] = None,
) -> str:
    """Render the IMC-aware prompt for one scene + ref + persona.

    Inputs are dataclass instances (Scene, CampaignSpec) for clarity. Optional
    overrides allow downstream injection of LLM-generated moments and
    scene-specific accessory choices.
    """
    persona = spec.persona_by_id(scene.persona_match) or (spec.personas[0] if spec.personas else None)

    brand_lower = (spec.brand or "").strip().lower()
    brand_kw = BRAND_MODEL_KEYWORDS.get(
        brand_lower,
        "natural minimal makeup model, editorial proportions",
    )

    # Pose / expression / gaze come from the reference's labels — that's the
    # selector's anchor. Defaults are conservative.
    rmodel = ref.get("model") or {}
    pose = (rmodel.get("pose") if isinstance(rmodel.get("pose"), str)
            else (", ".join(rmodel.get("pose") or []) if isinstance(rmodel.get("pose"), list)
                  else "full body shot"))
    expression = (rmodel.get("expression") if isinstance(rmodel.get("expression"), str)
                  else "cool")
    gaze = (rmodel.get("gaze direction") if isinstance(rmodel.get("gaze direction"), str)
            else "front")

    persona_demo = persona.demo if persona and persona.demo else "young adult"

    keywords_csv = ", ".join(k.get("kw", "") for k in (spec.keywords or [])[:5]) or "(none)"
    sub_desc_csv = "; ".join(f"{x.get('code', '')} {x.get('desc', '')}".strip()
                             for x in (spec.sub_garments or [])[:3]) or "(none)"
    scene_influencer_profile = (
        ", ".join(scene.influencer_categories_match[:6])
        if getattr(scene, "influencer_categories_match", None)
        else "(unspecified)"
    )

    return IMC_PROMPT_TEMPLATE.format(
        brand=spec.brand or "",
        season=spec.season or "",
        lifestyle=spec.lifestyle_display or spec.lifestyle or "",
        headline_en=spec.headline_en or "",
        headline_ko=spec.headline_ko or "",
        keywords_csv=keywords_csv,
        scene_num=scene.num,
        scene_title=scene.title,
        scene_tone=scene.tone or "(unspecified)",
        scene_mood=scene.mood or "(unspecified)",
        scene_location=scene.location or "(unspecified)",
        scene_visual=scene.visual or "(unspecified)",
        scene_influencer_profile=scene_influencer_profile,
        moment=moment or "a candid editorial moment captured mid-flow",
        persona_demo=persona_demo,
        brand_model_keyword=brand_kw,
        expression=expression or "cool",
        gaze=gaze or "front",
        pose=pose or "full body shot",
        phone_context_rule=_phone_context_rule(ref),
        phone_negative_clause=_phone_negative_clause(ref),
        product_prompt_section=format_product_prompt_section(outfit_manifest),
        hero_desc=f"[{spec.hero_garment.get('code', '')}] {spec.hero_garment.get('desc', '')}".strip(),
        sub_desc_csv=sub_desc_csv,
        accessories=accessories or "minimal scene-appropriate items",
        footwear=footwear or "scene-appropriate footwear",
        camera="Hasselblad 500CM",
        lens="85mm f/1.8",
        film="Kodak Portra 400",
        aspect_ratio="3:4 portrait",
        anti_ai="wind-displaced hair strands, natural skin texture and pores visible, fabric caught mid-movement, slight imperfect symmetry",
    )


# ---------- legacy (v2) prompt build --------------------------------------

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
