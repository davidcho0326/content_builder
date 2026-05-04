"""Build a full input/output review board for one campaign run.

The regular gallery focuses on generated-image comparison. This renderer adds
the upstream inputs as first-class context: IMC snapshot, selected products,
influencer references, prompt text, and provider outputs in one HTML file.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
import webbrowser
from pathlib import Path
from typing import Any


PROVIDERS = [
    ("gpt", "GPT-image-2", "_gpt.png"),
    ("hf_gpt", "HF GPT-image 2", "_hf_gpt.png"),
    ("hf_mkt", "HF Marketing Studio", "_hf_mkt.png"),
    ("gemini", "Gemini legacy", "_gemini.png"),
    ("hf_soul", "HF Soul legacy", "_hf_soul.png"),
    ("hf_nano", "HF Nano legacy", "_hf_nano.png"),
]


def _load_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _esc(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _short_path(value: Any, keep: int = 4) -> str:
    if not value:
        return ""
    parts = str(value).replace("\\", "/").split("/")
    return "/".join(parts[-keep:]) if len(parts) > keep else str(value)


def _as_rel_or_uri(path: Path, run_dir: Path) -> str:
    try:
        return path.resolve().relative_to(run_dir.resolve()).as_posix()
    except Exception:
        try:
            return path.resolve().as_uri()
        except Exception:
            return path.as_posix()


def _json_details(title: str, data: Any, open_by_default: bool = False) -> str:
    if data in ({}, [], None, ""):
        return ""
    body = json.dumps(data, ensure_ascii=False, indent=2)
    open_attr = " open" if open_by_default else ""
    return (
        f'<details class="json-block"{open_attr}>'
        f"<summary>{_esc(title)}</summary>"
        f"<pre>{_esc(body)}</pre>"
        "</details>"
    )


def _pill(value: Any, class_name: str = "") -> str:
    if value in (None, ""):
        return ""
    return f'<span class="pill {class_name}">{_esc(value)}</span>'


def _image_link(src: str, label: str, caption: str = "", class_name: str = "") -> str:
    if not src:
        return (
            f'<div class="image-tile missing {class_name}">'
            f'<div class="tile-label">{_esc(label)}</div>'
            "<div class=\"placeholder\">missing</div>"
            "</div>"
        )
    cap = caption or label
    return (
        f'<figure class="image-tile {class_name}">'
        f'<a href="{_esc(src)}" target="_blank" rel="noreferrer">'
        f'<img class="zoomable" src="{_esc(src)}" alt="{_esc(label)}" '
        f'data-caption="{_esc(cap)}" loading="lazy" />'
        "</a>"
        f'<figcaption><span>{_esc(label)}</span>{_esc(caption)}</figcaption>'
        "</figure>"
    )


def _find_ref_image(refs_dir: Path, scene_id: str, rank: int, ref: dict[str, Any], run_dir: Path) -> str:
    pattern = f"{scene_id}_R{rank:02d}_*"
    matches = sorted(p for p in refs_dir.glob(pattern) if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})
    if matches:
        return _as_rel_or_uri(matches[0], run_dir)
    image = ref.get("image")
    if image:
        p = Path(image)
        if p.exists():
            return _as_rel_or_uri(p, run_dir)
    return ""


def _provider_image(images_dir: Path, unit_id: str, suffix: str, run_dir: Path) -> str:
    p = images_dir / f"{unit_id}{suffix}"
    return _as_rel_or_uri(p, run_dir) if p.exists() else ""


def _product_panel(run_dir: Path, manifest: dict[str, Any]) -> str:
    products_dir = run_dir / "04_products"
    selected = manifest.get("selected_match") or {}
    selected_role = manifest.get("selected_role") or ""
    top = manifest.get("top_match") or {}
    bottom = manifest.get("bottom_match") or {}
    brief = manifest.get("product_brief") or {}

    def product_card(role: str, match: dict[str, Any], used_name: str) -> str:
        if not match:
            return ""
        role_brief = (brief.get(role.lower()) or {}) if isinstance(brief, dict) else {}
        img = products_dir / used_name
        src = _as_rel_or_uri(img, run_dir) if img.exists() else ""
        preserve = "".join(f"<li>{_esc(x)}</li>" for x in role_brief.get("must_preserve", [])[:6])
        variants = "".join(
            f'<li><code>{_esc(_short_path(v))}</code></li>'
            for v in (match.get("color_variants") or [])[:5]
        )
        trend = "".join(
            f'<li><code>{_esc(_short_path(v))}</code></li>'
            for v in (match.get("trend_examples") or [])[:3]
        )
        return f"""
