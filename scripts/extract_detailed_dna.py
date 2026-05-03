# WORKFLOW_BYPASS_OK: strategy-cut-builder DNA extraction (2026-04-30)
"""Extract DETAILED marketing DNA matching existing preset format

Targets: woven_jacket + setup marketing images only (~54 images)
Output matches db/presets/duvetica/ pose/expression/background format exactly.

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/extract_detailed_dna.py
"""

import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv

load_dotenv()

from PIL import Image
from google import genai
from google.genai import types

from core.config import VISION_MODEL
from core.api import _get_next_api_key, _pil_to_part

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DNA_DIR = PROJECT_ROOT / "db" / "strategy-cut-builder" / "duvetica" / "_dna"
DNA_DIR.mkdir(parents=True, exist_ok=True)

REPORT_PATH = DNA_DIR / "full_dna_report.json"

POSE_PROMPT = """You are a fashion photography pose analyst. Analyze this DUVETICA campaign image and extract the model's pose in EXTREME detail.

Return valid JSON with these EXACT fields:

{
  "summary": "one-line Korean description of the full pose (e.g. '풀사이드 데크에 앉아 어깨너머로 돌아보는 캔디드 포즈')",
  "stance": "stand / sit / lean / walk / lie_back / recline / crouch",
  "left_arm": {
    "description": "detailed description of left arm position",
    "hand": "what the hand is doing (e.g. 'fingers lightly resting on thigh', 'holding bag strap')",
    "elbow_angle": "approximate angle in degrees (e.g. '140 degrees')",
    "elbow_direction": "direction elbow points (e.g. 'outward', 'forward', 'behind')"
  },
  "right_arm": {
    "description": "detailed description",
    "hand": "what the hand is doing",
    "elbow_angle": "approximate angle",
    "elbow_direction": "direction"
  },
  "left_leg": {
    "description": "detailed description",
    "knee_angle": "approximate angle (e.g. '90 degrees' for sitting, '175 degrees' for standing)",
    "knee_direction": "direction knee points",
    "knee_height": "floor level / seat level / chest height",
    "foot_direction": "forward / left / right",
    "foot_position": "on floor / crossed / frame edge"
  },
  "right_leg": {
    "description": "same structure as left_leg",
    "knee_angle": "",
    "knee_direction": "",
    "knee_height": "",
    "foot_direction": "",
    "foot_position": ""
  },
  "hip": {
    "description": "hip position and weight distribution",
    "torso_lean": "degrees and direction (e.g. 'leaning back about 10 degrees')"
  },
  "shoulder_line": "describe shoulder asymmetry or tilt",
  "face_direction": "facing camera / 3/4 left / 3/4 right / profile / looking over shoulder",
  "neck_tilt": "direction and approximate degrees (e.g. 'tilted left about 5 degrees')",
  "head_angle": "horizontal / slightly down / slightly up",
  "leg_shape": "straight / crossed / one raised / bent 90deg / wide stance",
  "camera": {
    "angle": "front / slightly side / profile / from behind",
    "height": "eye level / slightly low / slightly high / top view",
    "framing": "CU / MCU / MS / MFS / FS / LS"
  }
}

Be PRECISE with angles. If a body part is not visible, write "not visible" instead of guessing.
Respond ONLY with valid JSON."""

EXPRESSION_PROMPT = """You are a fashion photography expression analyst. Analyze this DUVETICA campaign image and extract the model's facial expression in EXTREME detail.

Return valid JSON with these EXACT fields:

{
  "base": "dreamy / serene / candid / confident / cool / neutral",
  "eyes": "detailed description (e.g. 'half-closed, dreamy gaze under strong sunlight, eyelids relaxed', 'direct calm stare with soft focus')",
  "gaze_direction": "camera / left / right / down / up / distant / over shoulder",
  "mouth": "detailed description (e.g. 'closed, lips relaxed with no tension', 'slightly parted about 2mm, natural and effortless')",
  "face_angle": "describe rotation from front (e.g. 'front with slight 5-degree turn to right', '3/4 left')",
  "chin": "natural / slightly raised / slightly lowered / resting on hand",
  "note": "contextual note in Korean describing the overall mood and what makes this expression unique (e.g. '풀사이드 선베딩. 강한 직사광선 아래 반쯤 감은 눈. 포즈가 아닌 캔디드한 순간.')"
}

Be specific. "Neutral" is too vague - describe WHAT makes it neutral (relaxed muscles? deliberate blankness? bored elegance?).
Respond ONLY with valid JSON."""

