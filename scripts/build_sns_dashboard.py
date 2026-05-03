"""Build a single self-contained, filterable HTML dashboard from sns-influencer-output.

Reads:
    source/sns-influencer-output/{brand}/labels_raw/*.json
    source/sns-influencer-output/{brand}/**/*.jpg|.png|.webp     # any image with stem == post_id

Writes:
    st_cut-dev/results/sns_dashboard.html

Design:
- Vanilla JS, no CDN — opens fully offline.
- Posts JSON is inlined into the HTML via <script type="application/json">.
- Image src uses relative path to local files (works when browser opens HTML directly).
- Filter UI (top sticky): brand, free-text search, confidence min, multi-select chips
  for cat/fashion_style/color_tone/coordination/gender/age_group/pose/location/mood.
- Card grid lazy-loads images (loading="lazy"). Pagination 60/page.
"""
from __future__ import annotations

import html
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "source" / "sns-influencer-output"
OUT_HTML = PROJECT_ROOT / "st_cut-dev" / "results" / "sns_dashboard.html"

IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
BRANDS = ("DV", "DX", "MLB")


def _index_images(brand_dir: Path) -> dict[str, str]:
    """Return {post_id: relative_path_from_OUT_HTML_dir} using the FIRST image found."""
    out: dict[str, str] = {}
    for dp, _, fs in os.walk(brand_dir):
        for f in fs:
            stem, ext = os.path.splitext(f)
            if ext.lower() not in IMG_EXTS:
                continue
            if stem in out:
                continue
            full = Path(dp) / f
            try:
                rel = os.path.relpath(full, OUT_HTML.parent).replace("\\", "/")
            except ValueError:
                rel = full.as_posix()
            out[stem] = rel
    return out


def _load_brand(brand: str) -> tuple[list[dict], dict[str, str]]:
    brand_dir = SRC_ROOT / brand
    labels_dir = brand_dir / "labels_raw"
    img_idx = _index_images(brand_dir)

    posts: list[dict] = []
    for fname in sorted(os.listdir(labels_dir)):
        if not fname.endswith(".json") or fname.startswith("_"):
            continue
        try:
            rec = json.loads((labels_dir / fname).read_text(encoding="utf-8"))
        except Exception:
            continue
        post_id = rec.get("post_id") or os.path.splitext(fname)[0]
        label = rec.get("label") or {}
        person = label.get("person") or {}
        bg = label.get("background") or {}
        st = label.get("styling") or {}
        items_in = label.get("items") or []
        items_out = []
        cats_set = []
        seen_cats = set()
        for it in items_in:
            cat = it.get("cat")
            if cat and cat not in seen_cats:
                cats_set.append(cat)
                seen_cats.add(cat)
            ad = it.get("additional_details") or []
            items_out.append({
                "cat": cat,
                "sub_cat": it.get("sub_cat"),
                "color": it.get("color"),
                "fabrication": it.get("fabrication"),
                "material": it.get("material"),
                "pattern": it.get("pattern"),
                "silhouette_or_length": it.get("silhouette_or_length"),
                "details": ad if isinstance(ad, list) else [],
            })
        posts.append({
            "brand": brand,
            "post_id": post_id,
            "handle": rec.get("handle"),
            "post_url": rec.get("post_url"),
            "model": rec.get("model"),
            "labeled_at": rec.get("labeled_at"),
            "image": img_idx.get(post_id),
            "person": {
                "gender": person.get("gender"),
                "age_group": person.get("age_group"),
                "number_of_people": person.get("number_of_people"),
                "pose": person.get("pose"),
                "expression": person.get("expression"),
            },
            "background": {
                "location": bg.get("location"),
                "mood": bg.get("mood"),
                "season_weather": bg.get("season_weather"),
            },
            "styling": {
                "fashion_style": st.get("fashion_style"),
                "overall_color_tone": st.get("overall_color_tone"),
                "coordination_method": st.get("coordination_method"),
            },
            "confidence": label.get("confidence"),
            "notes": (label.get("notes") or "")[:1200],
            "cats": cats_set,
            "items": items_out,
        })
    return posts, img_idx


