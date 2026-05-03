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


# ---------- IMC-driven prompt (v3, Option α) -----------------------------

IMC_PROMPT_TEMPLATE = """You are given a REFERENCE photograph. Generate a NEW high-end fashion editorial image for the campaign described below.

USE THE REFERENCE FOR (anchor):
- POSE and BODY POSITION (replicate the exact pose, limb positions, head angle)
- COMPOSITION and FRAMING (same camera angle, distance, crop, rule-of-thirds placement)
- The MODEL'S age range, gender, and proportions

IGNORE FROM THE REFERENCE (replace entirely):
- Setting, location, background, architecture
- Lighting and color grading
- Clothing, accessories, footwear
- Color palette and styling

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

WEARING (PRODUCT-AWARE COORDINATION):
- HERO ({hero_code}) = real product visual:
{hero_visual_block}
- BOTTOM ({bottom_code}) = real product visual:
{bottom_visual_block}
- COORDINATED ITEMS (from brand DNA · theme: {coord_theme}):
    Top suggestion (if hero is bottom): {coord_top_suggestion}
    Cap/Hat: {coord_hat}
    Footwear: {coord_footwear}
    Accessories: {coord_accessories}
    Style notes: {coord_styling_note}

COLOR HARMONY:
- Hero garment color leads: {hero_color_lead}
- Scene tone shapes background: {scene_tone}
- Brand palette accent: {coord_color_palette}

PHOTOGRAPHY:
- Camera: {camera}, {lens}.
- Film: {film} — visible fine grain, organic tonal transitions.
- Aspect ratio: {aspect_ratio}.

POST-PRODUCTION: rich tonal depth, creamy highlight rolloff, neutral white balance,
visible skin pores and natural skin texture, fine fabric grain.

ANTI-AI DETAILS: {anti_ai}.

NEGATIVE: no Y2K poses, no mirror selfies, no exaggerated cute gestures, no plastic skin, no AI-symmetric features, no team mascots in the foreground.

CRITICAL: Match the REFERENCE photograph's POSE / COMPOSITION / CAMERA ANGLE precisely. The model's SETTING, COLOR PALETTE, CLOTHING, and ACCESSORIES must match the SCENE BRIEF above — NOT the reference image. The TONE & COLOR direction ({scene_tone}) must dominate the rendered image's color grading."""


def _format_garment_visual_block(code: str, desc: str, analysis) -> str:
    """Compose multi-line visual description for a garment (hero or bottom).

    Falls back to imc desc when analysis is None (v3.3 behavior).
    """
    indent = "    "
    if analysis is None:
        line = (desc or "(unspecified)").strip()
        return f"{indent}{line}"

    def _g(name, default=""):
        v = getattr(analysis, name, None)
        return v if v else default

    bits = []
    gtype = _g("garment_type")
    cat = _g("category")
    if gtype or cat:
        bits.append(f"type: {gtype} / category: {cat}".strip(" /"))

    pc = _g("primary_color")
    sc_raw = _g("secondary_colors")
    if pc:
        sc_text = (", ".join(sc_raw) if isinstance(sc_raw, list) else str(sc_raw)) if sc_raw else ""
        bits.append(f"color: {pc}" + (f" (+ {sc_text})" if sc_text else ""))

    mat = _g("material_appearance") or _g("material")
    pat = _g("pattern")
    if mat or pat:
        bits.append(f"material: {mat or '-'}, pattern: {pat or '-'}")

    fit = _g("fit_style") or _g("fit")
    logo = _g("logo")
    if fit or logo:
        bits.append(f"fit: {fit or '-'}, logo: {logo or '-'}")

    details = _g("key_details")
    if details:
        d_text = "; ".join(details) if isinstance(details, list) else str(details)
        bits.append(f"key details: {d_text}")

    if not bits:
        return f"{indent}{(desc or '(unspecified)').strip()}"
    return "\n".join(f"{indent}{b}" for b in bits)


def build_prompt_from_imc_scene(
    scene,                        # imc_plan_loader.Scene
    spec,                         # imc_plan_loader.CampaignSpec
    ref: dict,                    # selected reference (selector_v3 output)
    *,
    moment: Optional[str] = None,
    accessories: Optional[str] = None,        # legacy, used only when product_context is None
    footwear: Optional[str] = None,           # legacy
    product_context: Optional[dict] = None,   # v3.4 product-aware Step C
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

    # v3.4 product-aware Step C: build hero/bottom visual blocks + coord.
    # When product_context is None (v3.3 fallback), all blocks degrade gracefully
    # to the imc_plan text-only description.
    pc = product_context or {}
    hero_match = pc.get("hero_match")
    bottom_match = pc.get("bottom_match")
    hero_analysis = pc.get("hero_analysis")
    bottom_analysis = pc.get("bottom_analysis")
    coord = pc.get("coord_block") or {}

    hero_code_disp = (hero_match.code if hero_match
                      else (spec.hero_garment.get("code") or ""))
    hero_desc_text = (spec.hero_garment.get("desc") or "")
    hero_visual_block = _format_garment_visual_block(
        hero_code_disp, hero_desc_text, hero_analysis,
    )

    bottom_code_disp = (bottom_match.code if bottom_match
                        else (spec.sub_garments[0].get("code") if spec.sub_garments else ""))
    bottom_desc_text = (spec.sub_garments[0].get("desc")
                        if spec.sub_garments else "")
    bottom_visual_block = _format_garment_visual_block(
        bottom_code_disp, bottom_desc_text, bottom_analysis,
    )

    hero_color_lead = (
        getattr(hero_analysis, "primary_color", None) if hero_analysis
        else "(per scene tone)"
    ) or "(per scene tone)"

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
        hero_code=hero_code_disp or "(none)",
        hero_visual_block=hero_visual_block,
        bottom_code=bottom_code_disp or "(none)",
        bottom_visual_block=bottom_visual_block,
        coord_theme=coord.get("theme_key") or "(no theme matched)",
        coord_top_suggestion=coord.get("coord_top_suggestion") or "(n/a — hero is top)",
        coord_hat=coord.get("coord_hat") or "(unspecified)",
        coord_footwear=coord.get("coord_footwear")
                        or (footwear or "scene-appropriate footwear"),
        coord_accessories=coord.get("coord_accessories")
                            or (accessories or "minimal scene-appropriate items"),
        coord_styling_note=coord.get("coord_styling_note") or "",
        coord_color_palette=coord.get("coord_color_palette") or "(scene tone leads)",
        hero_color_lead=hero_color_lead,
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