BACKGROUND_PROMPT = """You are a fashion photography background/setting analyst. Analyze this DUVETICA campaign image and extract the background/setting in EXTREME detail.

Return valid JSON with these EXACT fields:

{
  "type": "specific setting type (e.g. 'studio with beige textured wall', 'outdoor Mediterranean villa terrace', 'modern indoor cafe')",
  "region_vibe": "Korean studio / Mediterranean / European street / garden / resort / indoor cafe / outdoor nature",
  "time_of_day": "daytime (strong direct light) / daytime (soft diffused) / golden hour / overcast / studio lighting",
  "colors": "list dominant background colors (e.g. 'beige, cream, warm grey')",
  "setting_description": "detailed Korean paragraph describing the background (e.g. '베이지 톤의 텍스처드 스튜디오 벽. 바닥은 라이트 그레이 콘크리트. 자연광이 왼쪽에서 들어와 부드러운 그림자를 만듦. 소품 없이 미니멀한 배경.')",
  "mood": "overall mood (e.g. 'quiet luxury', 'casual editorial', 'resort leisure', 'minimalist premium')",
  "provided_elements": ["list what the background provides: wall, floor, chair, table, plants, water, etc."],
  "available_poses": ["what poses this setting allows: stand, sit, lean, walk, etc."],
  "sit_surfaces": "what can be sat on (e.g. 'chair, stone ledge, floor') or 'none'",
  "lighting_detail": "describe light direction, quality, shadows (e.g. 'soft natural light from left window, minimal shadows, even exposure')",
  "notes": ["any special notes about the background in Korean"]
}

Be SPECIFIC about colors, materials, textures. "Studio" alone is too vague.
Respond ONLY with valid JSON."""


def load_target_images() -> list[dict]:
    with open(REPORT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    targets = [
        r
        for r in data["marketing_results"]
        if r.get("target_category") in ("woven_jacket", "setup")
    ]
    return targets


def analyze_detailed(img_path: str, prompt: str) -> dict:
    client = genai.Client(api_key=_get_next_api_key())
    pil_img = Image.open(img_path).convert("RGB")
    if pil_img.width > 1200 or pil_img.height > 1200:
        pil_img.thumbnail((1200, 1200), Image.LANCZOS)

    parts = [types.Part(text=prompt), _pil_to_part(pil_img)]

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=VISION_MODEL,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(
                    temperature=0.1, response_modalities=["TEXT"]
                ),
            )
            text = (
                response.text.strip().replace("```json", "").replace("```", "").strip()
            )
            return json.loads(text)
        except json.JSONDecodeError:
            if attempt < 2:
                time.sleep(2)
                continue
            return {"error": "JSON parse", "raw": text[:300]}
        except Exception as e:
            if attempt < 2:
                time.sleep((attempt + 1) * 3)
                continue
            return {"error": str(e)}


def _resolve_path(target: dict) -> str:
    file_name = target["file"]
    source = target.get("source", "")
    if source == "instagram":
        return str(
            PROJECT_ROOT
            / "db"
            / "strategy-cut-builder"
            / "duvetica"
            / "instagram"
            / file_name
        )
    for gender in ["women", "men"]:
        gdir = (
            PROJECT_ROOT
            / "db"
            / "strategy-cut-builder"
            / "duvetica"
            / "official-site"
            / gender
        )
        if not gdir.exists():
            continue
        for pdir in gdir.iterdir():
            candidate = pdir / file_name
            if candidate.exists():
                return str(candidate)
    return str(
        PROJECT_ROOT
        / "db"
        / "strategy-cut-builder"
        / "duvetica"
        / "official-site"
        / file_name
    )


def process_image(target: dict) -> dict:
    img_path = _resolve_path(target)
    file_name = target["file"]
    category = target["target_category"]

    pose = analyze_detailed(img_path, POSE_PROMPT)
    expr = analyze_detailed(img_path, EXPRESSION_PROMPT)
    bg = analyze_detailed(img_path, BACKGROUND_PROMPT)

    return {
        "file": file_name,
        "path": img_path,
        "category": category,
        "garment_type": target.get("garment_type", ""),
        "color_primary": target.get("color_primary", ""),
        "pose": pose,
        "expression": expr,
        "background": bg,
    }


def main():
    targets = load_target_images()
    print(f"{'=' * 60}")
    print(f"DUVETICA Detailed DNA Extraction")
    print(f"Target images: {len(targets)} (woven_jacket + setup marketing)")
    print(f"3 API calls per image (pose + expression + background)")
    print(f"{'=' * 60}")

    results = []
    total = len(targets)

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(process_image, t): t for t in targets}
        for i, future in enumerate(as_completed(futures), 1):
            r = future.result()
            pose_ok = "error" not in r["pose"]
            expr_ok = "error" not in r["expression"]
            bg_ok = "error" not in r["background"]
            status = f"P:{'OK' if pose_ok else 'ERR'} E:{'OK' if expr_ok else 'ERR'} B:{'OK' if bg_ok else 'ERR'}"
            print(f"  [{i}/{total}] {r['file']} ({r['category']}) - {status}")
            results.append(r)

    wj = [r for r in results if r["category"] == "woven_jacket"]
    su = [r for r in results if r["category"] == "setup"]

    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total": len(results),
        "woven_jacket_count": len(wj),
        "setup_count": len(su),
        "woven_jacket": wj,
        "setup": su,
    }

    out_path = DNA_DIR / "detailed_dna_report.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    errors = sum(
        1
        for r in results
        if "error" in r["pose"]
        or "error" in r["expression"]
        or "error" in r["background"]
    )

    print(f"\n{'=' * 60}")
    print(f"DONE")
    print(f"  Woven Jacket: {len(wj)} | Setup: {len(su)}")
    print(f"  Errors: {errors}")
    print(f"  Report: {out_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
