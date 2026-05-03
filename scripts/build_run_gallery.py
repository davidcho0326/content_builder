"""Render a single run directory as one self-contained HTML gallery.

Input:  st_cut-dev/results/{brand}/{timestamp}_auto_pipeline/
Output: gallery.html  (in the same directory)

Layout (top → bottom):
    1. Run header — brand, season, model, timestamp, totals
    2. Campaign proposal summary (persona, ref-pool stats, color direction)
    3. Per-scene grid: REF | GEMINI | GPT | HIGGSFIELD (placeholder if missing)
       + collapsible prompt + scene metadata
    4. Reference pool gallery (selected refs with score/handle)

Uses relative file:// paths so images load locally without a server.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path
from typing import Optional

# image filename suffixes per provider.
# Order = display order in galleries. Standard 3 (gpt + hf_gpt + hf_mkt) first,
# legacy providers (gemini / hf_soul / hf_nano) kept for backward compat with
# older runs but rendered after the standard set.
PROVIDER_SUFFIX = {
    "gpt":     "_gpt.png",          # Direct (current standard)
    "hf_gpt":  "_hf_gpt.png",       # HF GPT Image 2 (standard)
    "hf_mkt":  "_hf_mkt.png",       # HF Marketing Studio (standard)
    "gemini":  "_gemini.png",       # legacy Direct
    "hf_soul": "_hf_soul.png",      # legacy HF Soul 2.0
    "hf_nano": "_hf_nano.png",      # legacy HF Nano-Banana Pro
}

PROVIDER_LABEL = {
    "gpt":     "GPT-image-2",
    "hf_gpt":  "HF GPT-image 2",
    "hf_mkt":  "HF Marketing Studio",
    "gemini":  "Gemini-3-pro (legacy)",
    "hf_soul": "HF Soul 2.0 (legacy)",
    "hf_nano": "HF Nano-Banana Pro (legacy)",
}


def _safe_load(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _scenes_from_proposal(proposal: dict) -> list[dict]:
    return list(proposal.get("scene_plan") or [])


def _esc(s) -> str:
    if s is None:
        return ""
    import html as _h
    return _h.escape(str(s))


def _resolve_image(images_dir: Path, scene_id: str, suffix: str) -> Optional[str]:
    p = images_dir / f"{scene_id}{suffix}"
    if p.exists():
        return p.name
    return None


# Brand DNA + product image lookup -----------------------------------------

PROJECT_ROOT_FROM_SCRIPT = Path(__file__).resolve().parents[2]
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def _load_brand_dna(brand: Optional[str]) -> dict:
    if not brand:
        return {}
    p = PROJECT_ROOT_FROM_SCRIPT / "st_cut-dev" / "brand-dna" / f"{brand.lower()}.json"
    return _safe_load(p) or {}


def _scan_product_images(brand: Optional[str], cap: int = 24) -> list[Path]:
    """Find DUVETICA-style official-site product images for the brand."""
    if not brand:
        return []
    candidates = [
        PROJECT_ROOT_FROM_SCRIPT / "st_cut-dev" / "data" / brand.lower() / "official-site",
        PROJECT_ROOT_FROM_SCRIPT / "db" / "strategy-cut-builder" / brand.lower() / "official-site",
    ]
    out: list[Path] = []
    for root in candidates:
        if not root.exists():
            continue
        for dp, _, fs in os.walk(root):
            for f in sorted(fs):
                if Path(f).suffix.lower() in IMG_EXTS and not f.startswith("_"):
                    out.append(Path(dp) / f)
        if out:
            break
    out.sort()
    return out[:cap]


def render(run_dir: Path) -> Path:
    refs_dir = run_dir / "01_references"
    prop_dir = run_dir / "02_proposal"
    images_dir = run_dir / "03_images"

    selection = _safe_load(refs_dir / "selection.json") or {}
    mood_mode = selection.get("mood_mode") or "marketing"
    proposal = _safe_load(prop_dir / "campaign_proposal.json") or {}
    summary = _safe_load(images_dir / "_summary.json") or {}
    proposal_md = ""
    md_path = prop_dir / "campaign_proposal.md"
    if md_path.exists():
        proposal_md = md_path.read_text(encoding="utf-8")

    brand_for_dna = selection.get("brand") or (proposal.get("campaign") or {}).get("brand")
    brand_dna_full = _load_brand_dna(brand_for_dna)
    product_imgs: list[Path] = []  # 자사 제품 섹션 제거됨 (사용자 요청)

    scenes = _scenes_from_proposal(proposal)
    refs_meta = selection.get("selected") or []

    campaign = proposal.get("campaign") or {}
    persona = proposal.get("influencer_persona") or {}
    ref_summary = proposal.get("ref_pool_summary") or {}
    color_dir = proposal.get("color_direction") or {}
    garment = proposal.get("garment_direction") or {}

    # build scene rows
    scene_rows_html = []
    for s in scenes:
        sid = s.get("scene_id") or "?"
        # reference image resolver — proposal stores scene.reference.image (absolute);
        # we prefer the per-scene `_00_reference.jpg` saved alongside results
        ref_local = images_dir / f"{sid}_00_reference.jpg"
        if not ref_local.exists():
            # fall back to whatever absolute path the proposal stored
            ref_abs = (s.get("reference") or {}).get("image")
            if ref_abs and Path(ref_abs).exists():
                # use absolute path with file:// for src
                ref_url = "file:///" + Path(ref_abs).as_posix()
                ref_filename_for_caption = Path(ref_abs).name
            else:
                ref_url = ""
                ref_filename_for_caption = "(missing)"
        else:
            ref_url = f"03_images/{ref_local.name}"
            ref_filename_for_caption = ref_local.name

        gem_name      = _resolve_image(images_dir, sid, PROVIDER_SUFFIX["gemini"])
        gpt_name      = _resolve_image(images_dir, sid, PROVIDER_SUFFIX["gpt"])
        hf_soul_name  = _resolve_image(images_dir, sid, PROVIDER_SUFFIX["hf_soul"])
        hf_nano_name  = _resolve_image(images_dir, sid, PROVIDER_SUFFIX["hf_nano"])
        hf_gpt_name   = _resolve_image(images_dir, sid, PROVIDER_SUFFIX["hf_gpt"])
        hf_mkt_name   = _resolve_image(images_dir, sid, PROVIDER_SUFFIX["hf_mkt"])
        prompt_path = images_dir / f"{sid}_prompt.txt"
        prompt_text = ""
        if prompt_path.exists():
            try:
                prompt_text = prompt_path.read_text(encoding="utf-8")
            except Exception:
                prompt_text = ""

        ref_block = (s.get("reference") or {})
        m = s.get("model_direction") or {}
        sd = s.get("setting_direction") or {}
        st = s.get("styling_direction") or {}

        def _img_cell(name: Optional[str], provider: str, src_override: str = "") -> str:
            if not name and not src_override:
                return (f'<div class="cell missing">'
                          f'<div class="ph">{_esc(PROVIDER_LABEL[provider])}<br/><small>(없음)</small></div>'
                          f'</div>')
            url = src_override or f"03_images/{name}"
            return (f'<div class="cell">'
                      f'<a href="{_esc(url)}" target="_blank" rel="noreferrer">'
                      f'<img src="{_esc(url)}" loading="lazy" alt="{_esc(provider)}" />'
                      f'</a>'
                      f'<div class="cap"><span class="prov prov-{provider}">{_esc(PROVIDER_LABEL[provider])}</span></div>'
                      f'</div>')

        ref_cell = (
            f'<div class="cell">'
            f'<a href="{_esc(ref_url)}" target="_blank" rel="noreferrer">'
            f'<img src="{_esc(ref_url)}" loading="lazy" alt="reference" />'
            f'</a>'
            f'<div class="cap"><span class="prov prov-ref">REF</span> '
            f'<a href="{_esc(ref_block.get("post_url") or "#")}" target="_blank" rel="noreferrer">'
            f'@{_esc(ref_block.get("handle"))}</a> '
            f'<span class="muted">score {_esc(ref_block.get("score"))}</span></div>'
            f'</div>'
        ) if ref_url else ""

        moment_html = (f'<div class="moment-line">💭 <i>{_esc(s.get("moment"))}</i></div>'
                        if s.get("moment") else "")
        meta_html = (
            f'<div class="meta">'
            f'<div><b>{_esc(sid)}</b> &middot; '
            f'<span class="muted">cat: {_esc((s.get("garment_brief") or {}).get("category_key"))}</span></div>'
            f'{moment_html}'
            f'<div class="row">'
            f'<span class="tag m1">{_esc(m.get("age_range"))}</span>'
            f'<span class="tag m1">{_esc(m.get("expression"))}</span>'
            f'<span class="tag m1">{_esc(m.get("pose"))}</span>'
            f'<span class="tag m4">📍 {_esc(sd.get("location"))}</span>'
            f'<span class="tag m5">{_esc(sd.get("mood"))}</span>'
            f'<span class="tag m2">{_esc(st.get("fashion_style"))}</span>'
            f'<span class="tag m3">{_esc(st.get("color_tone"))}</span>'
            f'</div>'
            f'</div>'
        )

        prompt_html = (
            f'<details class="prompt"><summary>프롬프트 보기 ({len(prompt_text):,} chars)</summary>'
            f'<pre>{_esc(prompt_text)}</pre></details>'
        ) if prompt_text else ""

        # 3 + 3 + 1(big) layout. Big cell (HF GPT-image 2) spans both rows on
        # the right; left side is 3 small cells × 2 rows. Emit big cell first
        # with explicit placement; the rest auto-flow into the 3 small columns.
        hf_gpt_cell = _img_cell(hf_gpt_name, "hf_gpt").replace(
            'class="cell"', 'class="cell cell-big"', 1
        ).replace(
            'class="cell missing"', 'class="cell cell-big missing"', 1
        )
        scene_rows_html.append(
            f'<section class="scene">'
            f'  {meta_html}'
            f'  <div class="grid-331">'
            f'    {hf_gpt_cell}'
            f'    {ref_cell}'
            f'    {_img_cell(gem_name,     "gemini")}'
            f'    {_img_cell(gpt_name,     "gpt")}'
            f'    {_img_cell(hf_soul_name, "hf_soul")}'
            f'    {_img_cell(hf_nano_name, "hf_nano")}'
            f'    {_img_cell(hf_mkt_name,  "hf_mkt")}'
            f'  </div>'
            f'  {prompt_html}'
            f'</section>'
        )

    # ---- product images html (자사 제품 thumbnails) ----
    product_cards = []
    for p in product_imgs:
        try:
            rel = os.path.relpath(p, run_dir).replace("\\", "/")
        except ValueError:
            rel = p.as_posix()
        product_cards.append(
            f'<a class="prod-card" href="{_esc(rel)}" target="_blank" rel="noreferrer" '
            f'title="{_esc(p.parent.name + "/" + p.name)}">'
            f'<img src="{_esc(rel)}" loading="lazy" alt="product"/>'
            f'<div class="prod-cap">{_esc(p.parent.name)}</div>'
            f'</a>'
        )
    product_html = "\n".join(product_cards)

    # ---- brand-dna richer info ----
    silhouette = brand_dna_full.get("silhouette") or {}
    fabric = brand_dna_full.get("fabric") or {}
    length = brand_dna_full.get("length") or {}
    styling_dna = brand_dna_full.get("styling") or {}
    setting_dna = brand_dna_full.get("setting") or {}
    model_dna = brand_dna_full.get("model") or {}
    photog_dna = brand_dna_full.get("photography") or {}
    md_block = brand_dna_full.get("marketing_dna") or {}

    def _kv_html(d: dict, exclude: tuple = ()) -> str:
        items = []
        for k, v in (d or {}).items():
            if k in exclude or k.startswith("_"):
                continue
            if isinstance(v, list):
                v_str = ", ".join(str(x) for x in v[:6]) + (f" (+{len(v)-6})" if len(v) > 6 else "")
            elif isinstance(v, dict):
                inner = ", ".join(f"{kk}:{vv}" for kk, vv in list(v.items())[:5])
                v_str = "{" + inner + "}"
            else:
                v_str = str(v)[:300]
            items.append(f"<p><span class='dnak'>{_esc(k)}</span> {_esc(v_str)}</p>")
        return "\n".join(items)

    silhouette_html = _kv_html(silhouette)
    fabric_html = _kv_html(fabric, exclude=("data_correction",))
    length_html = _kv_html(length)
    styling_dna_html = _kv_html(styling_dna)
    setting_dna_html = _kv_html(setting_dna)
    model_dna_html = _kv_html(model_dna, exclude=("ambassadors",))
    photog_html = _kv_html(photog_dna)

    def _dist_bars(dist: dict) -> str:
        if not dist:
            return ""
        out = []
        for k, v in dist.items():
            pct = v if isinstance(v, str) else f"{int(float(v)*100)}%" if isinstance(v, (int, float)) else str(v)
            try:
                w = float(str(pct).rstrip("%"))
            except Exception:
                w = 0
            out.append(
                f'<div class="bar-row"><span class="bar-label">{_esc(k)}</span>'
                f'<div class="bar-track"><div class="bar-fill" style="width:{min(w, 100):.0f}%"></div></div>'
                f'<span class="bar-pct">{_esc(pct)}</span></div>'
            )
        return "\n".join(out)

    md_pose_dist = _dist_bars((md_block.get("pose") or {}).get("stance_distribution") or {})
    md_expr_dist = _dist_bars((md_block.get("expression") or {}).get("base_distribution") or {})
    md_gaze_dist = _dist_bars((md_block.get("expression") or {}).get("gaze_distribution") or {})
    md_bgmood_dist = _dist_bars((md_block.get("background") or {}).get("mood_distribution") or {})
    md_vibe_dist = _dist_bars((md_block.get("background") or {}).get("vibe_distribution") or {})

    pose_rules = (md_block.get("pose") or {}).get("brand_rules") or {}
    expr_rules = (md_block.get("expression") or {}).get("brand_rules") or {}
    bg_rules = (md_block.get("background") or {}).get("brand_rules") or {}

    # ref pool html (after product + dna sections)
    ref_pool_cards = []
    for r in refs_meta:
        rid = r.get("post_id") or "?"
        local = refs_dir / f"ref_{r.get('rank', 0):02d}_{rid}.jpg"
        url = (f"01_references/{local.name}" if local.exists()
                else ("file:///" + Path(r.get("image") or "").as_posix() if r.get("image") else ""))
        ref_pool_cards.append(
            f'<div class="ref-card">'
            f'<a href="{_esc(url)}" target="_blank" rel="noreferrer">'
            f'<img src="{_esc(url)}" loading="lazy" alt="ref {rid}" />'
            f'</a>'
            f'<div class="cap">'
            f'<span class="rank">#{r.get("rank","")}</span> '
            f'<a href="{_esc(r.get("post_url") or "#")}" target="_blank" rel="noreferrer">@{_esc(r.get("handle"))}</a><br/>'
            f'<span class="muted">{_esc(", ".join((r.get("matched_axes") or [])[:3]))}</span>'
            f'</div></div>'
        )
    ref_pool_html = "\n".join(ref_pool_cards)

    # campaign header info
    by_provider = (summary.get("by_provider") or {})
    provider_pill = " ".join(
        f'<span class="pill">{_esc(p)} ok={s.get("ok",0)}/fail={s.get("fail",0)}/skip={s.get("skip",0)}</span>'
        for p, s in by_provider.items()
    )

    persona_lines = [
        f"연령 {_esc(persona.get('age_range'))}, 인종 {_esc(persona.get('demographics'))}",
        f"시그니처: {_esc(persona.get('signature_mood'))} / {_esc(persona.get('signature_style'))}",
        f"포즈 {_esc(persona.get('pose_signature'))}, 표정 {_esc(persona.get('expression_signature'))}",
    ]

    color_lines = []
    for tier in ("base", "key", "accent"):
        b = (color_dir or {}).get(tier) or {}
        names = b.get("colors") or []
        if names:
            color_lines.append(f"<b>{tier.upper()}</b> ({_esc(b.get('ratio') or '-')}): {_esc(', '.join(names))}")

    out_path = run_dir / "gallery.html"
    rel_md = "02_proposal/campaign_proposal.md"
    rel_json = "02_proposal/campaign_proposal.json"

    html = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<title>{_esc(campaign.get('brand'))} {_esc(campaign.get('season'))} — {_esc(run_dir.name)}</title>
<style>
:root {{
  --bg:#0e1117; --panel:#161a22; --panel2:#1d2230; --line:#2a3140;
  --text:#e7eaf0; --dim:#98a0ad; --accent:#7cc4ff;
  --ok:#7ee787; --warn:#ffb86b;
  --m1:#cfe6ff; --m2:#ffd68a; --m3:#cdb4ff; --m4:#b6f1c2; --m5:#ffb6c8;
  --ref:#a3a8b8; --gem:#7cc4ff; --gpt:#7ee787;
  --hfs:#ffd68a; --hfn:#cdb4ff; --hfg:#ffb6c8;
}}
* {{ box-sizing: border-box; }}
html, body {{ margin:0; background: var(--bg); color: var(--text);
              font-family: -apple-system, "Segoe UI", Roboto, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif; }}
header {{ position: sticky; top:0; z-index:5; background: var(--panel);
          border-bottom: 1px solid var(--line); padding: 14px 18px; }}
header h1 {{ margin: 0; font-size: 18px; }}
header .sub {{ color: var(--dim); font-size: 12px; margin-top: 2px; }}
header .pills {{ margin-top: 8px; display:flex; gap:6px; flex-wrap: wrap; }}
.pill {{ background: var(--panel2); color: var(--text); border:1px solid var(--line);
         padding: 3px 8px; border-radius: 999px; font-size: 12px; }}
main {{ padding: 16px 18px; }}
section.block {{ background: var(--panel); border:1px solid var(--line); border-radius: 10px;
                  padding: 12px 16px; margin-bottom: 12px; }}
section.block h2 {{ margin: 0 0 6px 0; font-size: 14px; color: var(--text); }}
section.block .body {{ font-size: 13px; color: var(--text); }}
section.block .body p {{ margin: 4px 0; }}
section.block .body .muted {{ color: var(--dim); }}
.persona {{ display:grid; gap:4px; }}
.color-tiers {{ display:grid; gap:4px; }}
.refs-pool {{ display:grid; gap:8px;
              grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); }}
.ref-card {{ background: var(--panel2); border:1px solid var(--line); border-radius: 8px;
             overflow: hidden; }}
.ref-card img {{ width:100%; aspect-ratio: 1/1; object-fit: cover; display:block; }}
.ref-card .cap {{ padding: 6px 8px; font-size: 11px; line-height: 1.4; }}
.ref-card .rank {{ background: var(--accent); color: #0b1320; border-radius: 4px;
                   padding: 1px 5px; font-weight: 700; font-size: 10px; }}
.products {{ display:grid; gap:6px;
              grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); }}
.prod-card {{ background: var(--panel2); border:1px solid var(--line); border-radius: 6px;
              overflow: hidden; text-decoration: none; color: inherit; display: block; }}
.prod-card img {{ width: 100%; aspect-ratio: 3/4; object-fit: cover; display: block; }}
.prod-card .prod-cap {{ font-size: 10px; padding: 4px 6px; color: var(--dim);
                        white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.dna-grid {{ display:grid; gap:8px;
              grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }}
.dna-cell {{ background: var(--panel2); border:1px solid var(--line); border-radius: 8px;
              padding: 8px 10px; }}
.dna-cell h3 {{ margin: 0 0 4px 0; font-size: 12px; color: var(--accent);
                text-transform: uppercase; letter-spacing: 0.5px; }}
.dna-cell .dnak {{ color: var(--dim); display:inline-block; min-width:90px;
                    font-size: 11px; }}
.dna-cell p {{ margin: 2px 0; font-size: 12px; line-height: 1.4; }}
.bar-row {{ display: flex; align-items: center; gap: 6px;
            margin: 2px 0; font-size: 11px; }}
.bar-label {{ min-width: 130px; color: var(--dim); }}
.bar-track {{ flex: 1; background: #141821; border-radius: 4px; height: 8px;
              overflow: hidden; }}
.bar-fill {{ background: linear-gradient(90deg, var(--accent), #5dafe6);
             height: 100%; }}
.bar-pct {{ min-width: 40px; text-align: right; color: var(--text);
            font-variant-numeric: tabular-nums; }}
.rules {{ display:flex; gap: 12px; flex-wrap: wrap; font-size: 11px; margin-top: 4px; }}
.rules .rule-block {{ flex: 1; min-width: 200px; }}
.rules .rule-tag {{ display: inline-block; padding: 1px 5px; border-radius: 4px;
                    background: var(--panel); margin: 1px; font-size: 11px; }}
.rules .avoid {{ color: #ff8b8b; }}
.rules .prefer {{ color: var(--ok); }}
section.scene {{ margin-bottom: 18px; padding: 12px 14px; background: var(--panel);
                  border:1px solid var(--line); border-radius: 10px; }}
section.scene .meta {{ font-size: 13px; margin-bottom: 8px; }}
.moment-line {{ color: var(--m2); font-size: 12.5px; line-height: 1.4;
                margin: 4px 0 6px 0; padding: 4px 0;
                border-left: 2px solid var(--m2); padding-left: 8px;
                background: rgba(255, 214, 138, 0.04); }}
.row {{ display:flex; gap:6px; flex-wrap: wrap; margin-top: 4px; }}
.tag {{ background: var(--panel2); border:1px solid var(--line);
         padding: 1px 6px; border-radius: 6px; font-size: 11px; }}
.tag.m1 {{ color: var(--m1); }}
.tag.m2 {{ color: var(--m2); }}
.tag.m3 {{ color: var(--m3); }}
.tag.m4 {{ color: var(--m4); }}
.tag.m5 {{ color: var(--m5); }}
.muted {{ color: var(--dim); font-size: 11px; }}
.grid4 {{ display:grid; gap:8px;
           grid-template-columns: repeat(6, minmax(0, 1fr)); }}
/* 3+3+1 layout: 3 small cols + 1 big col on right spanning 2 rows */
.grid-331 {{ display:grid; gap:10px;
              grid-template-columns: repeat(3, minmax(0, 1fr)) 2fr;
              grid-template-rows: repeat(2, auto); }}
.cell-big {{ grid-column: 4; grid-row: 1 / span 2;
             aspect-ratio: 3/4; }}
.cell-big img {{ width:100%; height:100%; object-fit: cover; }}
.cell-big .cap {{ font-size: 13px; padding: 8px 12px; }}
.cell-big .prov {{ font-size: 11px; padding: 2px 7px; }}
.cell {{ background: #000; border-radius:8px; overflow:hidden;
         position: relative; aspect-ratio: 3/4; }}
.cell img {{ width:100%; height:100%; object-fit: cover; display:block; }}
.cell.missing {{ background: linear-gradient(135deg,#222,#111);
                 display:flex; align-items:center; justify-content:center;
                 color: var(--dim); font-size: 12px; aspect-ratio: 3/4; }}
.cell .ph {{ text-align:center; }}
.cell .cap {{ position: absolute; bottom: 0; left:0; right:0;
              padding: 5px 8px;
              background: linear-gradient(transparent, rgba(0,0,0,0.65));
              font-size: 11px; }}
.prov {{ display:inline-block; padding: 1px 5px; border-radius: 4px; font-weight: 700;
         font-size: 10px; letter-spacing: 0.4px; }}
.prov-ref {{ background: var(--ref); color: #11151c; }}
.prov-gemini {{ background: var(--gem); color: #11151c; }}
.prov-gpt {{ background: var(--gpt); color: #11151c; }}
.prov-hf_soul {{ background: var(--hfs); color: #11151c; }}
.prov-hf_nano {{ background: var(--hfn); color: #11151c; }}
.prov-hf_gpt  {{ background: var(--hfg); color: #11151c; }}
.prov-hf_mkt  {{ background: var(--accent); color: #11151c; }}
details.prompt {{ margin-top: 8px; }}
details.prompt summary {{ cursor: pointer; color: var(--dim); font-size: 12px; }}
details.prompt[open] summary {{ color: var(--text); }}
details.prompt pre {{ background: var(--panel2); border:1px solid var(--line);
                       border-radius: 6px; padding: 10px;
                       white-space: pre-wrap; font-size: 11px; line-height: 1.4;
                       max-height: 400px; overflow:auto; color: var(--dim); }}
.links a {{ color: var(--accent); text-decoration: none; margin-right: 10px; }}
@media (max-width: 1400px) {{
  .grid4 {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
  .grid-331 {{ grid-template-columns: repeat(3, minmax(0, 1fr)) 1.6fr; }}
}}
@media (max-width: 900px) {{
  .grid-331 {{ grid-template-columns: repeat(3, minmax(0, 1fr));
                grid-template-rows: auto; }}
  .cell-big {{ grid-column: 1 / -1; grid-row: auto;
                aspect-ratio: 4/3; }}
}}
@media (max-width: 700px) {{
  .grid4 {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .grid-331 {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .cell-big {{ aspect-ratio: 1/1; }}
}}
::-webkit-scrollbar {{ width: 10px; height: 10px; }}
::-webkit-scrollbar-thumb {{ background: #2a3140; border-radius: 5px; }}
</style>
</head>
<body>
<header>
  <h1>{_esc(campaign.get('brand') or '?')} {_esc(campaign.get('season') or '')} — {_esc(campaign.get('season_category_input') or '')}</h1>
  <div class="sub">
    카테고리: {_esc(campaign.get('category_resolved') or '-')} &middot;
    셀렉 모드: <b style="color:var(--accent)">{_esc(mood_mode)}</b> &middot;
    생성: {_esc(proposal.get('generated_at') or '-')} &middot;
    refs: {len(refs_meta)} &middot; scenes: {len(scenes)} &middot;
    <span class="links">
      <a href="{_esc(rel_md)}" target="_blank">제안서.md</a>
      <a href="{_esc(rel_json)}" target="_blank">제안서.json</a>
      <a href="03_images/_summary.json" target="_blank">summary.json</a>
    </span>
  </div>
  <div class="pills">{provider_pill}</div>
</header>

<main>

<section class="block">
  <h2>1. 캠페인 개요</h2>
  <div class="body">
    {f'<p><b>Core message</b> — {_esc(campaign.get("core_message"))}</p>' if campaign.get("core_message") else ""}
    {f'<p><b>Positioning</b> — {_esc(campaign.get("positioning"))}</p>' if campaign.get("positioning") else ""}
    {f'<p><span class="muted">Brand moods:</span> {_esc(", ".join(campaign.get("moods") or []))}</p>' if campaign.get("moods") else ""}
  </div>
</section>

<section class="block">
  <h2>2. 인플루언서 페르소나</h2>
  <div class="body persona">
    {''.join(f'<p>{l}</p>' for l in persona_lines)}
  </div>
</section>

<section class="block">
  <h2>3. 컬러 디렉션</h2>
  <div class="body color-tiers">
    {''.join(f'<p>{l}</p>' for l in color_lines)}
  </div>
</section>

<section class="block">
  <h2>4. 카테고리 / 의류</h2>
  <div class="body">
    {f'<p><b>{_esc(garment.get("category_key"))}</b> — {_esc(garment.get("key_points"))}</p>' if garment.get("category_key") else "<p class='muted'>(매핑 없음)</p>"}
    {f'<p class="muted">아이템: {_esc(", ".join(garment.get("items") or []))}</p>' if garment.get("items") else ""}
    {f'<p class="muted">경쟁사 ref: {_esc(", ".join(garment.get("competitors") or []))}</p>' if garment.get("competitors") else ""}
  </div>
</section>

<section class="block">
  <h2>5. Brand DNA — 사용된 정보</h2>
  <div class="body dna-grid">
    {f'<div class="dna-cell"><h3>Silhouette</h3>{silhouette_html}</div>' if silhouette_html else ""}
    {f'<div class="dna-cell"><h3>Fabric</h3>{fabric_html}</div>' if fabric_html else ""}
    {f'<div class="dna-cell"><h3>Length</h3>{length_html}</div>' if length_html else ""}
    {f'<div class="dna-cell"><h3>Styling</h3>{styling_dna_html}</div>' if styling_dna_html else ""}
    {f'<div class="dna-cell"><h3>Setting</h3>{setting_dna_html}</div>' if setting_dna_html else ""}
    {f'<div class="dna-cell"><h3>Model</h3>{model_dna_html}</div>' if model_dna_html else ""}
    {f'<div class="dna-cell"><h3>Photography</h3>{photog_html}</div>' if photog_html else ""}
  </div>
</section>

<section class="block">
  <h2>6. Marketing DNA — 분포 (셀렉 점수의 근거)</h2>
  <div class="body dna-grid">
    {f'<div class="dna-cell"><h3>Pose stance</h3>{md_pose_dist}</div>' if md_pose_dist else ""}
    {f'<div class="dna-cell"><h3>Expression base</h3>{md_expr_dist}</div>' if md_expr_dist else ""}
    {f'<div class="dna-cell"><h3>Gaze direction</h3>{md_gaze_dist}</div>' if md_gaze_dist else ""}
    {f'<div class="dna-cell"><h3>Background mood</h3>{md_bgmood_dist}</div>' if md_bgmood_dist else ""}
    {f'<div class="dna-cell"><h3>Background vibe</h3>{md_vibe_dist}</div>' if md_vibe_dist else ""}
  </div>
  {('<div class="body rules">'
    + (f'<div class="rule-block"><b>Pose 지향:</b><br/>' + ' '.join(f'<span class="rule-tag prefer">{_esc(t)}</span>' for t in (pose_rules.get("prefer") or pose_rules.get("지향") or [])) + '<br/><b>금지:</b><br/>' + ' '.join(f'<span class="rule-tag avoid">{_esc(t)}</span>' for t in (pose_rules.get("avoid") or pose_rules.get("금지") or [])) + '</div>' if (pose_rules.get("avoid") or pose_rules.get("금지") or pose_rules.get("prefer") or pose_rules.get("지향")) else "")
    + (f'<div class="rule-block"><b>Expression 지향:</b><br/>' + ' '.join(f'<span class="rule-tag prefer">{_esc(t)}</span>' for t in (expr_rules.get("prefer") or expr_rules.get("지향") or [])) + '<br/><b>금지:</b><br/>' + ' '.join(f'<span class="rule-tag avoid">{_esc(t)}</span>' for t in (expr_rules.get("avoid") or expr_rules.get("금지") or [])) + '</div>' if (expr_rules.get("avoid") or expr_rules.get("금지") or expr_rules.get("prefer") or expr_rules.get("지향")) else "")
    + (f'<div class="rule-block"><b>Background 지향:</b><br/>' + ' '.join(f'<span class="rule-tag prefer">{_esc(t)}</span>' for t in (bg_rules.get("prefer") or bg_rules.get("지향") or [])) + '<br/><b>금지:</b><br/>' + ' '.join(f'<span class="rule-tag avoid">{_esc(t)}</span>' for t in (bg_rules.get("avoid") or bg_rules.get("금지") or [])) + '</div>' if (bg_rules.get("avoid") or bg_rules.get("금지") or bg_rules.get("prefer") or bg_rules.get("지향")) else "")
    + '</div>')}
</section>

<section class="block">
  <h2>7. 추구미 풀 ({len(refs_meta)}장)</h2>
  <div class="body">
    <div class="refs-pool">
      {ref_pool_html}
    </div>
  </div>
</section>

<section class="block">
  <h2>8. 씬별 결과 (REF / Gemini-3 / GPT-2 / HF-Soul / HF-Nano / HF-GPT)</h2>
  <div class="body" style="padding:0;">
    {''.join(scene_rows_html)}
  </div>
</section>

</main>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")
    return out_path


# ============================================================================
# IMC-driven scene-grouped gallery (v3)
# ============================================================================

def render_imc(run_dir: Path) -> Path:
    """Render the IMC-driven run directory as a 3-scene grouped gallery.

    Expected dir layout:
      run_dir/
        00_imc_snapshot.json
        01_references/{scene.slug}_R{NN}_*.jpg + selection.json
        02_proposal/campaign_proposal.json (imc proposal — schema_version=imc-1.0)
        03_images/{scene.slug}_R{NN}_{provider}.png + ..._prompt.txt

    Output: run_dir / "gallery.html"
    """
    proposal = _safe_load(run_dir / "02_proposal" / "campaign_proposal.json") or {}
    if proposal.get("schema_version") != "imc-1.0":
        # Not an IMC proposal — caller should fall back to render() instead.
        raise ValueError(f"not an imc-1.0 proposal: {run_dir}")

    campaign = proposal.get("campaign") or {}
    personas = proposal.get("personas") or []
    scene_plan = proposal.get("scene_plan") or []
    images_dir = run_dir / "03_images"
    refs_dir = run_dir / "01_references"

    out_path = run_dir / "gallery.html"

    # Hero/Bottom product manifests (Step C+ output) — optional
    hero_product_manifest = _safe_load(run_dir / "04_products" / "hero_product.json")
    bottom_product_manifest = _safe_load(run_dir / "04_products" / "bottom_product.json")
    hero_product_used = None
    bottom_product_used = None
    products_dir = run_dir / "04_products"
    if products_dir.exists():
        for p in products_dir.iterdir():
            if p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
                continue
            if p.name.startswith("hero_product_used"):
                hero_product_used = p.name
            elif p.name.startswith("bottom_product_used"):
                bottom_product_used = p.name

    def _img_tag(rel_path: str, alt: str = "", caption: str = "") -> str:
        cap = caption or alt
        return (f'<img src="{_esc(rel_path)}" alt="{_esc(alt)}" '
                f'data-caption="{_esc(cap)}" class="zoomable" loading="lazy" />')

    def _persona_for(scene: dict) -> Optional[dict]:
        pid = scene.get("persona_match")
        for p in personas:
            if p.get("id") == pid:
                return p
        return None

    def _scene_card(scene: dict) -> str:
        sid = scene.get("scene_id") or ""
        scene_title = scene.get("title") or sid
        persona = _persona_for(scene)
        persona_label = (
            f"{persona['id']} · {persona['name']} · {persona['demo']}"
            if persona else "(persona unmatched)"
        )
        refs = scene.get("references") or []

        # Each ref row: [ref] [gemini] [gpt] [hf_soul] [hf_nano] [hf_gpt] [hf_mkt]
        # Skip provider cells whose file is missing.
        provider_keys = list(PROVIDER_SUFFIX.keys())  # canonical order
        rows_html: list[str] = []
        for r in refs:
            rank = r.get("rank") or 0
            unit = f"{sid}_R{rank:02d}"
            ref_jpg = next(
                (p.name for p in refs_dir.glob(f"{unit}_*.jpg")), None
            )
            handle = r.get("handle") or ""
            cells = []
            ref_rel = f"01_references/{ref_jpg}" if ref_jpg else None
            ref_caption = f"REF · {scene_title} · Variant {rank} · @{handle}"
            cells.append(
                f'<div class="cell ref"><div class="cap">REF · @{_esc(handle)} '
                f'(rank {rank}, score {r.get("score", 0):.3f})</div>'
                f'{_img_tag(ref_rel, "ref", ref_caption) if ref_rel else "<div class=\"missing\">no ref</div>"}'
                + (f'<div class="moment">{_esc((r.get("moment") or "")[:160])}</div>'
                   if r.get("moment") else "")
                + "</div>"
            )
            tryon_engines = [
                ("gemini", "TRY-ON · Gemini-3-pro"),
                ("gpt",    "TRY-ON · GPT-image-2"),
            ]
            for pk in provider_keys:
                fname = _resolve_image(images_dir, unit, PROVIDER_SUFFIX[pk])
                cell_caption = f"{scene_title} · Variant {rank} · {PROVIDER_LABEL[pk]}"
                cells.append(
                    f'<div class="cell">'
                    f'<div class="cap">{_esc(PROVIDER_LABEL[pk])}</div>'
                    + (_img_tag(f"03_images/{fname}", pk, cell_caption)
                       if fname else f'<div class="missing">{_esc(pk)} —</div>')
                    + "</div>"
                )
                # Step C+ try-on cells (only for providers that have raw image present
                # AND a try-on file on disk)
                if not fname:
                    continue
                for engine_id, engine_label in tryon_engines:
                    tname = (
                        f"{unit}_{pk.replace('hf_', 'hf_')}_tryon_{engine_id}.png"
                    )
                    # match new naming: {unit}_{provider_key}_tryon_{engine}.png
                    tname = f"{unit}_{pk}_tryon_{engine_id}.png"
                    tpath = images_dir / tname
                    if not tpath.exists():
                        continue
                    tcap = (
                        f"{scene_title} · Variant {rank} · {PROVIDER_LABEL[pk]} → "
                        f"{engine_label}"
                    )
                    cells.append(
                        f'<div class="cell tryon">'
                        f'<div class="cap">{_esc(engine_label)}</div>'
                        + _img_tag(f"03_images/{tname}", f"{pk}_tryon_{engine_id}", tcap)
                        + "</div>"
                    )
            # prompt link if it exists
            prompt_path = images_dir / f"{unit}_prompt.txt"
            prompt_link = (f'<a class="prompt-link" href="03_images/{unit}_prompt.txt" '
                           f'target="_blank">prompt.txt</a>'
                           if prompt_path.exists() else "")
            rows_html.append(
                f'<div class="ref-row">'
                f'<div class="ref-row-head">Variant {rank} {prompt_link}</div>'
                f'<div class="cells">{"".join(cells)}</div>'
                f'</div>'
            )

        cats = scene.get("influencer_categories_match") or []
        cats_html = (
            f'<div style="grid-column: 1 / -1;">'
            f'<span class="mlabel">Target Influencer</span> '
            f'{_esc(", ".join(cats[:6]))}'
            f'{" <span style=\"opacity:.6\">+" + str(len(cats) - 6) + " more</span>" if len(cats) > 6 else ""}'
            f'</div>' if cats else ""
        )
        moods_inline = (
            f'<div class="meta-grid">'
            f'<div><span class="mlabel">Tone</span> {_esc(scene.get("tone"))}</div>'
            f'<div><span class="mlabel">Mood</span> {_esc(scene.get("mood"))}</div>'
            f'<div><span class="mlabel">Location</span> {_esc(scene.get("location"))}</div>'
            f'<div><span class="mlabel">Visual</span> {_esc(scene.get("visual"))}</div>'
            f'{cats_html}'
            f'</div>'
        )

        return f"""
