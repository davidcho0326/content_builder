"""Marketing-context dashboard — single self-contained, filterable HTML.

Reads:
    source/sns-influencer-output/labels_marketing_index.jsonl
Writes:
    st_cut-dev/results/marketing_dashboard.html

Differences vs. the earlier raw-data dashboard:
- No item-level cards (items[]/common removed at the data layer already).
- Stronger marketing-context filters grouped as: 모델 / 배경 / 스타일링.
- Each card shows brand+handle, confidence, and 3 chip-rows (model/bg/styling).
- Card click reveals notes (free-text from the labeling note field).
"""
from __future__ import annotations

import html
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_JSONL = PROJECT_ROOT / "source" / "sns-influencer-output" / "labels_marketing_index.jsonl"
OUT_HTML = PROJECT_ROOT / "st_cut-dev" / "results" / "marketing_dashboard.html"

# Filter facet groups (display label, list of (key, ko_label)).
FACETS = [
    ("모델", [
        ("gender", "성별"),
        ("age_group", "연령"),
        ("number_of_people", "인원"),
        ("pose", "포즈"),
        ("expression", "표정"),
        ("gaze_direction", "시선"),
        ("hair_style", "헤어"),
        ("skin_tone", "피부톤"),
    ]),
    ("배경", [
        ("location", "장소"),
        ("mood", "무드"),
        ("season_weather", "계절/날씨"),
        ("color_tone_filter", "색조/필터"),
        ("shooting_composition", "구도"),
    ]),
    ("스타일링", [
        ("fashion_style", "스타일"),
        ("coordination_method", "코디법"),
        ("overall_fashion_color_tone", "톤"),
    ]),
]
FACET_KEYS = [k for _, group in FACETS for k, _ in group]


def _load_records() -> list[dict]:
    """Load + flatten marketing records into card-friendly rows."""
    out: list[dict] = []
    if not SRC_JSONL.exists():
        print(f"[ERROR] missing {SRC_JSONL}", file=sys.stderr)
        sys.exit(1)
    for line in SRC_JSONL.open(encoding="utf-8"):
        rec = json.loads(line)
        a = rec.get("account") or {}
        m = rec.get("model") or {}
        bg = rec.get("background") or {}
        st = rec.get("styling") or {}
        ft = rec.get("free_text") or {}
        img = rec.get("image") or {}
        out.append({
            "brand": (a.get("brand") or "").lower(),
            "post_id": a.get("post_id"),
            "handle": a.get("handle"),
            "post_url": a.get("post_url"),
            "image": _to_rel_path(img.get("path")),
            "confidence": ft.get("_confidence"),
            "notes": (ft.get("_notes") or "")[:1500],
            "model": {
                "gender": m.get("gender"),
                "age_group": m.get("age group"),
                "number_of_people": m.get("number of people"),
                "pose": m.get("pose"),
                "expression": m.get("expression"),
                "gaze_direction": m.get("gaze direction"),
                "hair_style": m.get("hair style"),
                "skin_tone": m.get("skin tone"),
            },
            "background": {
                "location": bg.get("location"),
                "mood": bg.get("mood"),
                "season_weather": bg.get("season/weather"),
                "color_tone_filter": bg.get("color tone/filter"),
                "shooting_composition": bg.get("shooting composition"),
            },
            "styling": {
                "fashion_style": st.get("fashion style"),
                "coordination_method": st.get("coordination method"),
                "overall_fashion_color_tone": st.get("overall fashion color tone"),
            },
        })
    return out


def _to_rel_path(abs_path: str | None) -> str | None:
    if not abs_path:
        return None
    p = Path(abs_path)
    if not p.is_absolute():
        return abs_path.replace("\\", "/")
    try:
        rel = os.path.relpath(p, OUT_HTML.parent).replace("\\", "/")
        return rel
    except ValueError:
        return p.as_posix()


def _facet_counts(records: list[dict]) -> dict[str, list[tuple[str, int]]]:
    counts: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        for bin_name in ("model", "background", "styling"):
            for k, v in r[bin_name].items():
                if v:
                    counts[k][str(v)] += 1
    return {k: c.most_common() for k, c in counts.items()}


