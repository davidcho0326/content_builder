"""Deterministic routing: imc_plan campaign keys → products_resource folder.

Maps a CampaignSpec (brand, season, lifestyle, hero_garment.code) to the
specific product image file under
`products_resource/{brand_folder}/{season} {code_folder}/{lifestyle_folder}/`.

Used by Step C+ (virtual try-on) to fetch the real-world product image that
should replace the AI-described garment in each generated editorial cut.

No LLM calls — pure filesystem lookup with alias / substring matching.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PRODUCTS_DIR = PROJECT_ROOT / "products_resource"


# brand display name → on-disk folder name
BRAND_FOLDER = {
    "mlb": "MLB",
    "duvetica": "DV",
    "discovery": "DX",
}

# imc category code → on-disk code-folder suffix.
# imc_plan uses `WP` (와이드 우븐팬츠) but products_resource folder is `PT`.
CODE_ALIASES = {
    "WP": "PT",
    "PT": "PT",
    "TS": "TS",
    "SH": "SH",
    "WJ": "WJ",
    "DJ": "DJ",
    "SET": "SET",
}


@dataclass
class ProductMatch:
    brand: str                      # display: "MLB" / "DUVETICA" / "DISCOVERY"
    brand_folder: str               # on-disk: "MLB" / "DV" / "DX"
    season: str                     # "27SS" / "26FW"
    code: str                       # imc code: "TS" / "WP" / ...
    code_folder: str                # on-disk: "TS" / "PT" / ...
    lifestyle_imc: str              # imc lifestyle slug: "Feminine_Sportive"
    lifestyle_folder: str           # on-disk: "Feminine Sportive"
    folder: Path                    # absolute path to lifestyle folder
    hero_image: Path                # main product image to use for try-on
    hero_strategy: str              # "representative" / "v1_first" / "first_png"
    color_variants: list[Path] = field(default_factory=list)
    trend_examples: list[Path] = field(default_factory=list)
    match_strategy: str = ""        # how lifestyle was matched

    def to_dict(self) -> dict:
        out = asdict(self)
        out["folder"] = str(self.folder).replace("\\", "/")
        out["hero_image"] = str(self.hero_image).replace("\\", "/")
        out["color_variants"] = [str(p).replace("\\", "/") for p in self.color_variants]
        out["trend_examples"] = [str(p).replace("\\", "/") for p in self.trend_examples]
        return out


# ---------- helpers ----------------------------------------------------------

def _slug(s: str) -> str:
    """Normalize for substring matching: lowercase, strip non-alnum."""
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _list_subdirs(p: Path) -> list[Path]:
    if not p.exists():
        return []
    return sorted(d for d in p.iterdir() if d.is_dir())


def _pick_hero_image(folder: Path) -> tuple[Optional[Path], str, list[Path], list[Path]]:
    """Pick the canonical product packshot from a lifestyle folder.

    Priority:
      1. `representative_*.png` (explicit hero flag)
      2. `V1_src01_*.png` (first product variant, source 01)
      3. `V1_src02_*.png` (source 02)
      4. any other `V*.png`
      5. first `*.png` (last resort)

    Returns (hero_image, strategy, color_variants, trend_examples).
    """
    if not folder.exists() or not folder.is_dir():
        return None, "missing", [], []

    pngs = sorted(folder.glob("*.png"))
    jpgs = sorted(folder.glob("*.jpg"))

    rep = [p for p in pngs if p.name.lower().startswith("representative_")]
    v1_src01 = [p for p in pngs if re.match(r"^V1_src01_", p.name)]
    v1_src02 = [p for p in pngs if re.match(r"^V1_src02_", p.name)]
    v_all = [p for p in pngs if re.match(r"^V\d", p.name)]

    if rep:
        hero = rep[0]
        strategy = "representative"
    elif v1_src01:
        hero = v1_src01[0]
        strategy = "v1_src01"
    elif v1_src02:
        hero = v1_src02[0]
        strategy = "v1_src02"
    elif v_all:
        hero = v_all[0]
        strategy = "v_first"
    elif pngs:
        hero = pngs[0]
        strategy = "first_png"
    else:
        return None, "no_png", [], jpgs

    # color variants = all V*.png in same folder excluding the chosen hero
    variants = [p for p in v_all if p != hero]
    trends = [p for p in jpgs if p.name.startswith("trend_")]
    return hero, strategy, variants, trends


def _match_lifestyle_folder(season_code_dir: Path,
                             lifestyle_imc: str) -> tuple[Optional[Path], str]:
    """Match imc_plan.lifestyle to one of the lifestyle subfolders.

    Strategy:
      1. exact (slugified) match
      2. one folder slug ⊂ imc slug or vice-versa (substring)
      3. word overlap score (highest wins)
      4. first folder fallback
    """
    folders = _list_subdirs(season_code_dir)
    if not folders:
        return None, "no_lifestyles"

    target_slug = _slug(lifestyle_imc)
    if not target_slug:
        return folders[0], "no_target_first_folder"

    # 1. exact
    for f in folders:
        if _slug(f.name) == target_slug:
            return f, "exact"

    # 2. substring (either direction)
    for f in folders:
        fs = _slug(f.name)
        if fs and (fs in target_slug or target_slug in fs):
            return f, "substring"

    # 3. word overlap
    target_words = set(re.findall(r"[a-z0-9]+", lifestyle_imc.lower()))
    best_folder, best_overlap = None, 0
    for f in folders:
        fw = set(re.findall(r"[a-z0-9]+", f.name.lower()))
        overlap = len(target_words & fw)
        if overlap > best_overlap:
            best_folder, best_overlap = f, overlap
    if best_folder:
        return best_folder, f"word_overlap_{best_overlap}"

    # 4. fallback
    return folders[0], "first_folder_fallback"


# ---------- main API ---------------------------------------------------------

def route_hero_product(
    spec,                                # imc_plan_loader.CampaignSpec
    products_dir: Path | str = DEFAULT_PRODUCTS_DIR,
) -> Optional[ProductMatch]:
    """Resolve hero garment from imc_plan to a real product image file.

    Returns None if any of brand/season/code mapping fails or no product files.
    Caller (Step C+) gracefully skips try-on when None.
    """
    products_dir = Path(products_dir)
    if not products_dir.exists():
        return None

    brand_lower = (spec.brand or "").lower().split()[0]
    brand_folder = BRAND_FOLDER.get(brand_lower)
    if not brand_folder:
        return None
    brand_dir = products_dir / brand_folder
    if not brand_dir.exists():
        return None

    season = (spec.season or "").upper()
    code = (spec.hero_garment.get("code") or "").upper().strip()
    code_folder = CODE_ALIASES.get(code, code)
    if not season or not code_folder:
        return None

    season_code_dir = brand_dir / f"{season} {code_folder}"
    if not season_code_dir.exists():
        return None

    # imc lifestyle slug like "Feminine_Sportive" → match to one of the folders
    lifestyle_imc = spec.lifestyle or spec.lifestyle_display or ""
    lifestyle_folder, match_strategy = _match_lifestyle_folder(
        season_code_dir, lifestyle_imc
    )
    if lifestyle_folder is None:
        return None

    hero, hero_strategy, variants, trends = _pick_hero_image(lifestyle_folder)
    if hero is None:
        return None

    return ProductMatch(
        brand=spec.brand,
        brand_folder=brand_folder,
        season=season,
        code=code,
        code_folder=code_folder,
        lifestyle_imc=lifestyle_imc,
        lifestyle_folder=lifestyle_folder.name,
        folder=lifestyle_folder,
        hero_image=hero,
        hero_strategy=hero_strategy,
        color_variants=variants,
        trend_examples=trends,
        match_strategy=match_strategy,
    )


# Codes that virtual_tryon's multi-mode can handle as bottom (pants).
# Excludes SH (shoes — needs different segmentation pipeline).
BOTTOM_CODES = {"WP", "PT"}


def route_bottom_product(
    spec,
    products_dir: Path | str = DEFAULT_PRODUCTS_DIR,
) -> Optional[ProductMatch]:
    """Find a bottom (pants) product among spec.sub_garments for multi-tryon.

    Returns the first matched ProductMatch with code in BOTTOM_CODES, or None.
    """
    for sub in spec.sub_garments or []:
        code = (sub.get("code") or "").upper().strip()
        if code not in BOTTOM_CODES:
            continue

        class _Tmp:
            brand = spec.brand
            season = spec.season
            lifestyle = spec.lifestyle
            lifestyle_display = spec.lifestyle_display
            hero_garment = {"code": code, "desc": sub.get("desc", "")}
        m = route_hero_product(_Tmp, products_dir=products_dir)
        if m:
            return m
    return None


def route_sub_products(
    spec,
    products_dir: Path | str = DEFAULT_PRODUCTS_DIR,
) -> list[ProductMatch]:
    """Same as hero, but for sub_garments[]. Used in v2 multi-tryon."""
    out: list[ProductMatch] = []
    for sub in spec.sub_garments or []:
        sub_code = (sub.get("code") or "").upper().strip()
        if not sub_code:
            continue
        # build a temporary spec-like object for routing reuse
        class _Tmp:
            brand = spec.brand
            season = spec.season
            lifestyle = spec.lifestyle
            lifestyle_display = spec.lifestyle_display
            hero_garment = {"code": sub_code}
        m = route_hero_product(_Tmp, products_dir=products_dir)
        if m:
            out.append(m)
    return out


def write_manifest(match: ProductMatch, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(match.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


__all__ = [
    "ProductMatch",
    "route_hero_product",
    "route_sub_products",
    "route_bottom_product",
    "write_manifest",
    "DEFAULT_PRODUCTS_DIR",
    "BRAND_FOLDER",
    "CODE_ALIASES",
    "BOTTOM_CODES",
]


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) < 2:
        print("usage: python product_router.py <imc_plan.json>", file=sys.stderr)
        sys.exit(1)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sns_labeling.imc_plan_loader import load_campaign_spec

    spec = load_campaign_spec(sys.argv[1])
    print(f"campaign: {spec.campaign_id}")
    print(f"brand: {spec.brand} season: {spec.season} lifestyle: {spec.lifestyle}")
    print(f"hero: {spec.hero_garment}")
    print()

    hero_match = route_hero_product(spec)
    if hero_match:
        print("=== HERO MATCH ===")
        print(f"  folder: {hero_match.folder}")
        print(f"  hero_image: {hero_match.hero_image.name} ({hero_match.hero_strategy})")
        print(f"  match_strategy: {hero_match.match_strategy}")
        print(f"  color variants: {len(hero_match.color_variants)}")
        for v in hero_match.color_variants[:3]:
            print(f"    - {v.name}")
    else:
        print("=== HERO MATCH: NONE ===")

    print()
    print("=== SUB MATCHES ===")
    subs = route_sub_products(spec)
    for m in subs:
        print(f"  [{m.code}→{m.code_folder}] {m.folder.name} :: {m.hero_image.name}")
