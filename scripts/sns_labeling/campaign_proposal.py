"""Build an Influencer Campaign Proposal from selected mood references + brand DNA.

This is the "중간 산출물" between mood selection and image generation.
A human (PM, 마케팅 팀) reviews the proposal before authorizing image generation.

Outputs:
  - campaign_proposal.json   (machine-readable)
  - campaign_proposal.md     (human-readable one-pager)
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import random
from collections import Counter
from pathlib import Path
from typing import Optional


# Per-scene accessory probability for items beyond index 3 in
# brand_dna.styling.accessories. Items at index 0-2 always appear; items at
# index 3+ are sampled per scene using a deterministic hash so the same
# (brand, scene) pair always yields the same result.
ACCESSORY_OPTIONAL_PROB = 0.25


def _strip_meta(s: str) -> str:
    """Drop '(...)' meta-tags like '(occasional, ~25%)' from an accessory name."""
    import re
    return re.sub(r"\s*\([^)]*\)\s*", "", s).strip()


def _scene_accessories(brand_dna: dict, scene_id: str) -> list[str]:
    """Build a per-scene accessory list with stable randomization.

    - First 3 items in brand_dna.styling.accessories: always included
    - Items at index 3+: each appears with probability ACCESSORY_OPTIONAL_PROB,
      seeded by md5(brand_id + scene_id) so results are reproducible.
    Parenthetical meta-tags like "(occasional, ~25%)" are stripped before
    the names are emitted into prompts.
    """
    raw = (brand_dna.get("styling") or {}).get("accessories") or []
    cleaned = [_strip_meta(x) for x in raw]
    base = list(cleaned[:3])
    extras = list(cleaned[3:])
    if not extras:
        return base
    brand_id = (brand_dna.get("brand") or "").lower()
    seed_int = int(hashlib.md5(f"{brand_id}:{scene_id}".encode()).hexdigest()[:8], 16)
    rng = random.Random(seed_int)
    chosen_extra = None
    for extra in extras:
        if rng.random() < ACCESSORY_OPTIONAL_PROB:
            chosen_extra = extra
            break
    if chosen_extra is None:
        return base
    # swap last (lowest-priority) slot to keep total at 3
    if len(base) >= 3:
        return base[:-1] + [chosen_extra]
    return base + [chosen_extra]


# ---------- helpers --------------------------------------------------------

def _top_n(counter: Counter, n: int = 3) -> list[tuple[str, int]]:
    return [(k, v) for k, v in counter.most_common(n) if k]


def _summarise_refs(refs: list[dict]) -> dict:
    """Pull the dominant marketing-context patterns out of selected refs."""
    pose = Counter()
    expr = Counter()
    gaze = Counter()
    mood = Counter()
    loc  = Counter()
    season = Counter()
    style = Counter()
    coord = Counter()
    tone  = Counter()
    handles = Counter()
    for r in refs:
        m = r.get("model") or {}
        b = r.get("background") or {}
        s = r.get("styling") or {}
        pose[m.get("pose")] += 1
        expr[m.get("expression")] += 1
        gaze[m.get("gaze direction")] += 1
        mood[b.get("mood")] += 1
        loc[b.get("location")] += 1
        season[b.get("season/weather")] += 1
        style[s.get("fashion style")] += 1
        coord[s.get("coordination method")] += 1
        tone[s.get("overall fashion color tone")] += 1
        if r.get("handle"):
            handles[r["handle"]] += 1
    return {
        "pose":  _top_n(pose),
        "expression": _top_n(expr),
        "gaze_direction": _top_n(gaze),
        "mood": _top_n(mood),
        "location": _top_n(loc),
        "season_weather": _top_n(season),
        "fashion_style": _top_n(style),
        "coordination_method": _top_n(coord),
        "color_tone": _top_n(tone),
        "top_handles": _top_n(handles, n=10),
    }


def _influencer_persona(brand_dna: dict, summary: dict) -> dict:
    """Distil a 1-paragraph persona from brand DNA + ref summary."""
    md = brand_dna.get("marketing_dna") or {}
    bdmodel = brand_dna.get("model") or {}
    age = bdmodel.get("age_range") or "20s-30s"
    beauty = bdmodel.get("beauty") if isinstance(bdmodel.get("beauty"), str) \
        else (bdmodel.get("beauty", {}) or {}).get("women") or "natural, minimal makeup"
    demo = bdmodel.get("demographics") or "Asian"

    top_pose = summary["pose"][0][0] if summary["pose"] else "stand"
    top_expr = summary["expression"][0][0] if summary["expression"] else "expressionless"
    top_mood = summary["mood"][0][0] if summary["mood"] else "chic"
    top_style = summary["fashion_style"][0][0] if summary["fashion_style"] else "casual"

    pose_rules = (md.get("pose") or {}).get("brand_rules") or {}
    expr_rules = (md.get("expression") or {}).get("brand_rules") or {}

    return {
        "age_range": age,
        "demographics": demo,
        "beauty": beauty,
        "signature_mood": top_mood,
        "signature_style": top_style,
        "pose_signature": top_pose,
        "expression_signature": top_expr,
        "pose_avoid": pose_rules.get("avoid") or pose_rules.get("금지", []),
        "pose_prefer": pose_rules.get("prefer") or pose_rules.get("지향", []),
        "expression_avoid": expr_rules.get("avoid") or expr_rules.get("금지", []),
        "expression_prefer": expr_rules.get("prefer") or expr_rules.get("지향", []),
    }


def _color_direction(brand_dna: dict) -> dict:
    color = brand_dna.get("color") or {}
    out = {}
    for tier in ("base", "key", "accent"):
        block = color.get(tier) or {}
        names = []
        if isinstance(block, dict):
            for c in (block.get("colors") or []):
                if isinstance(c, dict) and c.get("name"):
                    names.append(c["name"])
        out[tier] = {"ratio": (block.get("ratio") if isinstance(block, dict) else None),
                      "colors": names[:6]}
    return out


CATEGORY_ALIASES = {
    "WJ": ["woven_jacket"],
    "DOWN": ["down"],
    "PADDING": ["down"],
    "PADDED": ["down"],
    "PUFFER": ["down"],
    "SETUP": ["setup"],
    "PANTS": ["pants", "bottom_women", "bottom_men", "woven_pants", "knit_pants"],
    "TEE": ["tee", "tshirt"],
    "WB": ["windbreaker"],
    "DJ": ["denim", "jacket"],
    "SH": ["shoes"],
    "TS": ["tee", "tshirt"],
    "WP": ["pants", "woven_pants"],
    "BAG": ["bag", "accessories"],
    "JACKET": ["jacket", "windbreaker"],
    "SET": ["set", "setup"],
}


def _scene_garment_brief(brand_dna: dict, season_category: str) -> dict:
    """Extract the garment description for the target category from brand DNA."""
    sc = (season_category or "").upper()
    cats = brand_dna.get("categories") or {}
    target_key = None

    # 1) explicit alias dictionary
    sc_tokens = [t for t in sc.replace("/", " ").split() if t]
    for tok in sc_tokens:
        for alias in CATEGORY_ALIASES.get(tok, []):
            if alias in cats:
                target_key = alias
                break
        if target_key:
            break

    # 2) substring match
    if not target_key:
        for ckey in cats.keys():
            token = ckey.upper().replace("_", "")
            if any(t in sc.replace(" ", "") for t in (token, ckey.upper())):
                target_key = ckey
                break

    # 3) data_driven_guardrails fallback (mlb / discovery may put info here)
    if not target_key:
        ddg = brand_dna.get("data_driven_guardrails") or {}
        for tok in sc_tokens + [t.lower() for t in sc_tokens]:
            for key in CATEGORY_ALIASES.get(tok.upper(), []) + [tok.lower()]:
                if key in ddg and isinstance(ddg[key], dict):
                    info = ddg[key]
                    return {
                        "category_key": key,
                        "items": info.get("garment_types") or [],
                        "competitors": [],
                        "key_points": ", ".join(info.get("key_features") or []),
                    }

    # 4) marketing_strategy_*.target_image_direction.must_have fallback
    for k in (brand_dna or {}).keys():
        if k.startswith("marketing_strategy_"):
            tid = (brand_dna[k] or {}).get("target_image_direction") or {}
            if tid.get("must_have"):
                return {
                    "category_key": (cats and list(cats.keys())[0]) or "tee",
                    "items": tid.get("must_have") or [],
                    "competitors": [],
                    "key_points": tid.get("positioning") or "",
                }

    if not target_key:
        return {"category_key": None, "items": [], "competitors": [], "key_points": ""}
    cat = cats[target_key] or {}
    return {
        "category_key": target_key,
        "items": cat.get("items") or cat.get("key_items") or [],
        "competitors": cat.get("competitors") or [],
        "key_points": cat.get("key_points") or "",
    }


def _build_scene_brief(
    ref: dict,
    brand_dna: dict,
    garment: dict,
    season_category: str,
    persona: dict,
    scene_idx: int,
    category_key: str,
) -> dict:
    setting = brand_dna.get("setting") or {}
    photog = brand_dna.get("photography") or {}
    locations = setting.get("location") or []
    location_pick = locations[scene_idx % len(locations)] if locations else (
        ref.get("background") or {}).get("location") or "studio"
    lighting = setting.get("lighting") if isinstance(setting.get("lighting"), str) \
        else (setting.get("lighting") or {}).get("outdoor", "natural soft daylight")

    return {
        "scene_id": f"{category_key.upper()}_{scene_idx+1:02d}",
        "moment": None,  # filled by Step B.5 (moment_extractor)
        "reference": {
            "post_id": ref.get("post_id"),
            "handle": ref.get("handle"),
            "image": ref.get("image"),
            "score": ref.get("score"),
            "matched_axes": ref.get("matched_axes"),
            "post_url": ref.get("post_url"),
        },
        "model_direction": {
            "age_range": persona["age_range"],
            "demographics": persona["demographics"],
            "beauty": persona["beauty"],
            "expression": (ref.get("model") or {}).get("expression") or persona["expression_signature"],
            "pose": (ref.get("model") or {}).get("pose") or persona["pose_signature"],
            "gaze": (ref.get("model") or {}).get("gaze direction") or "camera",
        },
        "garment_brief": {
            "category_key": category_key,
            "items": garment["items"],
            "key_points": garment["key_points"],
            "competitors_for_reference": garment["competitors"],
        },
        "setting_direction": {
            "location": location_pick,
            "lighting": lighting,
            "architecture": setting.get("architecture", ""),
            "mood": (ref.get("background") or {}).get("mood"),
        },
        "styling_direction": {
            "fashion_style": (ref.get("styling") or {}).get("fashion style"),
            "coordination": (ref.get("styling") or {}).get("coordination method"),
            "color_tone": (ref.get("styling") or {}).get("overall fashion color tone"),
            "details": (brand_dna.get("styling") or {}).get("details", []),
            "accessories": _scene_accessories(
                brand_dna, f"{category_key.upper()}_{scene_idx+1:02d}"
            ),
            "footwear": (brand_dna.get("styling") or {}).get("footwear", []),
        },
        "photography_brief": {
            "framing": (photog.get("framing") if isinstance(photog.get("framing"), list)
                        else list((photog.get("framing") or {}).values())[:1]),
            "style": photog.get("style", "editorial lifestyle"),
            "tone": photog.get("tone") if isinstance(photog.get("tone"), str)
                    else (photog.get("tone") or {}).get("outdoor", "warm soft contrast"),
            "camera": "Hasselblad 500CM",
            "lens": "85mm f/1.8",
            "film": "Kodak Portra 400",
            "aspect_ratio": "3:4 portrait",
            "anti_ai": [
                "wind-displaced hair strands",
                "natural skin texture and pores visible",
                "fabric caught mid-movement",
                "slight imperfect symmetry",
            ],
        },
    }


# ---------- main builder --------------------------------------------------

def build_campaign_proposal(
    brand_dna: dict,
    season_category: str,
    refs: list[dict],
    *,
    n_scenes: Optional[int] = None,
    extra_notes: Optional[str] = None,
) -> dict:
    """Compose proposal JSON from brand DNA + selected references."""
    n_scenes = n_scenes or len(refs)
    summary = _summarise_refs(refs)
    persona = _influencer_persona(brand_dna, summary)
    color_dir = _color_direction(brand_dna)
    garment = _scene_garment_brief(brand_dna, season_category)
    cat_key = (garment["category_key"] or season_category.split()[-1] or "scene").lower()

    scenes = [
        _build_scene_brief(refs[i], brand_dna, garment, season_category, persona, i, cat_key)
        for i in range(min(n_scenes, len(refs)))
    ]

    return {
        "schema_version": "1.0",
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "campaign": {
            "brand": brand_dna.get("brand"),
            "season": brand_dna.get("season"),
            "season_category_input": season_category,
            "category_resolved": garment["category_key"],
            "positioning": brand_dna.get("positioning"),
            "core_message": ((brand_dna.get("marketing_strategy_26ss") or {}).get("core_message")
                              or (brand_dna.get("marketing_strategy_26fw") or {}).get("core_message")
                              or brand_dna.get("insight")),
            "moods": brand_dna.get("mood") or [],
        },
        "influencer_persona": persona,
        "ref_pool_summary": {
            "n_refs": len(refs),
            "top_handles": summary["top_handles"],
            "dominant_pose": summary["pose"],
            "dominant_expression": summary["expression"],
            "dominant_mood": summary["mood"],
            "dominant_location": summary["location"],
            "dominant_style": summary["fashion_style"],
            "dominant_color_tone": summary["color_tone"],
        },
        "color_direction": color_dir,
        "garment_direction": garment,
        "scene_plan": scenes,
        "extra_notes": extra_notes,
    }


# ---------- markdown rendering -------------------------------------------

def proposal_to_markdown(p: dict) -> str:
    c = p["campaign"]
    persona = p["influencer_persona"]
    summary = p["ref_pool_summary"]
    color = p["color_direction"]
    garment = p["garment_direction"]

    def _kv_lines(items: list[tuple[str, int]]) -> str:
        return ", ".join(f"{k}({v})" for k, v in items if k)

    out = []
    out.append(f"# {c['brand']} {c['season']} {c['season_category_input']} — 인플루언서 캠페인 제안")
    out.append("")
    out.append(f"_생성: {p['generated_at']}_")
    if c.get("core_message"):
        out.append("")
        out.append(f"**Core Message** — {c['core_message']}")
    if c.get("positioning"):
        out.append(f"**Positioning** — {c['positioning']}")
    if c.get("moods"):
        out.append(f"**Brand Moods** — {', '.join(c['moods'])}")
    out.append("")
    out.append("## 1. 타겟 인플루언서 페르소나")
    out.append("")
    out.append(f"- 연령: **{persona['age_range']}** / 인종: **{persona['demographics']}**")
    out.append(f"- 뷰티 디렉션: {persona['beauty']}")
    out.append(f"- 시그니처 무드: **{persona['signature_mood']}**, 스타일: **{persona['signature_style']}**")
    out.append(f"- 시그니처 포즈: **{persona['pose_signature']}**, 표정: **{persona['expression_signature']}**")
    if persona.get("pose_prefer"):
        out.append(f"- 포즈 지향: {', '.join(persona['pose_prefer'])}")
    if persona.get("pose_avoid"):
        out.append(f"- 포즈 금지: {', '.join(persona['pose_avoid'])}")
    if persona.get("expression_prefer"):
        out.append(f"- 표정 지향: {', '.join(persona['expression_prefer'])}")
    out.append("")
    out.append("## 2. 추구미 레퍼런스 풀 분석")
    out.append("")
    out.append(f"- 셀렉된 레퍼런스: **{summary['n_refs']}장**")
    out.append(f"- 상위 인플루언서: {_kv_lines(summary['top_handles'])}")
    out.append(f"- 포즈 빈도: {_kv_lines(summary['dominant_pose'])}")
    out.append(f"- 표정 빈도: {_kv_lines(summary['dominant_expression'])}")
    out.append(f"- 무드 빈도: {_kv_lines(summary['dominant_mood'])}")
    out.append(f"- 장소 빈도: {_kv_lines(summary['dominant_location'])}")
    out.append(f"- 스타일 빈도: {_kv_lines(summary['dominant_style'])}")
    out.append(f"- 컬러톤 빈도: {_kv_lines(summary['dominant_color_tone'])}")
    out.append("")
    out.append("## 3. 컬러 디렉션")
    for tier in ("base", "key", "accent"):
        b = color.get(tier) or {}
        if b.get("colors"):
            out.append(f"- **{tier.upper()}** ({b.get('ratio') or '-'}): {', '.join(b['colors'])}")
    out.append("")
    out.append("## 4. 카테고리 / 의류 디렉션")
    out.append("")
    if garment["category_key"]:
        out.append(f"- 매칭 카테고리: `{garment['category_key']}`")
    if garment["items"]:
        out.append(f"- 핵심 아이템: {', '.join(garment['items'])}")
    if garment["competitors"]:
        out.append(f"- 경쟁사 레퍼런스: {', '.join(garment['competitors'])}")
    if garment["key_points"]:
        out.append(f"- 핵심 포인트: {garment['key_points']}")
    out.append("")
    out.append("## 5. 씬 플랜")
    out.append("")
    for s in p["scene_plan"]:
        ref = s["reference"]
        m = s["model_direction"]
        st = s["styling_direction"]
        sd = s["setting_direction"]
        out.append(f"### {s['scene_id']}  —  ref: @{ref['handle']} ({ref['post_id']}, score {ref['score']})")
        if s.get("moment"):
            out.append(f"- **💭 The Moment**: _{s['moment']}_")
        out.append(f"- **모델**: {m['age_range']}, {m['demographics']}, "
                    f"표정 _{m['expression']}_, 포즈 _{m['pose']}_, 시선 _{m['gaze']}_")
        out.append(f"- **세팅**: 장소 _{sd['location']}_ / 무드 _{sd['mood']}_ / 라이팅 _{sd['lighting']}_")
        out.append(f"- **스타일링**: {st['fashion_style']} / 코디 {st['coordination']} / 톤 {st['color_tone']}")
        if st.get("accessories"):
            out.append(f"  - 액세서리: {', '.join(st['accessories'][:4])}")
        if st.get("footwear"):
            out.append(f"  - 신발: {', '.join(st['footwear'][:3])}")
        out.append(f"- **참조 URL**: {ref.get('post_url') or '-'}")
        out.append("")
    out.append("## 6. 이미지 생성 브리프 (3모델 병렬)")
    out.append("")
    out.append("- 카메라: Hasselblad 500CM, 85mm f/1.8")
    out.append("- 필름: Kodak Portra 400 (visible film grain, organic tonal)")
    out.append("- 비율: 3:4 portrait")
    out.append("- Anti-AI: 자연스러운 머리카락 흐트러짐, 피부 텍스처/모공, 옷 자락 움직임 중간 포착")
    out.append("- 후보정: rich tonal depth, creamy highlights, neutral white balance")
    if p.get("extra_notes"):
        out.append("")
        out.append(f"## 추가 노트\n\n{p['extra_notes']}")
    return "\n".join(out)


__all__ = ["build_campaign_proposal", "proposal_to_markdown"]