HTML_TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<title>F&F SNS 마케팅 대시보드</title>
<style>
:root {
  --bg:#0e1117; --panel:#161a22; --panel2:#1d2230; --line:#2a3140;
  --text:#e7eaf0; --dim:#98a0ad; --accent:#7cc4ff; --warn:#ffb86b; --ok:#7ee787;
  --m1:#cfe6ff; --m2:#ffd68a; --m3:#cdb4ff; --m4:#b6f1c2; --m5:#ffb6c8;
}
* { box-sizing: border-box; }
html, body { margin:0; background: var(--bg); color: var(--text);
             font-family: -apple-system, "Segoe UI", Roboto, "Apple SD Gothic Neo",
                          "Noto Sans KR", sans-serif; }
header { position: sticky; top:0; z-index:10; background: var(--panel);
         border-bottom: 1px solid var(--line); padding: 12px 16px; }
.title { display:flex; align-items: baseline; gap:12px; flex-wrap: wrap; }
.title h1 { margin:0; font-size: 17px; }
.title .sub { color: var(--dim); font-size: 12px; }
.count { color: var(--dim); font-size: 13px; }
.toprow { margin-top: 8px; display:flex; gap:8px; flex-wrap: wrap; align-items: center; }
.row { display:flex; gap:6px; flex-wrap: wrap; align-items: center; font-size:12px; }
.row > label { color: var(--dim); margin-right:2px; min-width: 56px; }
.chip { background: var(--panel2); border:1px solid var(--line); color: var(--text);
        padding: 3px 8px; border-radius: 999px; font-size: 12px; cursor: pointer;
        user-select: none; white-space: nowrap; }
.chip.on { background: var(--accent); color:#0b1320; border-color: var(--accent); font-weight: 600; }
.chip .n { color: var(--dim); margin-left: 4px; font-weight: 400; }
.chip.on .n { color: #0b1320; }
input[type=text], input[type=number], select {
  background: var(--panel2); color: var(--text); border:1px solid var(--line);
  border-radius:6px; padding:6px 8px; font-size: 13px; }
input[type=text] { min-width: 240px; }
button.btn { background: var(--panel2); color: var(--text); border:1px solid var(--line);
             border-radius:6px; padding:6px 10px; font-size:12px; cursor:pointer; }
button.btn:hover { border-color: var(--accent); }
details > summary { cursor:pointer; color: var(--dim); font-size:12px; padding: 6px 0; }
details[open] > summary { color: var(--text); }
.facet-block { margin-top: 6px; padding: 8px 10px;
               background: var(--panel2); border:1px solid var(--line); border-radius:8px; }
.facet-block .head { color: var(--dim); font-size:11px; margin-bottom: 4px;
                     letter-spacing: 0.6px; text-transform: uppercase; }
main { padding: 12px 16px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
        overflow:hidden; display:flex; flex-direction: column; cursor: pointer; }
.card .img-wrap { width:100%; aspect-ratio: 1/1; background: #000; }
.card .img-wrap img { width:100%; height:100%; object-fit: cover; }
.card .img-wrap .missing { color: var(--dim); font-size: 12px; padding: 8px; text-align:center; }
.card .meta { padding: 8px 10px; font-size: 12px; line-height: 1.45; }
.card .meta .top { display:flex; justify-content: space-between; gap:6px; align-items:center; }
.card .meta .brand { font-weight: 700; }
.card .meta .handle { color: var(--accent); text-decoration: none; }
.card .meta .conf { color: var(--ok); font-variant-numeric: tabular-nums; }
.card .meta .conf.low { color: var(--warn); }
.tags { display:flex; flex-wrap: wrap; gap:4px; margin-top:6px; }
.tag { background: var(--panel2); border:1px solid var(--line); padding: 1px 6px;
       border-radius:6px; font-size:11px; }
.tag.m1 { color: var(--m1); }   /* model */
.tag.m2 { color: var(--m2); }   /* styling */
.tag.m3 { color: var(--m3); }   /* color tone */
.tag.m4 { color: var(--m4); }   /* location */
.tag.m5 { color: var(--m5); }   /* mood */
.notes { margin-top: 6px; color: var(--dim); font-size: 11px;
         max-height: 0; overflow: hidden; transition: max-height .15s ease; }
.card.expanded .notes { max-height: 600px; }
.pager { margin: 16px auto; display:flex; gap:8px; justify-content: center;
         align-items: center; flex-wrap: wrap; }
.pager .pinfo { color: var(--dim); font-size: 12px; }
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: #2a3140; border-radius: 5px; }
</style>
</head>
<body>
<header>
  <div class="title">
    <h1>F&F SNS 마케팅 대시보드</h1>
    <span class="sub">items / common 제거된 marketing-context 전용</span>
    <span class="count" id="count"></span>
  </div>
  <div class="toprow">
    <div class="row" id="brand-row"><label>브랜드</label></div>
    <div class="row">
      <label>검색</label>
      <input type="text" id="q" placeholder="handle, post_id, notes, value…"/>
      <button class="btn" id="reset">필터 초기화</button>
    </div>
    <div class="row">
      <label>최소 신뢰도</label>
      <input type="range" id="conf" min="0" max="1" step="0.01" value="0"/>
      <span id="conf-val" style="color:var(--dim);width:34px;display:inline-block">0.00</span>
    </div>
  </div>
  <details open>
    <summary>모델 / 배경 / 스타일링 필터</summary>
    <div id="facet-root"></div>
  </details>
</header>
<main>
  <div id="grid" class="grid"></div>
  <div class="pager" id="pager"></div>
</main>

<script type="application/json" id="data">__DATA_JSON__</script>
<script type="application/json" id="facets">__FACETS_JSON__</script>
<script type="application/json" id="groups">__GROUPS_JSON__</script>

<script>
const POSTS = JSON.parse(document.getElementById('data').textContent);
const FACET_COUNTS = JSON.parse(document.getElementById('facets').textContent);
const GROUPS = JSON.parse(document.getElementById('groups').textContent);
const BRANDS = [...new Set(POSTS.map(p => p.brand))].sort();
const PAGE_SIZE = 60;
const FACET_KEYS = GROUPS.flatMap(g => g.keys.map(k => k.key));

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
      [b.toUpperCase(), el('span', { class: 'n' }, ` ${n}`)]);
    c.addEventListener('click', () => {
      if (state.brand.has(b)) state.brand.delete(b); else state.brand.add(b);
      c.classList.toggle('on', state.brand.has(b));
      state.page = 0; render();
    });
    row.appendChild(c);
  }
}

