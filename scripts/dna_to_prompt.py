# WORKFLOW_BYPASS_OK: strategy-cut-builder DNA prompt builder (2026-04-30)
"""Brand DNA JSON → garment/styling prompt auto-generation

Reads any brand DNA JSON and generates garment descriptions for image prompts.
Swap the JSON file to switch between DUVETICA / MLB / DISCOVERY.

Usage:
    from scripts.strategy_cut_builder.dna_to_prompt import build_garment_prompt, build_full_editorial_prompt
"""

import json
import random
from pathlib import Path


def load_dna(brand: str) -> dict:
    dna_dir = (
        Path(__file__).resolve().parents[2]
        / ".claude"
        / "projects"
        / "strategy-cut-builder"
        / "brand-dna"
    )
    path = dna_dir / f"{brand.lower()}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def pick_color(dna: dict, tier: str = "base") -> dict:
    """Pick a random color from the specified tier (base/basic 70% / key/point 20% / accent 10%)."""
    color_data = dna.get("color", {})
    tier_map = {
        "base": ["base", "basic"],
        "key": ["key", "point"],
        "accent": ["accent"],
    }
    if tier == "weighted":
        roll = random.random()
        if roll < 0.7:
            tier = "base"
        elif roll < 0.9:
            tier = "key"
        else:
            tier = "accent"
    for candidate_key in tier_map.get(tier, [tier]):
        if candidate_key in color_data:
            source = color_data[candidate_key]
            colors = (
                source.get("colors", source) if isinstance(source, dict) else source
            )
            if isinstance(colors, list) and colors:
                c = random.choice(colors)
                if isinstance(c, dict):
                    return c
                return {"name": str(c), "code": str(c)}
    all_colors = []
    for v in color_data.values():
        if isinstance(v, list):
            all_colors.extend(v)
        elif isinstance(v, dict) and "colors" in v:
            all_colors.extend(v["colors"])
    if all_colors:
        c = random.choice(all_colors)
        return c if isinstance(c, dict) else {"name": str(c), "code": str(c)}
    return {"name": "white", "code": "WHT"}


def get_fabric_desc(dna: dict, category: str) -> str:
    """Generate fabric description from DNA guardrails."""
    guardrails = dna.get("data_driven_guardrails", {}).get(category, {})
    attrs = guardrails.get("attributes", {})

    fabric_val = attrs.get("fabric", {}).get("median", 4)
    sheen_val = attrs.get("sheen", {}).get("median", 2)
    weight_val = attrs.get("weight", {}).get("median", 2)

    fabric_map = {
        1: "natural premium linen-cotton blend",
        2: "natural-synthetic blend with organic hand-feel",
        3: "mid-weight technical cotton blend",
        4: "lightweight technical nylon with a premium dense weave",
        5: "high-performance technical nylon-polyester",
    }

    sheen_map = {
        1: "completely matte finish",
        2: "soft semi-matte finish that catches light with a subtle sophisticated sheen",
        3: "semi-sheen surface with gentle light reflection",
        4: "semi-glossy finish with visible light play",
        5: "high-gloss polished surface",
    }

    weight_map = {
        1: "ultra-lightweight, almost weightless drape",
        2: "lightweight with fluid natural movement",
        3: "mid-weight with structured but soft drape",
        4: "substantial weight with rich drape",
        5: "heavy structured weight",
    }

    return f"{fabric_map.get(fabric_val, fabric_map[4])}, {sheen_map.get(sheen_val, sheen_map[2])}, {weight_map.get(weight_val, weight_map[2])}"


def get_fit_desc(dna: dict, category: str) -> str:
    guardrails = dna.get("data_driven_guardrails", {}).get(category, {})
    fit_val = guardrails.get("attributes", {}).get("fit", {}).get("median", 3)

    fit_map = {
        1: "skin-tight bodycon",
        2: "slim tailored fit",
        3: "regular relaxed fit",
        4: "relaxed semi-oversized fit",
        5: "dramatically oversized",
    }
    return fit_map.get(fit_val, fit_map[3])