def _collect_facets(posts: list[dict]) -> dict[str, list[str]]:
    """Return facet -> sorted unique values (only from non-null)."""
    facets = defaultdict(Counter)
    for p in posts:
        for it in p["items"]:
            if it["cat"]:
                facets["cat"][it["cat"]] += 1
        for k in ("fashion_style", "overall_color_tone", "coordination_method"):
            v = p["styling"].get(k)
            if v:
                facets[k][v] += 1
        for k in ("gender", "age_group", "pose", "expression"):
            v = p["person"].get(k)
            if v:
                facets[k][v] += 1
        for k in ("location", "mood"):
            v = p["background"].get(k)
            if v:
                facets[k][v] += 1
    return {k: [v for v, _ in c.most_common()] for k, c in facets.items()}


HTML_TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<title>F&F SNS 라벨링 대시보드</title>
<style>
:root {
  --bg: #0f1115; --panel: #181c24; --panel2: #1f242e; --line: #2a3140;
  --text: #e7eaf0; --dim: #98a0ad; --accent: #7cc4ff; --warn: #ffb86b; --ok: #7ee787;
}
* { box-sizing: border-box; }
html, body { margin:0; background: var(--bg); color: var(--text); font-family: -apple-system, "Segoe UI", Roboto, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif; }
header { position: sticky; top:0; z-index: 5; background: var(--panel); border-bottom: 1px solid var(--line); padding: 12px 16px; }
.title { display:flex; align-items: baseline; gap:12px; flex-wrap: wrap; }
.title h1 { margin:0; font-size: 18px; }
.count { color: var(--dim); font-size: 13px; }
.controls { margin-top: 10px; display:grid; gap:8px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
.row { display:flex; gap:6px; flex-wrap: wrap; align-items: center; font-size:12px; }
.row label { color: var(--dim); margin-right:4px; }
.chip { background: var(--panel2); border:1px solid var(--line); color: var(--text); padding: 3px 8px; border-radius: 999px; font-size: 12px; cursor: pointer; user-select: none; white-space: nowrap; }
.chip.on { background: var(--accent); color:#0b1320; border-color: var(--accent); font-weight: 600; }
.chip .n { color: var(--dim); margin-left: 4px; font-weight: 400; }
.chip.on .n { color: #0b1320; }
input[type=text], input[type=number], select {
  background: var(--panel2); color: var(--text); border:1px solid var(--line); border-radius:6px; padding:6px 8px; font-size: 13px;
}
input[type=text] { min-width: 220px; }
input[type=range] { vertical-align: middle; }
button.btn { background: var(--panel2); color: var(--text); border:1px solid var(--line); border-radius:6px; padding:6px 10px; font-size:12px; cursor:pointer; }
button.btn:hover { border-color: var(--accent); }
details > summary { cursor:pointer; color: var(--dim); font-size:12px; }
details[open] > summary { color: var(--text); }
main { padding: 12px 16px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; overflow:hidden; display:flex; flex-direction: column; }
.card .img-wrap { width:100%; aspect-ratio: 1/1; background: #000; display:flex; align-items: center; justify-content: center; }
.card .img-wrap img { width:100%; height:100%; object-fit: cover; }
.card .img-wrap .missing { color: var(--dim); font-size: 12px; padding: 8px; text-align:center; }
.card .meta { padding: 8px 10px; font-size: 12px; line-height: 1.45; }
.card .meta .top { display:flex; justify-content: space-between; gap:6px; align-items:center; }
.card .meta .brand { font-weight: 700; }
.card .meta .handle { color: var(--accent); text-decoration: none; }
.card .meta .conf { color: var(--ok); font-variant-numeric: tabular-nums; }
.card .meta .conf.low { color: var(--warn); }
.tags { display:flex; flex-wrap: wrap; gap:4px; margin-top:6px; }
.tag { background: var(--panel2); border:1px solid var(--line); padding: 1px 6px; border-radius:6px; font-size:11px; color: var(--dim); }
.tag.cat   { color: #cfe6ff; }
.tag.style { color: #ffd68a; }
.tag.tone  { color: #cdb4ff; }
.tag.loc   { color: #b6f1c2; }
.tag.mood  { color: #ffb6c8; }
.items-list { margin-top: 6px; padding-left: 0; list-style:none; max-height: 0; overflow:hidden; transition: max-height .15s ease; }
.card.expanded .items-list { max-height: 800px; }
.items-list li { border-top: 1px dashed var(--line); padding: 4px 0; }
.items-list .it-head { font-weight: 600; }
.items-list .it-meta { color: var(--dim); }
.notes { margin-top:6px; color: var(--dim); font-size: 11px; max-height: 0; overflow:hidden; transition: max-height .15s ease; }
.card.expanded .notes { max-height: 600px; }
.pager { margin: 16px auto; display:flex; gap:8px; justify-content: center; align-items: center; flex-wrap: wrap; }
.pager .pinfo { color: var(--dim); font-size: 12px; }
.no-img { background: linear-gradient(135deg,#222,#111); }
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: #2a3140; border-radius: 5px; }
</style>
</head>
<body>
<header>
  <div class="title">
    <h1>F&F SNS 라벨링 대시보드</h1>
    <span class="count" id="count"></span>
  </div>
  <div class="controls">
    <div class="row" id="brand-row"><label>브랜드</label></div>
    <div class="row">
      <label>검색</label>
      <input type="text" id="q" placeholder="handle, post_id, sub_cat, notes…"/>
      <button class="btn" id="reset">필터 초기화</button>
    </div>
    <div class="row">
      <label>최소 confidence</label>
      <input type="range" id="conf" min="0" max="1" step="0.01" value="0"/>
      <span id="conf-val" style="color:var(--dim);width:34px;display:inline-block">0.00</span>
    </div>
  </div>
  <details style="margin-top:8px">
    <summary>필터 더보기 (cat / fashion_style / color_tone / coordination / gender / age_group / pose / location / mood)</summary>
    <div class="controls" id="facet-rows"></div>
  </details>
</header>
<main>
  <div id="grid" class="grid"></div>
  <div class="pager" id="pager"></div>
</main>

<script type="application/json" id="data">__DATA_JSON__</script>
<script type="application/json" id="facets">__FACETS_JSON__</script>

<script>
const POSTS = JSON.parse(document.getElementById('data').textContent);
const FACETS = JSON.parse(document.getElementById('facets').textContent);
const BRANDS = [...new Set(POSTS.map(p => p.brand))];
const PAGE_SIZE = 60;
const FACET_KEYS = ['cat','fashion_style','overall_color_tone','coordination_method','gender','age_group','pose','location','mood'];

const state = {
  brand: new Set(BRANDS),
  facet: Object.fromEntries(FACET_KEYS.map(k => [k, new Set()])),
  q: '',
  confMin: 0,
  page: 0,
};

function el(tag, attrs={}, children=[]) {
  const e = document.createElement(tag);
  for (const [k,v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v;
    else if (k === 'html') e.innerHTML = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  for (const c of (Array.isArray(children) ? children : [children])) {
    if (c == null) continue;
    e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  }
  return e;
}

function buildBrandRow() {
  const row = document.getElementById('brand-row');
  for (const b of BRANDS) {
    const n = POSTS.filter(p => p.brand === b).length;
    const c = el('span', { class: 'chip on', 'data-brand': b },
      [b, el('span', { class: 'n' }, ` ${n}`)]);
    c.addEventListener('click', () => {
      if (state.brand.has(b)) state.brand.delete(b); else state.brand.add(b);
      c.classList.toggle('on', state.brand.has(b));
      state.page = 0; render();
    });
    row.appendChild(c);
  }
}

function buildFacetRows() {
  const root = document.getElementById('facet-rows');
  for (const key of FACET_KEYS) {
    const values = FACETS[key] || [];
    if (!values.length) continue;
    const row = el('div', { class: 'row' });
    row.appendChild(el('label', {}, key));
    for (const v of values.slice(0, 30)) {
      const chip = el('span', { class: 'chip', 'data-facet': key, 'data-val': v }, v);
      chip.addEventListener('click', () => {
        const set = state.facet[key];
        if (set.has(v)) set.delete(v); else set.add(v);
        chip.classList.toggle('on', set.has(v));
        state.page = 0; render();
      });
      row.appendChild(chip);
    }
    if (values.length > 30) {
      row.appendChild(el('span', { class: 'tag' }, `+${values.length - 30} more (use search)`));
    }
    root.appendChild(row);
  }
}

function passesFacet(p) {
  for (const key of FACET_KEYS) {
    const sel = state.facet[key];
    if (!sel.size) continue;
    let vals = [];
    if (key === 'cat') vals = p.cats || [];
    else if (['fashion_style','overall_color_tone','coordination_method'].includes(key)) vals = [p.styling[key]];
    else if (['gender','age_group','pose'].includes(key)) vals = [p.person[key]];
    else if (['location','mood'].includes(key)) vals = [p.background[key]];
    if (!vals.some(v => sel.has(v))) return false;
  }
  return true;
}

function passesSearch(p, q) {
  if (!q) return true;
  const hay = [
    p.handle, p.post_id, p.notes,
    p.styling.fashion_style, p.background.location, p.background.mood,
    p.person.pose, p.person.expression,
    ...p.cats,
    ...p.items.flatMap(i => [i.cat, i.sub_cat, i.color, i.fabrication, i.material, i.pattern, i.silhouette_or_length, ...(i.details||[])])
  ].filter(Boolean).join(' · ').toLowerCase();
  return hay.includes(q);
}

function filtered() {
  const q = state.q.trim().toLowerCase();
  return POSTS.filter(p =>
    state.brand.has(p.brand)
    && (p.confidence == null ? state.confMin === 0 : p.confidence >= state.confMin)
    && passesFacet(p)
    && passesSearch(p, q)
  );
}

function tag(text, cls='') { return el('span', { class: 'tag '+cls }, text); }

function makeCard(p) {
  const conf = p.confidence == null ? '' : (p.confidence).toFixed(2);
  const card = el('div', { class: 'card' });
  // image
  const wrap = el('div', { class: 'img-wrap' + (p.image ? '' : ' no-img') });
  if (p.image) {
    wrap.appendChild(el('img', { src: p.image, loading: 'lazy', alt: p.post_id }));
  } else {
    wrap.appendChild(el('div', { class: 'missing' }, '(이미지 없음)'));
  }
  card.appendChild(wrap);

  // meta
  const meta = el('div', { class: 'meta' });
  const top = el('div', { class: 'top' });
  top.appendChild(el('span', { class: 'brand' }, p.brand));
  top.appendChild(el('a', { class: 'handle', href: p.post_url || '#', target: '_blank', rel: 'noreferrer' },
                       p.handle ? '@'+p.handle : (p.post_id || '')));
  if (conf) {
    const cls = (p.confidence < 0.7) ? 'conf low' : 'conf';
    top.appendChild(el('span', { class: cls }, conf));
  }
  meta.appendChild(top);

  const tags = el('div', { class: 'tags' });
  for (const c of (p.cats||[]).slice(0, 6)) tags.appendChild(tag(c, 'cat'));
  if (p.styling.fashion_style)   tags.appendChild(tag('스타일: ' + p.styling.fashion_style, 'style'));
  if (p.styling.overall_color_tone) tags.appendChild(tag('톤: ' + p.styling.overall_color_tone, 'tone'));
  if (p.background.location)     tags.appendChild(tag('장소: ' + p.background.location, 'loc'));
  if (p.background.mood)         tags.appendChild(tag('무드: ' + p.background.mood, 'mood'));
  meta.appendChild(tags);

  // expandable items list
  const list = el('ul', { class: 'items-list' });
  for (const it of p.items) {
    const li = el('li');
    li.appendChild(el('div', { class: 'it-head' },
      [it.cat || '?', el('span', { class: 'tag', style: 'margin-left:4px' }, it.sub_cat || '?')]));
    const m = [];
    if (it.color) m.push('color: '+it.color);
    if (it.fabrication) m.push('fab: '+it.fabrication);
    if (it.material) m.push('mat: '+it.material);
    if (it.pattern) m.push('pat: '+it.pattern);
    if (it.silhouette_or_length) m.push('silh: '+it.silhouette_or_length);
    if (m.length) li.appendChild(el('div', { class: 'it-meta' }, m.join(' · ')));
    if ((it.details||[]).length) li.appendChild(el('div', { class: 'it-meta' }, 'details: ' + it.details.join(', ')));
    list.appendChild(li);
  }
  meta.appendChild(list);

  if (p.notes) {
    meta.appendChild(el('div', { class: 'notes' }, '📝 ' + p.notes));
  }

  card.addEventListener('click', (e) => {
    if (e.target.tagName === 'A') return;
    card.classList.toggle('expanded');
  });
  card.appendChild(meta);
  return card;
}

function render() {
  const data = filtered();
  document.getElementById('count').textContent =
    `필터링: ${data.length.toLocaleString()} / 전체 ${POSTS.length.toLocaleString()} posts`;
  const grid = document.getElementById('grid');
  grid.innerHTML = '';
  const start = state.page * PAGE_SIZE;
  const end = Math.min(start + PAGE_SIZE, data.length);
  for (let i = start; i < end; i++) grid.appendChild(makeCard(data[i]));

  const pager = document.getElementById('pager');
  pager.innerHTML = '';
  const total = Math.max(1, Math.ceil(data.length / PAGE_SIZE));
  const pinfo = el('span', { class: 'pinfo' }, `Page ${state.page+1} / ${total}  (${start+1}–${end})`);
  const prev = el('button', { class: 'btn' }, '◀ Prev');
  const next = el('button', { class: 'btn' }, 'Next ▶');
  prev.disabled = state.page === 0;
  next.disabled = (state.page+1) >= total;
  prev.addEventListener('click', () => { state.page--; render(); window.scrollTo(0,0); });
  next.addEventListener('click', () => { state.page++; render(); window.scrollTo(0,0); });
  pager.append(prev, pinfo, next);
}

document.getElementById('q').addEventListener('input', (e) => {
  state.q = e.target.value; state.page = 0; render();
});
document.getElementById('conf').addEventListener('input', (e) => {
  state.confMin = parseFloat(e.target.value);
  document.getElementById('conf-val').textContent = state.confMin.toFixed(2);
  state.page = 0; render();
});
document.getElementById('reset').addEventListener('click', () => {
  state.q = '';
  document.getElementById('q').value = '';
  state.confMin = 0;
  document.getElementById('conf').value = 0;
  document.getElementById('conf-val').textContent = '0.00';
  for (const k of FACET_KEYS) state.facet[k].clear();
  document.querySelectorAll('.chip[data-facet]').forEach(c => c.classList.remove('on'));
  state.brand = new Set(BRANDS);
  document.querySelectorAll('.chip[data-brand]').forEach(c => c.classList.add('on'));
  state.page = 0; render();
});

buildBrandRow();
buildFacetRows();
render();
</script>
</body>
</html>
"""


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if not SRC_ROOT.is_dir():
        print(f"[ERROR] Not found: {SRC_ROOT}", file=sys.stderr)
        return 1

    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)

    all_posts: list[dict] = []
    for brand in BRANDS:
        bp = SRC_ROOT / brand
        if not bp.is_dir():
            print(f"[skip] {bp} not found")
            continue
        posts, _ = _load_brand(brand)
        miss = sum(1 for p in posts if not p["image"])
        print(f"  {brand}: {len(posts)} posts, missing image = {miss}")
        all_posts.extend(posts)

    facets = _collect_facets(all_posts)

    data_json = json.dumps(all_posts, ensure_ascii=False, separators=(",", ":"))
    facets_json = json.dumps(facets, ensure_ascii=False, separators=(",", ":"))

    html_text = (
        HTML_TEMPLATE
        .replace("__DATA_JSON__", data_json)
        .replace("__FACETS_JSON__", facets_json)
    )

    OUT_HTML.write_text(html_text, encoding="utf-8")
    size_mb = OUT_HTML.stat().st_size / (1024 * 1024)
    print(f"\n[OK] wrote {OUT_HTML}  ({size_mb:.1f} MB, {len(all_posts):,} posts)")
    print(f"     open file:///{OUT_HTML.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