function buildFacets() {
  const root = document.getElementById('facet-root');
  for (const grp of GROUPS) {
    const block = el('div', { class: 'facet-block' });
    block.appendChild(el('div', { class: 'head' }, grp.name));
    for (const {key, label} of grp.keys) {
      const values = FACET_COUNTS[key] || [];
      if (!values.length) continue;
      const row = el('div', { class: 'row', style:'margin-top:4px' });
      row.appendChild(el('label', {}, label));
      for (const [v, n] of values.slice(0, 25)) {
        const chip = el('span', { class: 'chip', 'data-facet': key },
          [v, el('span', { class: 'n' }, ` ${n}`)]);
        chip.addEventListener('click', () => {
          const set = state.facet[key];
          if (set.has(v)) set.delete(v); else set.add(v);
          chip.classList.toggle('on', set.has(v));
          state.page = 0; render();
        });
        row.appendChild(chip);
      }
      if (values.length > 25) {
        row.appendChild(el('span', { class: 'tag' }, `+${values.length - 25} 더보기 (검색 사용)`));
      }
      block.appendChild(row);
    }
    root.appendChild(block);
  }
}

function passesFacet(p) {
  for (const key of FACET_KEYS) {
    const sel = state.facet[key];
    if (!sel.size) continue;
    let v = null;
    if (p.model[key] !== undefined) v = p.model[key];
    else if (p.background[key] !== undefined) v = p.background[key];
    else if (p.styling[key] !== undefined) v = p.styling[key];
    if (v == null || !sel.has(v)) return false;
  }
  return true;
}