<section class="product-row">
  <div class="product-media">
    {_image_link(src, role.upper(), _short_path(match.get("hero_image")), "product")}
  </div>
  <div class="product-copy">
    <h3>{_esc(role.upper())} product</h3>
    <div class="kv">
      <div><b>Code</b><span>{_esc(match.get("code"))} / {_esc(match.get("code_folder"))}</span></div>
      <div><b>Lifestyle</b><span>{_esc(match.get("lifestyle_folder"))}</span></div>
      <div><b>Match</b><span>{_esc(match.get("match_strategy"))} / {_esc(match.get("hero_strategy"))}</span></div>
      <div><b>Color signal</b><span>{_esc(role_brief.get("color_signal"))}</span></div>
      <div><b>Source</b><span><code>{_esc(_short_path(match.get("hero_image"), 6))}</code></span></div>
    </div>
    <div class="split-list">
      <div><h4>Must preserve</h4><ul>{preserve}</ul></div>
      <div><h4>Variants / trend refs</h4><ul>{variants}{trend}</ul></div>
    </div>
  </div>
</section>
"""

    rules = "".join(f"<li>{_esc(x)}</li>" for x in (brief.get("global_rules") or []))
    if selected:
        cards = product_card(selected_role or "selected", selected, "selected_product_used.png")
        note = "Only this selected garment is sent to image generation. The rest of the styling is generated from the scene mood."
    else:
        cards = product_card("top", top, "hero_product_used.png") + product_card("bottom", bottom, "bottom_product_used.png")
        note = "Legacy run: product inputs are shown as recorded by the run."
    return f"""
<section class="band" id="products">
  <div class="band-head">
    <div>
      <div class="eyebrow">INPUT 01</div>
      <h2>Single Product Grounding</h2>
    </div>
    <div class="band-note">{_esc(note)}</div>
  </div>
  <div class="product-stack">
    {cards}
  </div>
  <div class="rules"><h3>Generation rules</h3><ul>{rules}</ul></div>
  {_json_details("Raw outfit_manifest.json", manifest)}
</section>
"""


def _imc_panel(imc: dict[str, Any], proposal: dict[str, Any], run_dir: Path) -> str:
    campaign = proposal.get("campaign") or {}
    snapshot_headline = imc.get("headline") or {}
    keywords = campaign.get("keywords") or imc.get("keywords_3") or []
    personas = proposal.get("personas") or imc.get("persona_groups") or []
    scenes = proposal.get("scene_plan") or []
    source_path = campaign.get("imc_source_path") or ((imc.get("_meta") or {}).get("artifacts") or "")

    keyword_html = "".join(
        f'<div class="keyword"><b>{_esc(k.get("kw"))}</b><span>{_esc(k.get("score"))}</span>'
        f'<p>{_esc(k.get("rationale"))}</p></div>'
        for k in keywords[:6]
        if isinstance(k, dict)
    )
    persona_html = "".join(
        f'<div class="persona"><b>{_esc(p.get("id"))} · {_esc(p.get("name"))}</b>'
        f'<span>{_esc(p.get("demo"))}</span></div>'
        for p in personas[:6]
        if isinstance(p, dict)
    )
    scene_chips = "".join(
        f'<a href="#{_esc(s.get("scene_id"))}" class="scene-chip">'
        f'{_esc(s.get("scene_num"))}. {_esc(s.get("title"))}</a>'
        for s in scenes
        if isinstance(s, dict)
    )
    return f"""
