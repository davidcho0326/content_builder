"""IMC Plan loader — marketing_builder/output/{campaign}/05_marketing/output/imc_plan.json
into normalized CampaignSpec dataclass for the strategy-cut pipeline.

Usage:
    from sns_labeling.imc_plan_loader import load_campaign_spec
    spec = load_campaign_spec("path/to/imc_plan.json")
    for scene in spec.scenes:
        ...

Design (v3 Option α):
- Selector consumes only persona/pose-related signals (CampaignSpec.personas,
  Scene.persona_match resolved from SCENE_PERSONA_HINTS).
- Image generation prompt consumes scene.tone/mood/visual/location plus the
  campaign headline/keywords/hero garment — these strategic cues are LLM-synthesized
  rather than ref-anchored.
- Celebrity data (`celeb_matrix`, `media_split`, `promotions`, `outcome_funnel`,
  `global_sub_module`, etc.) is intentionally NOT loaded into CampaignSpec; the
  visualization module is not responsible for celeb casting.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Influencer-category → persona routing.
# imc_plan.influencer_tiers[*].categories holds 14-ish descriptive labels
# (e.g. "Jamsil Stadium Regulars", "Pilates Enthusiasts"). Each label is routed
# to the persona id whose scene most closely matches its lifestyle, so each
# scene gets a "TARGET INFLUENCER PROFILE" hint injected into its prompt.
# Order: first matched substring (lowercase) wins.
INFLUENCER_CATEGORY_TO_PERSONA: list[tuple[str, str]] = [
    # G1 — Stadium Cheer Squad (20-24, K-pop fandom + baseball fans)
    ("k-pop challenge", "G1"),
    ("k-pop fandom", "G1"),
    ("k-pop", "G1"),
    ("hardcore baseball", "G1"),
    ("baseball fanatic", "G1"),
    ("pro-baseball", "G1"),
    ("stadium regular", "G1"),
    ("stadium", "G1"),
    ("festival single", "G1"),
    # G2 — Dugout-to-Daylight Crew (25-29, Songridan + wellness commute)
    ("songridan", "G2"),
    ("hotspot creator", "G2"),
    ("pilates", "G2"),
    ("health/fitness", "G2"),
    ("look-book", "G2"),
    ("look book", "G2"),
    ("feminine sportive", "G2"),
    ("stylish working mom", "G2"),
    # G3 — Heritage Lounge Mom (30-35, premium / heritage)
    ("premium working mom", "G3"),
    ("working mom", "G3"),
    ("heritage expert", "G3"),
    ("heritage", "G3"),
    ("festival crew", "G3"),
]


# Persona-scene mapping heuristic — keyword in scene.title/mood/location → persona id.
# Marketing builder does not encode scene→persona linkage explicitly, so we infer.
# Order: first matched key wins. Keys are lowercase substrings.
SCENE_PERSONA_HINTS: list[tuple[str, str]] = [
    ("cheer", "G1"),
    ("stadium", "G1"),
    ("응원", "G1"),
    ("야구장", "G1"),
    ("game", "G1"),
    ("daylight", "G2"),
    ("wave", "G2"),
    ("commute", "G2"),
    ("running", "G2"),
    ("café", "G2"),
    ("cafe", "G2"),
    ("송리", "G2"),
    ("park", "G2"),
    ("backstage", "G3"),
    ("dugout", "G3"),
    ("lounge", "G3"),
    ("heritage", "G3"),
    ("팝업", "G3"),
    ("워터밤", "G3"),
    ("페스티벌", "G3"),
    ("festival", "G3"),
    ("resort", "G3"),
]


@dataclass
class Persona:
    id: str                      # "G1" | "G2" | "G3"
    name: str                    # "Stadium Cheer Squad"
    cluster_size: str            # "5명 클러스터"
    demo: str                    # "20-24세 / 여성 / 대학생·신입사회"
    age_min: Optional[int]       # 20 (parsed from demo)
    age_max: Optional[int]       # 24
    gender: Optional[str]        # "female" (parsed)
    situations: list[str] = field(default_factory=list)
    jtbd: list[str] = field(default_factory=list)


@dataclass
class Scene:
    num: int                     # 1, 2, 3
    title: str                   # "Cheer Line"
    tone: str                    # "D.GREEN base + L.MINT 액센트"
    mood: str                    # "응원봉 라이트, 팀 스피릿, 다이나믹"
    visual: str                  # "잠실 응원석 야간 — 라이트 스틱 곡선 + 크롭 저지 + 와이드 팬츠"
    location: str                # "잠실 야구장 응원석 (홈개막전 시구 전후)"
    persona_match: Optional[str] # "G1" — inferred via SCENE_PERSONA_HINTS
    influencer_categories_match: list[str] = field(default_factory=list)
    # Categories routed to this scene via INFLUENCER_CATEGORY_TO_PERSONA
    # (e.g. ["Pro-Baseball Fanatics", "K-POP Fandom Fan-cam Editors"]).

    @property
    def slug(self) -> str:
        s = re.sub(r"[^a-z0-9]+", "_", self.title.lower()).strip("_")
        return f"S{self.num:02d}_{s or 'scene'}"

    def text_brief(self) -> str:
        """Compact natural-language brief for prompt embedding / LLM context."""
        return (
            f"Scene {self.num}: {self.title}. "
            f"Tone & Color: {self.tone}. "
            f"Mood: {self.mood}. "
            f"Location: {self.location}. "
            f"Visual: {self.visual}."
        )


@dataclass
class CampaignSpec:
    brand: str                          # "MLB"
    season: str                         # "27SS"
    lifestyle: str                      # "Feminine_Sportive"
    lifestyle_display: str              # "Feminine Sportive"
    headline_en: str
    headline_ko: str
    season_message: str
    keywords: list[dict]                # [{kw, score, rationale}]
    hero_garment: dict                  # {code, desc}
    sub_garments: list[dict]            # [{code, desc}, ...]
    personas: list[Persona]
    influencer_categories: list[str]    # flattened from influencer_tiers
    scenes: list[Scene]
    dna_grid: dict                      # {means, experience, core, goal}
    core_hook: dict                     # {formula, definition, ...} — optional
    campaign_id: str                    # derived from imc_plan path or _meta
    source_path: str

    def persona_by_id(self, pid: Optional[str]) -> Optional[Persona]:
        if not pid:
            return None
        for p in self.personas:
            if p.id == pid:
                return p
        return None


# ---------- parsing helpers --------------------------------------------------

_AGE_RANGE_RX = re.compile(r"(\d{2})\s*[-~]\s*(\d{2})\s*세")
_AGE_SINGLE_RX = re.compile(r"(\d{2})\s*세")


def _parse_age(demo: str) -> tuple[Optional[int], Optional[int]]:
    if not demo:
        return None, None
    m = _AGE_RANGE_RX.search(demo)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = _AGE_SINGLE_RX.search(demo)
    if m:
        v = int(m.group(1))
        return v, v
    return None, None


def _parse_gender(demo: str) -> Optional[str]:
    if not demo:
        return None
    if "여성" in demo or "여자" in demo or "female" in demo.lower():
        return "female"
    if "남성" in demo or "남자" in demo or "male" in demo.lower():
        return "male"
    return None


def _infer_persona_match(scene: dict) -> Optional[str]:
    """Match scene → persona id via SCENE_PERSONA_HINTS.

    Priority: title only (most specific) > location > mood > visual.
    Earlier passes win — prevents incidental keyword matches in 'visual'
    (e.g. '응원봉' appearing in Scene 3's visual) from overriding the
    intent encoded in the title (e.g. 'Dugout Backstage' → G3).
    """
    title = str(scene.get("title") or "").lower()
    location = str(scene.get("location") or "").lower()
    mood = str(scene.get("mood") or "").lower()
    visual = str(scene.get("visual") or "").lower()
    for haystack in (title, location, mood, visual):
        if not haystack:
            continue
        for kw, pid in SCENE_PERSONA_HINTS:
            if kw.lower() in haystack:
                return pid
    return None


def _route_category_to_persona(category: str) -> Optional[str]:
    """First-match substring lookup against INFLUENCER_CATEGORY_TO_PERSONA."""
    if not category:
        return None
    cat_lower = category.lower()
    for kw, pid in INFLUENCER_CATEGORY_TO_PERSONA:
        if kw in cat_lower:
            return pid
    return None


def _route_categories_to_scenes(scenes: list[Scene],
                                  categories: list[str]) -> None:
    """Mutate each scene.influencer_categories_match in place.

    Categories routed by INFLUENCER_CATEGORY_TO_PERSONA → scene.persona_match.
    Unmatched categories are appended to every scene as generic context (so a
    new label introduced by marketing-builder is not silently lost).
    """
    if not scenes:
        return
    persona_to_cats: dict[str, list[str]] = {}
    unmatched: list[str] = []
    for cat in categories:
        pid = _route_category_to_persona(cat)
        if pid:
            persona_to_cats.setdefault(pid, []).append(cat)
        else:
            unmatched.append(cat)
    for scene in scenes:
        scene.influencer_categories_match = list(
            persona_to_cats.get(scene.persona_match or "", [])
        )
        if unmatched:
            scene.influencer_categories_match.extend(unmatched)


def _flatten_influencer_categories(tiers: list[dict]) -> list[str]:
    """Extract all influencer sub-categories from influencer_tiers[*].categories.

    "Festival Single Event (1), K-POP Challenge Leader (1)"  ->
        ["Festival Single Event", "K-POP Challenge Leader"]
    """
    out: list[str] = []
    for t in tiers or []:
        cats = t.get("categories")
        if not cats:
            continue
        if isinstance(cats, list):
            tokens = cats
        else:
            tokens = re.split(r"\s*,\s*", str(cats))
        for tok in tokens:
            # strip trailing "(N)" count annotations
            cleaned = re.sub(r"\s*\(\s*\d+\s*\)\s*$", "", tok).strip()
            if cleaned and cleaned not in out:
                out.append(cleaned)
    return out


def _derive_campaign_id(path: Path, plan: dict) -> str:
    """Prefer the marketing_builder folder name (e.g. 20260503_MLB_27SS).
    Falls back to brand+season."""
    # path like .../20260503_MLB_27SS/05_marketing/output/imc_plan.json
    for parent in path.parents:
        name = parent.name
        if re.match(r"^\d{8}_[A-Za-z]+_\w+", name):
            return name
    brand = (plan.get("brand") or "BRAND").upper()
    season = (plan.get("season") or "SS").upper()
    return f"{brand}_{season}"


# ---------- main loader ------------------------------------------------------

def load_campaign_spec(imc_plan_path: str | Path) -> CampaignSpec:
    p = Path(imc_plan_path)
    plan = json.loads(p.read_text(encoding="utf-8"))

    ctx = plan.get("campaign_context") or {}
    headline = plan.get("headline") or {}

    cats = ctx.get("categories") or {}
    hero = cats.get("hero") or {}
    sub = cats.get("sub") or []

    personas: list[Persona] = []
    for pg in plan.get("persona_groups") or []:
        demo = pg.get("demo") or ""
        amin, amax = _parse_age(demo)
        personas.append(Persona(
            id=pg.get("id") or f"P{len(personas)+1}",
            name=pg.get("name") or "",
            cluster_size=pg.get("cluster_size") or "",
            demo=demo,
            age_min=amin,
            age_max=amax,
            gender=_parse_gender(demo),
            situations=list(pg.get("situations") or []),
            jtbd=list(pg.get("jtbd") or []),
        ))

    scenes: list[Scene] = []
    for s in plan.get("scenes") or []:
        scenes.append(Scene(
            num=int(s.get("num") or len(scenes) + 1),
            title=s.get("title") or f"Scene {len(scenes)+1}",
            tone=s.get("tone") or "",
            mood=s.get("mood") or "",
            visual=s.get("visual") or "",
            location=s.get("location") or "",
            persona_match=_infer_persona_match(s),
        ))

    influencer_cats = _flatten_influencer_categories(plan.get("influencer_tiers") or [])
    _route_categories_to_scenes(scenes, influencer_cats)

    return CampaignSpec(
        brand=plan.get("brand") or "BRAND",
        season=plan.get("season") or "",
        lifestyle=plan.get("lifestyle") or ctx.get("lifestyle") or "",
        lifestyle_display=ctx.get("lifestyle_display")
                          or (plan.get("lifestyle") or "").replace("_", " "),
        headline_en=headline.get("en_main") or "",
        headline_ko=headline.get("ko_sub") or "",
        season_message=headline.get("season_message") or "",
        keywords=list(plan.get("keywords_3") or []),
        hero_garment={
            "code": hero.get("code") or "",
            "desc": hero.get("desc") or "",
        },
        sub_garments=[{"code": x.get("code") or "", "desc": x.get("desc") or ""}
                      for x in sub],
        personas=personas,
        influencer_categories=influencer_cats,
        scenes=scenes,
        dna_grid=plan.get("dna_grid") or {},
        core_hook=plan.get("core_hook") or {},
        campaign_id=_derive_campaign_id(p, plan),
        source_path=str(p),
    )


__all__ = [
    "Persona", "Scene", "CampaignSpec",
    "load_campaign_spec",
    "SCENE_PERSONA_HINTS",
]


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) < 2:
        print("usage: python imc_plan_loader.py <imc_plan.json>", file=sys.stderr)
        sys.exit(1)
    spec = load_campaign_spec(sys.argv[1])
    print(f"campaign: {spec.campaign_id}")
    print(f"  brand/season/lifestyle: {spec.brand} {spec.season} {spec.lifestyle}")
    print(f"  headline: {spec.headline_en} / {spec.headline_ko}")
    print(f"  hero: [{spec.hero_garment['code']}] {spec.hero_garment['desc']}")
    print(f"  sub: {[(s['code'], s['desc'][:30]) for s in spec.sub_garments]}")
    print(f"  scenes ({len(spec.scenes)}):")
    for s in spec.scenes:
        print(f"    [{s.num}] {s.title} → persona={s.persona_match} "
              f"loc={s.location[:40]}")
        if s.influencer_categories_match:
            print(f"        influencer cats ({len(s.influencer_categories_match)}): "
                  f"{', '.join(s.influencer_categories_match[:5])}"
                  f"{' …' if len(s.influencer_categories_match) > 5 else ''}")
    print(f"  personas ({len(spec.personas)}):")
    for ps in spec.personas:
        print(f"    {ps.id}: {ps.name} | age={ps.age_min}-{ps.age_max} "
              f"gender={ps.gender}")
    print(f"  influencer_categories ({len(spec.influencer_categories)}): "
          f"{spec.influencer_categories[:5]}")