<section class="scene-card">
  <header class="scene-head">
    <div class="scene-title">SCENE {scene.get("scene_num")} · {_esc(scene.get("title"))}</div>
    <div class="scene-persona">{_esc(persona_label)}</div>
  </header>
  {moods_inline}
  <div class="ref-rows">{''.join(rows_html)}</div>
</section>
"""

    scene_cards_html = "\n".join(_scene_card(s) for s in scene_plan)

    keyword_chips = " · ".join(
        f'<span class="kw">{_esc(k.get("kw"))}</span>'
        for k in (campaign.get("keywords") or [])
    )

    hero = campaign.get("hero_garment") or {}
    sub = campaign.get("sub_garments") or []

    def _product_block(manifest, used_filename, label_tag):
        if not (manifest and used_filename):
            return ""
        m = manifest
        return (
            f'<div class="hero-product">'
            f'<img src="04_products/{_esc(used_filename)}" alt="{_esc(label_tag.lower())}" />'
            f'<div class="hp-text">'
            f'<span class="hp-tag">{_esc(label_tag)}</span>'
            f'<b>[{_esc(m.get("code"))} → {_esc(m.get("code_folder"))}]</b> '
            f'{_esc(m.get("brand_folder"))} · {_esc(m.get("season"))} · '
            f'{_esc(m.get("lifestyle_folder"))}<br/>'
            f'<span style="opacity:.65;">file: {_esc(Path(m.get("hero_image","")).name)} '
            f'· match: {_esc(m.get("match_strategy"))}/{_esc(m.get("hero_strategy"))}</span>'
            f'</div></div>'
        )

    hero_product_html = (
        _product_block(hero_product_manifest, hero_product_used, "TRY-ON HERO (TOP)")
        + _product_block(bottom_product_manifest, bottom_product_used, "TRY-ON BOTTOM")
    )

    html = f"""<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8" />
