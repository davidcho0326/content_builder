# WORKFLOW_BYPASS_OK: strategy-cut-builder custom prompt pipeline (2026-04-30)
"""5속성 JSON → 이미지 생성 프롬프트 변환기 (멀티 브랜드)

Discovery / MLB / Duvetica 각각의 DNA에 맞는 셀럽컷/인플컷 프롬프트 빌드
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
    cap_prompt = attrs.get("cap", {}).get("prompt", "")
    cap_line = f"\nCap: {cap_prompt}" if cap_prompt else ""

    return f"""[PRODUCT — REPRODUCE EXACTLY FROM REFERENCE IMAGES]
Fabric: {fab}
Top: {top}
Bottom: {bot}
Surface finish: {sheen}
Weight: {weight}
Color: {color}{cap_line}
Styling: {styling}"""


BRAND_CONFIGS = {
    "discovery": {
        "celeb_variations": [
            {
                "framing": "full body shot",
                "angle": "eye level, 3/4 view",
                "pose": "standing at rocky coastline, wind in hair, one hand adjusting hood",
            },
            {
                "framing": "medium full shot, knee up",
                "angle": "eye level, front",
                "pose": "leaning against a beige Jeep Wrangler, arms crossed, looking at camera with cool expression",
            },
            {
                "framing": "full body, action shot",
                "angle": "eye level, slightly dynamic",
                "pose": "mid-stride running on a trail, natural athletic movement, golden hour backlight",
            },
        ],
        "influencer_variations": [
            {
                "framing": "full body, street snap",
                "angle": "eye level, casual",
                "pose": "walking on urban street at dusk, coffee in hand, looking at phone",
                "scenario": "evening city walk after a workout",
            },
            {
                "framing": "upper body, candid",
                "angle": "slightly above, friend POV",
                "pose": "sitting on rocky cliff edge, legs dangling, looking out at ocean",
                "scenario": "weekend hike break at a coastal viewpoint",
            },
            {
                "framing": "full body mirror selfie",
                "angle": "eye level, phone at chest",
                "pose": "standing in gym changing room, post-workout glow",
                "scenario": "just finished a morning run, checking outfit in mirror",
            },
        ],
        "mood_builder": lambda dna: f"""[BRAND MOOD]
Positioning: {dna['positioning']}
Mood: Active Wellness, Hi-Tech Casualizing, Outdoor Adventure
Tone: Warm golden for outdoor, cool moody for urban
Core: Sporty chic — functional technical wear that looks fashionable""",
        "setting_builder": lambda dna: f"""[SETTING]
Location: Rocky coastline, Jeep Wrangler nearby, mountain trail, urban night street
Lighting: Golden hour natural warm (outdoor) or cool moody streetlight (urban)
Architecture: Raw rock, concrete, industrial, warm neutral studio""",
        "model_builder": lambda dna: f"""[MODEL]
Age: 20s mid-late
Beauty: Natural glow, minimal makeup, updo hair (bun/ponytail), healthy athletic skin
Expression: Cool + serene mix — confident but approachable, not smiling, quiet strength
Body: Slim-athletic, healthy fit (not muscular), 168-173cm
Demographics: Korean""",
        "photo_style": """[PHOTOGRAPHY]
