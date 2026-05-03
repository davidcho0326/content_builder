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

# image filename suffixes per provider
PROVIDER_SUFFIX = {
    "gemini":  "_gemini.png",
    "gpt":     "_gpt.png",
    "hf_soul": "_hf_soul.png",
    "hf_nano": "_hf_nano.png",
    "hf_gpt":  "_hf_gpt.png",
    "hf_mkt":  "_hf_mkt.png",
}

PROVIDER_LABEL = {
    "gemini":  "Gemini-3-pro",
    "gpt":     "GPT-image-2",
    "hf_soul": "HF Soul 2.0",
    "hf_nano": "HF Nano-Banana Pro",
    "hf_gpt":  "HF GPT-image 2",
    "hf_mkt":  "HF Marketing Studio",
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


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Render run dir → gallery.html")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--no-open", action="store_true",
                    help="don't auto-open in browser")
    args = ap.parse_args()
    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        print(f"[ERROR] not a directory: {run_dir}", file=sys.stderr)
        return 1
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