function passesSearch(p, q) {
  if (!q) return true;
  const hay = [
    p.handle, p.post_id, p.notes,
    ...Object.values(p.model), ...Object.values(p.background), ...Object.values(p.styling),
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
  const card = el('div', { class: 'card' });
  const wrap = el('div', { class: 'img-wrap' });
  if (p.image) {
    wrap.appendChild(el('img', { src: p.image, loading: 'lazy', alt: p.post_id }));
  } else {
    wrap.appendChild(el('div', { class: 'missing' }, '(이미지 없음)'));
  }
  card.appendChild(wrap);

  const meta = el('div', { class: 'meta' });
  const top = el('div', { class: 'top' });
  top.appendChild(el('span', { class: 'brand' }, p.brand.toUpperCase()));
  top.appendChild(el('a', { class: 'handle', href: p.post_url || '#', target: '_blank',
                            rel: 'noreferrer' },
                       p.handle ? '@'+p.handle : (p.post_id || '')));
  if (p.confidence != null) {
    const cls = (p.confidence < 0.7) ? 'conf low' : 'conf';
    top.appendChild(el('span', { class: cls }, p.confidence.toFixed(2)));
  }
  meta.appendChild(top);

  // tag rows: model, styling, background — color-coded
  const tags = el('div', { class: 'tags' });
  if (p.model.gender) tags.appendChild(tag(p.model.gender, 'm1'));
  if (p.model.age_group) tags.appendChild(tag(p.model.age_group, 'm1'));
  if (p.model.pose) tags.appendChild(tag(p.model.pose, 'm1'));
  if (p.model.expression) tags.appendChild(tag(p.model.expression, 'm1'));
  if (p.styling.fashion_style) tags.appendChild(tag('스타일: '+p.styling.fashion_style, 'm2'));
  if (p.styling.coordination_method) tags.appendChild(tag('코디: '+p.styling.coordination_method, 'm2'));
  if (p.styling.overall_fashion_color_tone) tags.appendChild(tag('톤: '+p.styling.overall_fashion_color_tone, 'm3'));
  if (p.background.location) tags.appendChild(tag('장소: '+p.background.location, 'm4'));
  if (p.background.mood) tags.appendChild(tag('무드: '+p.background.mood, 'm5'));
  if (p.background.season_weather) tags.appendChild(tag(p.background.season_weather, 'm5'));
  meta.appendChild(tags);

  if (p.notes) meta.appendChild(el('div', { class: 'notes' }, '📝 ' + p.notes));

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
  const prev = el('button', { class: 'btn' }, '◀ 이전');
  const next = el('button', { class: 'btn' }, '다음 ▶');
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
  state.q = ''; document.getElementById('q').value = '';
  state.confMin = 0; document.getElementById('conf').value = 0;
  document.getElementById('conf-val').textContent = '0.00';
  for (const k of FACET_KEYS) state.facet[k].clear();
  document.querySelectorAll('.chip[data-facet]').forEach(c => c.classList.remove('on'));
  state.brand = new Set(BRANDS);
  document.querySelectorAll('.chip[data-brand]').forEach(c => c.classList.add('on'));
  state.page = 0; render();
});

buildBrandRow();
buildFacets();
render();
</script>
</body>
</html>
"""


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)

    posts = _load_records()
    print(f"[INFO] loaded {len(posts):,} marketing records from {SRC_JSONL.name}")

    facets = _facet_counts(posts)
    groups = [{"name": name,
               "keys": [{"key": k, "label": lab} for k, lab in keys]}
              for name, keys in FACETS]

    data_json = json.dumps(posts, ensure_ascii=False, separators=(",", ":"))
    facets_json = json.dumps(facets, ensure_ascii=False, separators=(",", ":"))
    groups_json = json.dumps(groups, ensure_ascii=False, separators=(",", ":"))

    html_text = (
        HTML_TEMPLATE
        .replace("__DATA_JSON__", data_json)
        .replace("__FACETS_JSON__", facets_json)
        .replace("__GROUPS_JSON__", groups_json)
    )
    OUT_HTML.write_text(html_text, encoding="utf-8")

    size_mb = OUT_HTML.stat().st_size / (1024 * 1024)
    print(f"[OK] wrote {OUT_HTML} ({size_mb:.1f} MB, {len(posts):,} posts)")
    print(f"     open file:///{OUT_HTML.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