<section class="band" id="imc">
  <div class="band-head">
    <div>
      <div class="eyebrow">INPUT 00</div>
      <h2>IMC Strategy Snapshot</h2>
    </div>
    <div class="band-note"><code>{_esc(_short_path(source_path, 7))}</code></div>
  </div>
  <div class="overview-grid">
    <div class="overview">
      <h3>Campaign</h3>
      <p class="headline">{_esc(campaign.get("headline_en") or snapshot_headline.get("en_main"))}</p>
      <p>{_esc(campaign.get("headline_ko") or snapshot_headline.get("ko_sub"))}</p>
      <div class="meta-pills">
        {_pill(campaign.get("brand") or imc.get("brand"))}
        {_pill(campaign.get("season") or imc.get("season"))}
        {_pill(campaign.get("lifestyle_display") or imc.get("lifestyle"))}
        {_pill(campaign.get("id"))}
      </div>
    </div>
    <div class="overview">
      <h3>Scene anchors</h3>
      <div class="scene-chips">{scene_chips}</div>
    </div>
  </div>
  <div class="keyword-grid">{keyword_html}</div>
  <div class="persona-strip">{persona_html}</div>
  {_json_details("Raw campaign_proposal.json", proposal)}
  {_json_details("Raw 00_imc_snapshot.json", imc)}
</section>
"""


def _scene_panel(
    run_dir: Path,
    refs_dir: Path,
    images_dir: Path,
    scene: dict[str, Any],
    selected_refs: list[dict[str, Any]],
) -> str:
    scene_id = scene.get("scene_id") or f'S{scene.get("scene_num", "00")}'
    scene_refs = scene.get("references") or []
    if not scene_refs:
        scene_refs = [
            r for r in selected_refs
            if r.get("scene_id") == scene_id
        ]
    if not scene_refs:
        scene_refs = [{}]

    selected_product = run_dir / "04_products" / "selected_product_used.png"
    if not selected_product.exists():
        selected_product = run_dir / "04_products" / "hero_product_used.png"
    if not selected_product.exists():
        selected_product = run_dir / "04_products" / "bottom_product_used.png"
    selected_product_src = _as_rel_or_uri(selected_product, run_dir) if selected_product.exists() else ""
    product_inputs = (
        '<div class="mini-products">'
        '<h4>Single product input used for this scene</h4>'
        '<div class="mini-grid">'
        f'{_image_link(selected_product_src, "Selected product", selected_product.name if selected_product_src else "", "mini-product")}'
        '</div>'
        '</div>'
    )

    ref_rows = []
    for i, ref in enumerate(scene_refs, start=1):
        rank = int(ref.get("rank") or i)
        unit_id = f"{scene_id}_R{rank:02d}"
        ref_src = _find_ref_image(refs_dir, scene_id, rank, ref, run_dir)
        prompt_path = images_dir / f"{unit_id}_prompt.txt"
        prompt_text = _read_text(prompt_path)
        provider_tiles = []
        for key, label, suffix in PROVIDERS:
            src = _provider_image(images_dir, unit_id, suffix, run_dir)
            if not src and key in {"gemini", "hf_soul", "hf_nano"}:
                continue
            provider_tiles.append(_image_link(src, label, f"{unit_id}{suffix}", f"output provider-{key}"))
        axes = "".join(f"<li>{_esc(x)}</li>" for x in (ref.get("matched_axes") or [])[:10])
        model_meta = ref.get("model") or {}
        background_meta = ref.get("background") or {}
        styling_meta = ref.get("styling") or {}
        meta_bits = "".join(
            _pill(v, "soft")
            for v in [
                model_meta.get("gender"),
                model_meta.get("age group"),
                model_meta.get("pose"),
                background_meta.get("shooting composition"),
                background_meta.get("mood"),
                styling_meta.get("fashion style"),
                styling_meta.get("overall fashion color tone"),
            ]
        )
        prompt_html = (
            f'<details class="prompt"><summary>Prompt text · {len(prompt_text):,} chars</summary>'
            f"<pre>{_esc(prompt_text)}</pre></details>"
            if prompt_text else ""
        )
        ref_rows.append(f"""