<title>{_esc(campaign.get("brand"))} {_esc(campaign.get("season"))} · IMC Gallery</title>
<style>
  :root {{
    --bg: #0e1116; --card: #181c24; --line: #262b35; --ink: #e8eaed;
    --muted: #8a9099; --accent: #d7ff3f;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--ink); font-family:
        -apple-system, "Segoe UI", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
        padding: 24px; line-height: 1.5; }}
  header.run-head {{ margin-bottom: 24px; padding: 16px 20px;
        background: linear-gradient(160deg, #161a22, #1f2530);
        border: 1px solid var(--line); border-radius: 12px; }}
  .brand-line {{ font-size: 22px; font-weight: 800; letter-spacing: -0.01em; }}
  .brand-line .accent {{ color: var(--accent); }}
  .headline {{ margin-top: 8px; font-size: 14px; color: var(--ink); opacity: 0.9; }}
  .headline .ko {{ color: var(--muted); display: block; margin-top: 2px; }}
  .keywords {{ margin-top: 8px; font-size: 12px; }}
  .keywords .kw {{ background: var(--card); border: 1px solid var(--line);
        padding: 3px 9px; border-radius: 999px; margin-right: 6px;
        color: var(--accent); font-weight: 600; }}
  .garments {{ margin-top: 10px; font-size: 12px; color: var(--muted); }}
  .garments b {{ color: var(--ink); }}
  .scene-card {{ margin-bottom: 32px; padding: 18px; background: var(--card);
        border: 1px solid var(--line); border-radius: 12px; }}
  .scene-head {{ display: flex; justify-content: space-between; align-items: baseline;
        margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }}
  .scene-title {{ font-size: 18px; font-weight: 800; letter-spacing: -0.01em; }}
  .scene-persona {{ font-size: 11px; color: var(--accent); letter-spacing: 0.06em; }}
  .meta-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px 18px;
        font-size: 11.5px; color: var(--muted); padding: 8px 0; margin-bottom: 12px;
        border-top: 1px dashed var(--line); border-bottom: 1px dashed var(--line); }}
  .meta-grid .mlabel {{ color: var(--accent); font-weight: 700; letter-spacing: 0.08em;
        margin-right: 6px; font-size: 9.5px; text-transform: uppercase; }}
  .ref-rows {{ display: flex; flex-direction: column; gap: 14px; }}
  .ref-row {{ }}
  .ref-row-head {{ font-size: 11px; color: var(--muted); letter-spacing: 0.08em;
        margin-bottom: 6px; text-transform: uppercase; }}
  .ref-row .prompt-link {{ margin-left: 10px; color: var(--accent);
        text-decoration: none; font-size: 10.5px; }}
  .ref-row .prompt-link:hover {{ text-decoration: underline; }}
  .cells {{ display: grid;
        grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        gap: 8px; }}
  .cell {{ background: #0d1018; border: 1px solid var(--line); border-radius: 8px;
        padding: 6px; display: flex; flex-direction: column; gap: 4px; }}
  .cell.ref {{ border-color: #3a4055; }}
  .cell .cap {{ font-size: 9.5px; color: var(--muted); letter-spacing: 0.06em;
        text-transform: uppercase; }}
  .cell img {{ width: 100%; aspect-ratio: 3/4; object-fit: cover;
        border-radius: 4px; background: #000; }}
  .cell .missing {{ display: flex; align-items: center; justify-content: center;
        aspect-ratio: 3/4; background: #1a1f2a; color: #5a6273; font-size: 11px;
        border-radius: 4px; }}
  .cell .moment {{ font-size: 10.5px; color: var(--muted); line-height: 1.3;
        font-style: italic; padding-top: 2px; }}

  /* Step C+ try-on cell highlight */
  .cell.tryon {{ border-color: #d7ff3f55; box-shadow: 0 0 0 1px #d7ff3f22 inset; }}
  .cell.tryon .cap {{ color: var(--accent); }}

  /* Hero product thumbnail in run-head */
  .hero-product {{ margin-top: 12px; display: flex; align-items: center;
        gap: 12px; padding-top: 10px; border-top: 1px dashed var(--line); }}
  .hero-product img {{ width: 84px; height: 112px; object-fit: cover;
        border-radius: 6px; background: #000; flex-shrink: 0; }}
  .hero-product .hp-text {{ font-size: 11.5px; color: var(--muted); line-height: 1.45; }}
  .hero-product .hp-text b {{ color: var(--ink); }}
  .hero-product .hp-text .hp-tag {{ display: inline-block;
        background: var(--accent); color: #000; font-weight: 700;
        padding: 2px 7px; border-radius: 999px; font-size: 9.5px;
        letter-spacing: 0.06em; margin-right: 6px; }}

  /* Lightbox */
  img.zoomable {{ cursor: zoom-in; transition: filter .12s ease; }}
  img.zoomable:hover {{ filter: brightness(1.08); }}
  .lightbox {{ position: fixed; inset: 0; background: rgba(0,0,0,.92);
        display: none; align-items: center; justify-content: center;
        z-index: 1000; padding: 24px; flex-direction: column; gap: 12px; }}
  .lightbox.open {{ display: flex; }}
  .lightbox img {{ max-width: min(96vw, 1400px);
        max-height: calc(100vh - 110px); object-fit: contain;
        border-radius: 6px; box-shadow: 0 20px 60px rgba(0,0,0,.6);
        cursor: zoom-out; }}
  .lightbox .lb-cap {{ color: #fff; font-size: 12px; letter-spacing: 0.04em;
        max-width: 90vw; text-align: center; opacity: 0.9; }}
  .lightbox .lb-close {{ position: absolute; top: 18px; right: 22px;
        width: 38px; height: 38px; border-radius: 50%; border: 1px solid #444;
        background: rgba(20,20,20,.8); color: #fff; font-size: 22px;
        line-height: 0; cursor: pointer; }}
  .lightbox .lb-close:hover {{ background: var(--accent); color: #000;
        border-color: var(--accent); }}
  .lightbox .lb-nav {{ position: absolute; top: 50%; transform: translateY(-50%);
        background: rgba(20,20,20,.65); color: #fff; border: 1px solid #444;
        width: 44px; height: 44px; border-radius: 50%; cursor: pointer;
        font-size: 20px; line-height: 0; user-select: none; }}
  .lightbox .lb-nav:hover {{ background: var(--accent); color: #000;
        border-color: var(--accent); }}
  .lightbox .lb-prev {{ left: 24px; }}
  .lightbox .lb-next {{ right: 24px; }}
  .lightbox .lb-counter {{ position: absolute; top: 24px; left: 24px;
        color: #888; font-size: 11px; letter-spacing: 0.08em; }}
</style>
</head><body>

<header class="run-head">
  <div class="brand-line">
    <span class="accent">{_esc(campaign.get("brand"))}</span>
    {_esc(campaign.get("season"))} · {_esc(campaign.get("lifestyle_display") or campaign.get("lifestyle"))}
    <span style="opacity:.5; font-size:11px; margin-left:10px;">imc_driven · {_esc(campaign.get("id"))}</span>
  </div>
  <div class="headline">
    {_esc(campaign.get("headline_en"))}
    <span class="ko">{_esc(campaign.get("headline_ko"))}</span>
  </div>
  <div class="keywords">{keyword_chips}</div>
  <div class="garments">
    <b>HERO</b>: [{_esc(hero.get("code"))}] {_esc(hero.get("desc"))}
    {' &nbsp;·&nbsp; ' if sub else ''}
    {' '.join(f'<b>{_esc(s.get("code"))}</b>: {_esc(s.get("desc"))}' for s in sub)}
  </div>
  {hero_product_html}
</header>

{scene_cards_html}

<div class="lightbox" id="lb" role="dialog" aria-hidden="true">
  <button class="lb-close" id="lb-close" aria-label="Close">×</button>
  <button class="lb-nav lb-prev" id="lb-prev" aria-label="Previous">‹</button>
  <button class="lb-nav lb-next" id="lb-next" aria-label="Next">›</button>
  <div class="lb-counter" id="lb-counter"></div>
  <img id="lb-img" alt="" />
  <div class="lb-cap" id="lb-cap"></div>
</div>

<script>
(function() {{
  const imgs = Array.from(document.querySelectorAll('img.zoomable'));
  const lb = document.getElementById('lb');
  const lbImg = document.getElementById('lb-img');
  const lbCap = document.getElementById('lb-cap');
  const lbCounter = document.getElementById('lb-counter');
  let idx = -1;

  function open(i) {{
    if (i < 0 || i >= imgs.length) return;
    idx = i;
    const t = imgs[i];
    lbImg.src = t.src;
    lbImg.alt = t.alt || '';
    lbCap.textContent = t.dataset.caption || t.alt || '';
    lbCounter.textContent = (i + 1) + ' / ' + imgs.length;
    lb.classList.add('open');
    lb.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  }}
  function close() {{
    lb.classList.remove('open');
    lb.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    idx = -1;
  }}
  function next(d) {{
    if (idx < 0) return;
    open((idx + d + imgs.length) % imgs.length);
  }}

  imgs.forEach((el, i) => el.addEventListener('click', e => {{
    e.preventDefault();
    open(i);
  }}));
  document.getElementById('lb-close').addEventListener('click', close);
  document.getElementById('lb-prev').addEventListener('click', e => {{ e.stopPropagation(); next(-1); }});
  document.getElementById('lb-next').addEventListener('click', e => {{ e.stopPropagation(); next(1); }});
  lb.addEventListener('click', e => {{ if (e.target === lb) close(); }});
  lbImg.addEventListener('click', close);
  document.addEventListener('keydown', e => {{
    if (!lb.classList.contains('open')) return;
    if (e.key === 'Escape') close();
    else if (e.key === 'ArrowLeft') next(-1);
    else if (e.key === 'ArrowRight') next(1);
  }});
}})();
</script>

</body></html>
"""
    out_path.write_text(html, encoding="utf-8")
    return out_path


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Render run dir → gallery.html")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--no-open", action="store_true",
                    help="don't auto-open in browser")
    ap.add_argument("--imc", action="store_true",
                    help="render IMC-driven layout (3 scene cards)")
    args = ap.parse_args()
    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        print(f"[ERROR] not a directory: {run_dir}", file=sys.stderr)
        return 1
    if args.imc:
        out = render_imc(run_dir)
    else:
        out = render(run_dir)
    print(f"[OK] gallery: {out}")
    if not args.no_open:
        try:
            webbrowser.open(out.as_uri())
        except Exception as e:
            print(f"[warn] could not auto-open: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