def get_garment_type(dna: dict, category: str) -> str:
    guardrails = dna.get("data_driven_guardrails", {}).get(category, {})
    types = guardrails.get("garment_types", [])
    if types:
        return random.choice(types)
    cat_data = dna.get("categories", {}).get(category, {})
    items = cat_data.get("items", [])
    return random.choice(items) if items else category


def get_styling_details(dna: dict) -> str:
    styling = dna.get("styling", {})
    details = styling.get("details", [])
    accessories = styling.get("accessories", [])
    footwear = styling.get("footwear", [])

    chosen_details = random.sample(details, min(2, len(details))) if details else []
    chosen_acc = (
        random.sample(accessories, min(2, len(accessories))) if accessories else []
    )
    chosen_foot = random.choice(footwear) if footwear else ""

    parts = []
    if chosen_details:
        parts.append(f"styling: {', '.join(chosen_details)}")
    if chosen_acc:
        parts.append(f"accessories: {', '.join(chosen_acc)}")
    if chosen_foot:
        parts.append(f"footwear: {chosen_foot}")
    return ". ".join(parts)


def build_garment_prompt(dna: dict, category: str) -> str:
    """Build a complete garment description from DNA for use in image prompts."""
    brand = dna["brand"]
    color = pick_color(dna, "weighted")
    garment_type = get_garment_type(dna, category)
    fabric = get_fabric_desc(dna, category)
    fit = get_fit_desc(dna, category)
    styling = get_styling_details(dna)

    if category == "setup":
        prompt = (
            f"a {brand} {garment_type} in {color['name'].lower()} ({color['code']}), "
            f"{fit}, {fabric}. "
            f"The top and bottom are a matching tonal set in the same color family. "
            f"Tone-on-tone hardware, minimal branding. {styling}"
        )
    else:
        prompt = (
            f"a {brand} {garment_type} in {color['name'].lower()} ({color['code']}), "
            f"{fit}, {fabric}. "
            f"Hood resting naturally behind the neck, tone-on-tone zipper hardware. "
            f"The fabric drapes with weight and movement showing quality. {styling}"
        )

    return prompt


def get_setting_prompt(dna: dict) -> str:
    """Generate a setting/background description from DNA."""
    settings = dna.get("setting", {})
    locations = settings.get("location", [])
    lighting = settings.get("lighting", "Natural warm light")
    architecture = settings.get("architecture", "")

    location = random.choice(locations) if locations else "Mediterranean resort"
    return f"{location}. {architecture}. Lighting: {lighting}"


def get_model_prompt(dna: dict) -> str:
    """Generate model description from DNA."""
    model = dna.get("model", {})
    age = model.get("age_range", "20s-30s")
    beauty = model.get("beauty", "Clean, natural, minimal makeup")
    expression = model.get("expression", "Relaxed, confident")

    return (
        f"Professional high-fashion model in her {age}. "
        f"Sharp angular jawline, high cheekbones, long elegant neck, defined collarbones. "
        f"Slim editorial proportions. {beauty}. "
        f"Expression: {expression}"
    )


def get_mood_prompt(dna: dict) -> str:
    """Generate mood keywords from DNA."""
    moods = dna.get("mood", [])
    positioning = dna.get("positioning", "")
    return f"Mood: {', '.join(moods)}. Brand positioning: {positioning}"


EDITORIAL_TEMPLATE = """A high-end fashion editorial photograph for Vogue Italia / {brand} campaign, 3:4 portrait orientation.

THIS IS A LUXURY FASHION EDITORIAL. Art-directed by a top creative director, shot by a world-class fashion photographer.

THE MODEL: {model_desc}

THE MOMENT: {moment}

SHE IS WEARING: {garment_desc}

PHOTOGRAPHY:
- Camera: Hasselblad 500CM, {lens}, {aperture}
- Film: {film} — visible fine grain, organic tonal transitions
- {framing}. 3:4 portrait aspect ratio.
- {lighting_desc}

COMPOSITION: Editorial art direction — intentional use of negative space, strong leading lines, subject placed using rule of thirds. Published campaign quality.

SETTING: {setting_desc}

{mood_desc}

POST-PRODUCTION: Analog film grain visible throughout. Rich tonal depth in shadows. Creamy highlight rolloff. Professional fashion retouching — skin flawless but visible texture and pores. Warm, timeless, high-end editorial.

NATURAL DETAILS: wind-displaced strands of hair, fabric caught mid-movement, asymmetric pose, natural skin texture visible."""