<div class="variant-block">
  <div class="input-column">
    {_image_link(ref_src, "Influencer reference", f"@{ref.get('handle') or ''} · score {ref.get('score') or ''}", "reference")}
    {product_inputs}
    <div class="ref-data">
      <h4>@{_esc(ref.get("handle"))} · {_esc(ref.get("post_id"))}</h4>
      <p><a href="{_esc(ref.get("post_url") or "#")}" target="_blank" rel="noreferrer">Instagram post</a></p>
      <p><code>{_esc(_short_path(ref.get("image"), 7))}</code></p>
      <div class="meta-pills">{meta_bits}</div>
      <details><summary>Matching axes</summary><ul>{axes}</ul></details>
    </div>
  </div>
  <div class="output-column">
    <div class="output-grid">{''.join(provider_tiles)}</div>
    {prompt_html}
  </div>
</div>
""")

    categories = "".join(
        _pill(x, "category")
        for x in (scene.get("influencer_categories_match") or [])[:10]
    )
    return f"""
<section class="band scene-band" id="{_esc(scene_id)}">
  <div class="band-head">
    <div>
      <div class="eyebrow">SCENE {_esc(scene.get("scene_num"))}</div>
      <h2>{_esc(scene.get("title"))}</h2>
    </div>
    <div class="band-note">{_esc(scene_id)}</div>
  </div>
  <div class="scene-brief">
    <div><b>Tone</b><span>{_esc(scene.get("tone"))}</span></div>
    <div><b>Mood</b><span>{_esc(scene.get("mood"))}</span></div>
    <div><b>Location</b><span>{_esc(scene.get("location"))}</span></div>
    <div><b>Visual</b><span>{_esc(scene.get("visual"))}</span></div>
  </div>
  <div class="meta-pills categories">{categories}</div>
  {''.join(ref_rows)}
</section>
"""


def _summary_panel(images_dir: Path) -> str:
    summary = _load_json(images_dir / "_summary.json", {})
    hf_summary = _load_json(images_dir / "_hf_summary.json", {})
    items = []
    by_provider = summary.get("by_provider") or {}
    for provider, stats in by_provider.items():
        items.append(
            f'<div class="stat"><b>{_esc(provider)}</b>'
            f'<span>ok {stats.get("ok", 0)} · fail {stats.get("fail", 0)} · skip {stats.get("skip", 0)}</span></div>'
        )
    hf_jobs = hf_summary.get("jobs") or []
    if hf_jobs:
        providers = ", ".join(sorted({j.get("provider", "") for j in hf_jobs if j.get("provider")}))
        items.append(f'<div class="stat"><b>higgsfield</b><span>{len(hf_jobs)} jobs · {providers}</span></div>')
    return f"""
<section class="band" id="run-summary">
  <div class="band-head">
    <div>
      <div class="eyebrow">RUN</div>
      <h2>Generation Summary</h2>
    </div>
  </div>
  <div class="stats">{''.join(items)}</div>
  {_json_details("OpenAI _summary.json", summary, True)}
  {_json_details("Higgsfield _hf_summary.json", hf_summary, True)}