Style: Outdoor adventure lifestyle + urban street editorial
Tone: Warm earth tones for outdoor, cool blue-grey for urban
Quality: High-end campaign, sharp focus, natural skin texture
NO golden/warm cast, NO plastic skin, NO AI artifacts
Logo: Subtle D logo on chest, not dominant""",
    },
    "mlb": {
        "celeb_variations": [
            {
                "framing": "full body shot",
                "angle": "eye level, 3/4 view",
                "pose": "leaning against concrete wall, one leg bent, hand touching cap brim, cool stare",
            },
            {
                "framing": "medium close-up, waist up",
                "angle": "slightly low angle, looking up",
                "pose": "sitting on concrete steps, legs extended, leaning back on arms, chin slightly raised",
            },
            {
                "framing": "full body, environmental",
                "angle": "eye level, front",
                "pose": "walking on city street, mid-stride, one hand on bag strap, cap shadow over eyes",
            },
        ],
        "influencer_variations": [
            {
                "framing": "full body, street snap",
                "angle": "eye level, casual",
                "pose": "standing by a parked car, leaning on door, iced coffee in hand",
                "scenario": "afternoon in Gangnam/Seongsu trendy neighborhood",
            },
            {
                "framing": "upper body, selfie angle",
                "angle": "slightly above, self-shot",
                "pose": "looking up at camera with cool expression, cap tilted, one hand adjusting collar",
                "scenario": "waiting for friends at a cafe terrace",
            },
            {
                "framing": "full body, candid walking",
                "angle": "eye level, side angle",
                "pose": "walking past a graffiti wall, looking at phone, caught mid-step",
                "scenario": "NYC-vibe street in Seoul, evening golden light",
            },
        ],
        "mood_builder": lambda dna: f"""[BRAND MOOD]
Positioning: HIP FEMININE SPORTIVE
Mood: Urban Cool, Sporty Chic, Trendy Street
Tone: Cool confident attitude, fashion-forward sporty
Core: MLB cap is the brand icon — ALWAYS visible and prominent""",
        "setting_builder": lambda dna: f"""[SETTING]
Location: NYC-inspired urban street, concrete buildings, trendy cafe, stadium area
Lighting: Natural daylight with urban shadows, or warm golden hour on city streets
Architecture: Concrete walls, glass facades, graffiti, modern city""",
        "model_builder": lambda dna: f"""[MODEL]
Age: 20s mid-late
Beauty: Cool effortless beauty, dewy skin, straight black hair flowing under cap, minimal makeup
Expression: COOL and INDIFFERENT (89%) — not smiling, slightly raised chin, confident stare, KARINA-like attitude
Body: Slim, long legs emphasized, 165-172cm
Demographics: Korean female""",
        "photo_style": """[PHOTOGRAPHY]
Style: Urban street editorial with sporty edge
Tone: Cool neutral to warm, high contrast, Instagram-ready
Quality: High-fashion street style, sharp focus, cool color temperature
NO golden/warm cast, NO plastic skin, NO AI artifacts
Logo: NY/LA logo PROMINENT on cap and chest — brand identity MUST be clearly visible""",
    },
}


def build_celeb_prompt(attrs: dict, dna: dict, brand: str, variation: int = 0) -> str:
    cfg = BRAND_CONFIGS[brand]
    v = cfg["celeb_variations"][variation % len(cfg["celeb_variations"])]

    return f"""Generate a high-end fashion campaign photograph.

{cfg['mood_builder'](dna)}

{cfg['model_builder'](dna)}

{_outfit_section(attrs)}

{cfg['setting_builder'](dna)}

[COMPOSITION]
Framing: {v['framing']}
Camera angle: {v['angle']}
Pose: {v['pose']}

{cfg['photo_style']}

[CRITICAL]
Reproduce the outfit EXACTLY as described — fabric, color, fit, accessories
The outfit is the visual focus, the mood carries the brand DNA
Natural proportions, no distortion, no extra fingers"""


def build_influencer_prompt(
    attrs: dict, dna: dict, brand: str, variation: int = 0
) -> str:
    cfg = BRAND_CONFIGS[brand]
    v = cfg["influencer_variations"][variation % len(cfg["influencer_variations"])]

    return f"""Generate a natural, candid influencer photo for Instagram.

{cfg['mood_builder'](dna)}

{cfg['model_builder'](dna)}
Beauty addition: Dewy skin, barely-there makeup, relatable beauty

{_outfit_section(attrs)}

[SETTING]
Scenario: {v['scenario']}
Lighting: Natural daylight, soft warm but NOT golden/amber

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
Outfit clearly visible with all described details
Candid, effortless, "I just threw this on" energy
NO posed editorial feel, NO studio lighting
Natural proportions, no distortion"""