def build_full_editorial_prompt(
    dna: dict,
    category: str,
    moment: str,
    lens: str = "85mm f/1.8",
    aperture: str = "f/2.8 — background softly blurred",
    film: str = "Kodak Portra 400 — warm skin tones, soft greens",
    framing: str = "Full body shot, model placed in right third of frame",
    lighting_desc: str = "Late afternoon golden hour sun from the right. Warm soft light with gentle shadows.",
) -> str:
    """Build a complete editorial prompt from DNA + scene description."""
    return EDITORIAL_TEMPLATE.format(
        brand=dna["brand"],
        model_desc=get_model_prompt(dna),
        moment=moment,
        garment_desc=build_garment_prompt(dna, category),
        lens=lens,
        aperture=aperture,
        film=film,
        framing=framing,
        lighting_desc=lighting_desc,
        setting_desc=get_setting_prompt(dna),
        mood_desc=get_mood_prompt(dna),
    )


INFLUENCER_TEMPLATE = """A candid Korean influencer Instagram photo, 3:4 portrait orientation. This should look like a real influencer's feed post — NOT a professional campaign.

THE MODEL: Young Korean woman ({age}). {beauty}. She looks like a popular Korean fashion influencer — naturally pretty, stylish, approachable. NOT a high-fashion editorial model.

THE MOMENT: {moment}

SHE IS WEARING: {garment_desc}

PHOTOGRAPHY:
- Camera: iPhone 15 Pro — sharp but natural smartphone quality, slight computational photography look
- {framing}. 3:4 portrait ratio.
- {lighting_desc}
- Depth: Natural smartphone portrait mode — subject sharp, background has gentle natural blur (not extreme bokeh)

COMPOSITION: Casual influencer composition — slightly off-center, not perfectly composed, feels like a friend took this photo. Could be a mirror selfie, a candid snap, or a posed-but-natural outfit shot.

SETTING: {setting_desc}

STYLE: {mood_desc}

IMAGE QUALITY: This looks like it was posted on Instagram today. Slightly warm filter, maybe a subtle VSCO or Lightroom mobile edit. Clean and bright, not moody or cinematic. The kind of photo that gets 10K likes on a Korean fashion influencer's feed.

NATURAL DETAILS: phone slightly tilted, natural indoor/outdoor lighting, real environment with other people or objects partially visible in background, realistic smartphone lens distortion at edges."""


def get_influencer_model_prompt(dna: dict) -> str:
    model = dna.get("model", {})
    age = model.get("age_range", "early to mid-20s")
    beauty = model.get("beauty", "Dewy skin, natural makeup, long dark hair")
    expression = model.get("expression", "Cool, confident, slightly bored luxury")
    return age, beauty, expression


def build_full_influencer_prompt(
    dna: dict,
    category: str,
    moment: str,
    framing: str = "Full body shot, casual stance",
    lighting_desc: str = "Bright natural daylight, slightly overexposed highlights",
) -> str:
    """Build an influencer-style prompt from DNA + scene description."""
    age, beauty, expression = get_influencer_model_prompt(dna)
    return INFLUENCER_TEMPLATE.format(
        age=age,
        beauty=f"{beauty}. Expression: {expression}",
        moment=moment,
        garment_desc=build_garment_prompt(dna, category),
        framing=framing,
        lighting_desc=lighting_desc,
        setting_desc=get_setting_prompt(dna),
        mood_desc=get_mood_prompt(dna),
    )


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    dna = load_dna("duvetica")

    print("=== GARMENT PROMPTS (random each time) ===\n")
    for cat in ["woven_jacket", "setup"]:
        print(f"--- {cat} ---")
        print(build_garment_prompt(dna, cat))
        print()

    print("=== FULL EDITORIAL PROMPT ===\n")
    prompt = build_full_editorial_prompt(
        dna,
        "woven_jacket",
        moment="she just turned from watching the sunset over the Mediterranean, a half-smile still fading, one hand loosely holding her sunglasses",
    )
    print(prompt)