</section>
"""


def render(run_dir: Path) -> Path:
    refs_dir = run_dir / "01_references"
    proposal_dir = run_dir / "02_proposal"
    images_dir = run_dir / "03_images"
    products_dir = run_dir / "04_products"

    selection = _load_json(refs_dir / "selection.json", {})
    proposal = _load_json(proposal_dir / "campaign_proposal.json", {})
    imc = _load_json(run_dir / "00_imc_snapshot.json", {})
    manifest = _load_json(products_dir / "outfit_manifest.json", {})
    scenes = proposal.get("scene_plan") or []
    selected_refs = []
    for group in selection.get("scenes", []) or []:
        selected_refs.extend(group.get("refs") or [])

    campaign = proposal.get("campaign") or {}
    title = " / ".join(
        str(x)
        for x in [
            campaign.get("brand") or imc.get("brand") or "Campaign",
            campaign.get("season") or imc.get("season") or "",
            campaign.get("lifestyle_display") or imc.get("lifestyle") or "",
        ]
        if x
    )
    scene_nav = "".join(
        f'<a href="#{_esc(s.get("scene_id"))}">{_esc(s.get("scene_num"))}. {_esc(s.get("title"))}</a>'
        for s in scenes
    )
    scene_sections = "".join(_scene_panel(run_dir, refs_dir, images_dir, s, selected_refs) for s in scenes)

    html_doc = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{_esc(title)} · Full Gallery</title>
<style>
  :root {{
    --bg: #f4f1eb;
    --ink: #15171a;
    --muted: #68707a;
    --panel: #ffffff;
    --line: #d9d2c6;
    --soft: #ede7dd;
    --accent: #0b5c6b;
    --accent-2: #b7cf4a;
    --bad: #a53d2d;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    color: var(--ink);
    background: var(--bg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
    line-height: 1.45;
  }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  code {{ font-family: "Cascadia Mono", Consolas, monospace; font-size: .88em; }}
  .topbar {{
    position: sticky;
    top: 0;
    z-index: 20;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 18px;
    padding: 12px 22px;
    background: rgba(244, 241, 235, .94);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--line);
  }}
  .topbar strong {{ font-size: 14px; }}
  .nav {{ display: flex; flex-wrap: wrap; gap: 10px; font-size: 12px; }}
  .hero {{
    padding: 30px 24px 18px;
    border-bottom: 1px solid var(--line);
    background: #e8dfd2;
  }}
  .hero h1 {{
    margin: 0;
    max-width: 980px;
    font-size: 34px;
    line-height: 1.08;
    letter-spacing: 0;
  }}
  .hero p {{ margin: 10px 0 0; max-width: 900px; color: var(--muted); }}
  .run-path {{ margin-top: 14px; font-size: 12px; color: var(--muted); }}
  .band {{
    width: min(1500px, calc(100vw - 36px));
    margin: 22px auto;
    padding: 20px;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 8px;
  }}
  .band-head {{
    display: flex;
    justify-content: space-between;
    align-items: end;
    gap: 16px;
    margin-bottom: 16px;
    border-bottom: 1px solid var(--line);
    padding-bottom: 12px;
  }}
  .eyebrow {{
    font-size: 11px;
    color: var(--accent);
    font-weight: 800;
    letter-spacing: .08em;
  }}
  h2, h3, h4 {{ margin: 0; letter-spacing: 0; }}
  h2 {{ font-size: 22px; }}
  h3 {{ font-size: 15px; }}
  h4 {{ font-size: 12px; color: var(--muted); text-transform: uppercase; }}
  .band-note {{ font-size: 12px; color: var(--muted); text-align: right; }}
  .overview-grid {{ display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(280px, .8fr); gap: 14px; }}
  .overview {{ border: 1px solid var(--line); border-radius: 8px; padding: 14px; background: #fbfaf7; }}
  .headline {{ font-weight: 800; font-size: 20px; color: var(--ink); }}
  .meta-pills, .scene-chips {{ display: flex; gap: 7px; flex-wrap: wrap; margin-top: 10px; }}
  .pill, .scene-chip {{
    display: inline-flex;
    align-items: center;
    min-height: 26px;
    padding: 4px 9px;
    border: 1px solid var(--line);
    border-radius: 999px;
    background: var(--soft);
    color: var(--ink);
    font-size: 12px;
  }}
  .pill.soft {{ color: var(--muted); background: #f7f4ef; }}
  .pill.category {{ background: #eef5f1; border-color: #c8dbd2; }}
  .keyword-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 14px; }}
  .keyword, .persona {{
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 10px;
    background: #fbfaf7;
  }}
  .keyword b {{ color: var(--accent); }}
  .keyword span {{ float: right; color: var(--muted); font-size: 12px; }}
  .keyword p {{ clear: both; margin: 7px 0 0; color: var(--muted); font-size: 12px; }}
  .persona-strip {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 10px; }}
  .persona span {{ display: block; margin-top: 4px; color: var(--muted); font-size: 12px; }}
  .product-stack {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 14px; }}
  .product-row {{
    display: grid;
    grid-template-columns: 170px minmax(0, 1fr);
    gap: 14px;
    align-items: start;
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 12px;
    background: #fbfaf7;
  }}
  .kv {{ display: grid; gap: 6px; margin-top: 10px; }}
  .kv div {{ display: grid; grid-template-columns: 88px minmax(0, 1fr); gap: 10px; font-size: 12px; }}
  .kv b {{ color: var(--muted); }}
  .split-list {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px; }}
  ul {{ margin: 8px 0 0; padding-left: 18px; }}
  li {{ margin: 3px 0; color: var(--muted); font-size: 12px; }}
  .rules {{ margin-top: 14px; border-top: 1px solid var(--line); padding-top: 14px; }}
  .rules ul {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px 22px; }}
  .scene-brief {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 8px; }}
  .scene-brief div {{ background: #fbfaf7; border: 1px solid var(--line); border-radius: 8px; padding: 10px; }}
  .scene-brief b {{ display: block; color: var(--accent); font-size: 11px; text-transform: uppercase; margin-bottom: 4px; }}
  .scene-brief span {{ color: var(--muted); font-size: 12px; }}
  .variant-block {{
    display: grid;
    grid-template-columns: 310px minmax(0, 1fr);
    gap: 14px;
    margin-top: 14px;
    padding-top: 14px;
    border-top: 1px solid var(--line);
  }}
  .input-column, .output-column {{ min-width: 0; }}
  .mini-products {{
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px solid var(--line);
  }}
  .mini-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px; margin-top: 8px; }}
  .ref-data {{ margin-top: 10px; font-size: 12px; }}
  .ref-data p {{ margin: 5px 0; color: var(--muted); overflow-wrap: anywhere; }}
  .output-grid {{ display: grid; grid-template-columns: repeat(3, minmax(190px, 1fr)); gap: 10px; }}
  .image-tile {{
    margin: 0;
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 7px;
    background: #fbfaf7;
    min-width: 0;
  }}
  .image-tile img {{
    display: block;
    width: 100%;
    aspect-ratio: 3 / 4;
    object-fit: cover;
    border-radius: 6px;
    background: #111;
  }}
  .image-tile.product img {{ object-fit: contain; background: #f2f2f0; }}
  .image-tile.mini-product img {{ object-fit: contain; background: #f2f2f0; }}
  .image-tile.mini-product figcaption {{ min-height: 28px; }}
  .image-tile.reference img {{ object-fit: cover; }}
  .image-tile figcaption {{
    display: flex;
    flex-direction: column;
    gap: 2px;
    margin-top: 6px;
    min-height: 34px;
    color: var(--muted);
    font-size: 11px;
    overflow-wrap: anywhere;
  }}
  .image-tile figcaption span {{ color: var(--ink); font-weight: 800; }}
  .image-tile.missing .placeholder {{
    display: flex;
    align-items: center;
    justify-content: center;
    aspect-ratio: 3 / 4;
    border-radius: 6px;
    background: #eee7dc;
    color: var(--bad);
    font-size: 12px;
  }}
  .tile-label {{ font-size: 11px; font-weight: 800; margin-bottom: 6px; }}
  .prompt, .json-block {{ margin-top: 12px; border: 1px solid var(--line); border-radius: 8px; background: #fbfaf7; }}
  details summary {{ cursor: pointer; padding: 9px 11px; font-weight: 800; color: var(--accent); font-size: 12px; }}
  pre {{
    margin: 0;
    padding: 12px;
    border-top: 1px solid var(--line);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    max-height: 420px;
    overflow: auto;
    font-size: 11px;
    color: #30343a;
    background: #fffdf9;
  }}
  .stats {{ display: flex; flex-wrap: wrap; gap: 10px; }}
  .stat {{ border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; min-width: 190px; background: #fbfaf7; }}
  .stat b {{ display: block; color: var(--accent); }}
  .stat span {{ font-size: 12px; color: var(--muted); }}
  img.zoomable {{ cursor: zoom-in; }}
  .lightbox {{
    position: fixed;
    inset: 0;
    display: none;
    align-items: center;
    justify-content: center;
    flex-direction: column;
    gap: 10px;
    padding: 24px;
    background: rgba(0,0,0,.9);
    z-index: 50;
  }}
  .lightbox.open {{ display: flex; }}
  .lightbox img {{ max-width: 96vw; max-height: calc(100vh - 94px); object-fit: contain; border-radius: 8px; }}
  .lightbox .caption {{ color: white; font-size: 12px; max-width: 92vw; text-align: center; }}
  .lightbox button {{
    position: absolute;
    top: 18px;
    right: 18px;
    width: 38px;
    height: 38px;
    border: 1px solid rgba(255,255,255,.35);
    border-radius: 8px;
    color: #fff;
    background: rgba(0,0,0,.4);
    cursor: pointer;
  }}
  @media (max-width: 980px) {{
    .overview-grid, .product-stack, .product-row, .variant-block {{ grid-template-columns: 1fr; }}
    .keyword-grid, .persona-strip, .scene-brief, .output-grid, .rules ul {{ grid-template-columns: 1fr; }}
    .topbar {{ position: static; align-items: flex-start; flex-direction: column; }}
    .hero h1 {{ font-size: 26px; }}
  }}
</style>
</head>
<body>
<nav class="topbar">
  <strong>{_esc(title)} · Full Input/Output Gallery</strong>
  <div class="nav">
    <a href="#imc">IMC</a>
    <a href="#products">Products</a>
    {scene_nav}
    <a href="#run-summary">Run summary</a>
  </div>
</nav>
<header class="hero">
  <h1>{_esc(campaign.get("headline_en") or title)}</h1>
  <p>{_esc(campaign.get("headline_ko") or "Input data, selected references, product grounding, prompts, and generated outputs in one review board.")}</p>
  <div class="run-path"><code>{_esc(str(run_dir))}</code></div>
</header>
{_imc_panel(imc, proposal, run_dir)}
{_product_panel(run_dir, manifest)}
{scene_sections}
{_summary_panel(images_dir)}
<div class="lightbox" id="lightbox" aria-hidden="true">
  <button type="button" id="close-lightbox" aria-label="Close">x</button>
  <img id="lightbox-img" alt="" />
  <div class="caption" id="lightbox-caption"></div>
</div>
<script>
(function() {{
  const box = document.getElementById('lightbox');
  const img = document.getElementById('lightbox-img');
  const cap = document.getElementById('lightbox-caption');
  function openLightbox(target) {{
    img.src = target.src;
    img.alt = target.alt || '';
    cap.textContent = target.dataset.caption || target.alt || '';
    box.classList.add('open');
    box.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  }}
  function closeLightbox() {{
    box.classList.remove('open');
    box.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
  }}
  document.querySelectorAll('img.zoomable').forEach(el => {{
    el.addEventListener('click', event => {{
      event.preventDefault();
      openLightbox(el);
    }});
  }});
  document.getElementById('close-lightbox').addEventListener('click', closeLightbox);
  box.addEventListener('click', event => {{
    if (event.target === box) closeLightbox();
  }});
  document.addEventListener('keydown', event => {{
    if (event.key === 'Escape') closeLightbox();
  }});
}})();
</script>
</body>
</html>
"""
    out = run_dir / "full_gallery.html"
    out.write_text(html_doc, encoding="utf-8")
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Build full input/output gallery for a run directory.")
    parser.add_argument("--run-dir", required=True, help="Campaign run directory.")
    parser.add_argument("--open", action="store_true", help="Open the generated HTML in the default browser.")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        print(f"[ERROR] not a directory: {run_dir}", file=sys.stderr)
        return 1
    out = render(run_dir)
    print(f"[OK] full gallery: {out}")
    if args.open:
        webbrowser.open(out.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
