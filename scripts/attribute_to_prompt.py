# WORKFLOW_BYPASS_OK: strategy-cut-builder custom prompt pipeline (2026-04-30)
"""5속성 JSON → 이미지 생성 프롬프트 변환기

Usage:
    from scripts.strategy_cut_builder.attribute_to_prompt import (
        build_celeb_prompt,
        build_influencer_prompt,
    )
"""

import json


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _outfit_section(attrs: dict) -> str:
    fab = attrs["attributes"]["fabric"]["sub"]["prompt"]
    top = attrs["attributes"]["fit"]["sub"]["top"]["prompt"]
    bot = attrs["attributes"]["fit"]["sub"]["bottom"]["prompt"]
    sheen = attrs["attributes"]["sheen"]["sub"]["prompt"]
    weight = attrs["attributes"]["weight"]["sub"]["prompt"]
    color = attrs["color"]["prompt"]
    styling = attrs["styling"]["prompt"]

    return f"""[PRODUCT — REPRODUCE EXACTLY FROM REFERENCE IMAGES]
Fabric: {fab}
Top: {top}
Bottom: {bot}
Surface finish: {sheen}
Weight: {weight}
Color: {color}
Styling: {styling}"""


def _mood_section(dna: dict) -> str:
    mood = ", ".join(dna["mood"])
    return f"""[BRAND MOOD]
Positioning: {dna['positioning']}
Mood: {mood}
Lighting: {dna['setting']['lighting']}
Environment: {dna['setting']['architecture']}
Tone: {dna['photography']['tone']}"""


CELEB_VARIATIONS = [
    {
        "framing": "full body shot",
        "angle": "eye level, slightly angled 3/4 view",
        "pose": "standing relaxed with weight on one leg, one hand in pocket",
    },
    {
        "framing": "upper body, waist-up",
        "angle": "slightly low angle, looking up at model",
        "pose": "leaning against a stone wall, arms crossed casually",
    },
    {
        "framing": "environmental portrait, medium shot",
        "angle": "profile view with head turned toward camera",
        "pose": "walking casually, mid-stride, looking back over shoulder",
    },
]

INFLUENCER_VARIATIONS = [
    {
        "framing": "full body, mirror selfie style",
        "angle": "eye level, phone held at chest height",
        "pose": "standing in front of a mirror, casual pose, one hand holding phone",
        "scenario": "getting ready at a resort hotel room",
    },
    {
        "framing": "upper body, candid snap",
        "angle": "slightly above eye level (friend taking photo)",
        "pose": "sitting at a cafe terrace, leaning back, holding coffee",
        "scenario": "morning coffee at a European coastal cafe",
    },
    {
        "framing": "full body, street snap",
        "angle": "eye level, casual snapshot",
        "pose": "walking on a stone-paved street, looking at phone, caught mid-step",
        "scenario": "exploring a Mediterranean town in the afternoon",
    },
]


def build_celeb_prompt(attrs: dict, dna: dict, variation: int = 0) -> str:
    v = CELEB_VARIATIONS[variation % len(CELEB_VARIATIONS)]
    model = dna["model"]
    locations = ", ".join(dna["setting"]["location"][:3])

    return f"""Generate a high-end fashion editorial photograph.

{_mood_section(dna)}

[MODEL]
Age: {model['age_range']}
Beauty: {model['beauty']}
Expression: Confident editorial gaze, relaxed elegance
Body: Fashion model proportions, 170-175cm
Hair: Natural, wind-touched

{_outfit_section(attrs)}

[SETTING]
Location: {locations}
Architecture: {dna['setting']['architecture']}
Lighting: {dna['setting']['lighting']}

[COMPOSITION]
Framing: {v['framing']}
Camera angle: {v['angle']}
Pose: {v['pose']}

[PHOTOGRAPHY]
Style: {dna['photography']['style']}
Tone: {dna['photography']['tone']}
Quality: Magazine editorial, sharp focus, natural skin
NO golden/warm cast, NO plastic skin, NO AI artifacts
Cool to neutral color temperature

[CRITICAL]
Reproduce the outfit EXACTLY — boucle texture, ivory white
Matching set: hooded zip-up top + shorts, same fabric
The outfit is the visual focus, the mood carries the brand DNA"""


def build_influencer_prompt(attrs: dict, dna: dict, variation: int = 0) -> str:
    v = INFLUENCER_VARIATIONS[variation % len(INFLUENCER_VARIATIONS)]
    model = dna["model"]

    return f"""Generate a natural, candid influencer photo for Instagram.

{_mood_section(dna)}

[MODEL]
Age: {model['age_range']}
Beauty: {model['beauty']}, dewy skin, minimal makeup
Expression: Candid, {model['expression']}
Body: Natural proportions, relatable beauty
Hair: Effortless, natural

{_outfit_section(attrs)}

[SETTING]
Scenario: {v['scenario']}
Location feel: {', '.join(dna['setting']['location'][:3])}
Lighting: Natural daylight, soft warm but NOT golden/amber
Architecture: {dna['setting']['architecture']}

[COMPOSITION]
Framing: {v['framing']}
Camera angle: {v['angle']}
Pose: {v['pose']}
Feel: Casual iPhone snap, NOT professional photoshoot

[PHOTOGRAPHY]
Shot on iPhone 16 Pro
Slightly soft focus, natural grain OK
NOT over-processed, NOT HDR
Real authentic influencer aesthetic

[CRITICAL]
This should look like a REAL person posted on Instagram
Outfit clearly visible — ivory boucle matching set
Candid, effortless, "I just threw this on" energy
NO posed editorial feel, NO studio lighting"""
