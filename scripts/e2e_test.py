# WORKFLOW_BYPASS_OK: strategy-cut-builder E2E test (2026-05-01)
"""End-to-end pipeline verification — checks all steps work as defined in skills/agent"""

import sys
import json
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
PROJECT = Path(__file__).resolve().parents[2]

errors = []

print("=" * 60)
print("E2E PIPELINE TEST")
print("=" * 60)

# STEP 1: Crawling data exists
print("\n[STEP 1] /crawl")
site_dir = PROJECT / "db" / "strategy-cut-builder" / "duvetica" / "official-site"
insta_dir = PROJECT / "db" / "strategy-cut-builder" / "duvetica" / "instagram"
site_n = (
    len(list(site_dir.rglob("*.jpg"))) + len(list(site_dir.rglob("*.png")))
    if site_dir.exists()
    else 0
)
insta_n = len(list(insta_dir.glob("*.jpg"))) if insta_dir.exists() else 0
print(f"  site={site_n} insta={insta_n}")
for s in [
    "crawl_duvetica.py",
    "download_duvetica.py",
    "download_duvetica_instagram.py",
]:
    ok = (PROJECT / "scripts" / "strategy_cut_builder" / s).exists()
    print(f"  {s}: {'OK' if ok else 'MISSING'}")
    if not ok:
        errors.append(f"S1: {s} missing")
if site_n == 0:
    errors.append("S1: no site images")
s1 = "PASS" if not any("S1" in e for e in errors) else "FAIL"
print(f"  -> {s1}")

# STEP 2: DNA analysis
print("\n[STEP 2] /dna-extract")
dna_path = (
    PROJECT
    / ".claude"
    / "projects"
    / "strategy-cut-builder"
    / "brand-dna"
    / "duvetica.json"
)
if dna_path.exists():
    dna = json.loads(dna_path.read_text(encoding="utf-8"))
    req = [
        "brand",
        "season",
        "positioning",
        "mood",
        "color",
        "setting",
        "styling",
        "model",
        "fabric",
        "data_driven_guardrails",
        "marketing_dna",
    ]
    missing = [f for f in req if f not in dna]
    print(f"  DNA fields: {len(req)-len(missing)}/{len(req)}")
    if missing:
        print(f"  MISSING: {missing}")
        errors.append(f"S2: fields {missing}")
    for cat in ["woven_jacket", "setup"]:
        attrs = dna.get("data_driven_guardrails", {}).get(cat, {}).get("attributes", {})
        ok = all(
            k in attrs and "min" in attrs[k] and "max" in attrs[k]
            for k in ["fabric", "fit", "sheen", "weight"]
        )
        print(f"  guardrail[{cat}]: {'OK' if ok else 'FAIL'}")
        if not ok:
            errors.append(f"S2: {cat} guardrail incomplete")
    md = dna.get("marketing_dna", {})
    print(
        f"  marketing: pose={'pose' in md} expr={'expression' in md} bg={'background' in md}"
    )
    schema = (PROJECT / "scripts" / "strategy_cut_builder" / "dna_schema.py").exists()
    print(f"  dna_schema.py: {'OK' if schema else 'MISSING'}")
    if not schema:
        errors.append("S2: dna_schema.py missing")
else:
    errors.append("S2: DNA file not found")
s2 = "PASS" if not any("S2" in e for e in errors) else "FAIL"
print(f"  -> {s2}")

# STEP 3: Prompt build
print("\n[STEP 3] /prompt-build")
try:
    from scripts.strategy_cut_builder.dna_to_prompt import (
        load_dna,
        build_garment_prompt,
        build_full_editorial_prompt,
        build_full_influencer_prompt,
    )

    d = load_dna("duvetica")
    ed = build_full_editorial_prompt(d, "woven_jacket", moment="test moment")
    inf = build_full_influencer_prompt(d, "setup", moment="test moment")
    checks = {
        "Hasselblad": "Hasselblad" in ed,
        "Portra": "Portra" in ed or "portra" in ed,
        "model_kw": "jawline" in ed or "cheekbones" in ed,
        "brand": "DUVETICA" in ed,
        "garment_auto": len(ed) > 500,
        "influencer": len(inf) > 300,
    }
    for k, v in checks.items():
        print(f"  {k}: {'OK' if v else 'FAIL'}")
        if not v:
            errors.append(f"S3: {k} missing in prompt")
    print(f"  editorial={len(ed)}ch influencer={len(inf)}ch")
except Exception as e:
    errors.append(f"S3: {e}")
    print(f"  ERROR: {e}")
s3 = "PASS" if not any("S3" in e for e in errors) else "FAIL"
print(f"  -> {s3}")

# STEP 4: Generation scripts
print("\n[STEP 4] /generate")
gen_files = {
    "dna_auto": "generate_duvetica_dna_auto.py",
    "ref_guided": "generate_duvetica_dna_ref_guided.py",
    "mlb_dx_tuned": "generate_mlb_dx_tuned.py",
    "dna_to_prompt": "dna_to_prompt.py",
}
for name, f in gen_files.items():
    p = PROJECT / "scripts" / "strategy_cut_builder" / f
    ok = p.exists()
    print(f"  {name}: {'OK' if ok else 'MISSING'}")
    if not ok:
        errors.append(f"S4: {f} missing")

# Check ref-guided has image input (rule #5)
rg = (
    PROJECT / "scripts" / "strategy_cut_builder" / "generate_duvetica_dna_ref_guided.py"
)
if rg.exists():
    c = rg.read_text(encoding="utf-8")
    has_ref = "_pil_to_part" in c and "REFERENCE" in c
    print(f"  ref_guided uses image ref: {'OK' if has_ref else 'FAIL'}")
    if not has_ref:
        errors.append("S4: ref_guided missing image reference")

# Check 3-model support
print(f"  Gemini: IMAGE_MODEL in core.config")
try:
    from core.config import IMAGE_MODEL

    print(f"    -> {IMAGE_MODEL}")
except:
    errors.append("S4: IMAGE_MODEL import fail")

try:
    from core.model_utils import generate_gpt_image

    print(f"  GPT: generate_gpt_image OK")
except:
    errors.append("S4: GPT import fail")

hf = list((PROJECT / ".claude" / "skills").glob("*higgsfield*"))
print(f"  Higgsfield: skill={'OK' if hf else 'MISSING'}")

# Existing results
import glob

results = glob.glob(
    str(
        PROJECT
        / "Fnf_studio_outputs"
        / "strategy-cut-builder"
        / "duvetica"
        / "**"
        / "*.png"
    ),
    recursive=True,
)
print(f"  Existing results: {len(results)} images")
s4 = "PASS" if not any("S4" in e for e in errors) else "FAIL"
print(f"  -> {s4}")

# STEP 5: Inspection
print("\n[STEP 5] /inspect")
insp = PROJECT / "scripts" / "strategy_cut_builder" / "inspect_results.py"
print(f"  inspect_results.py: {'OK' if insp.exists() else 'MISSING'}")
if insp.exists():
    c = insp.read_text(encoding="utf-8")
    print(f"  ThreadPoolExecutor: {'OK' if 'ThreadPoolExecutor' in c else 'MISSING'}")
    print(f"  VISION_MODEL: {'OK' if 'VISION_MODEL' in c else 'MISSING'}")
    print(
        f"  JSON schema: {'OK' if 'schema' in c.lower() or 'INSPECT' in c else 'MISSING'}"
    )
    vals = list(
        (PROJECT / "Fnf_studio_outputs" / "strategy-cut-builder" / "duvetica").rglob(
            "validation.json"
        )
    )
    print(f"  Existing validations: {len(vals)}")
else:
    errors.append("S5: inspect_results.py missing")
s5 = "PASS" if not any("S5" in e for e in errors) else "FAIL"
print(f"  -> {s5}")

# RULES & HOOKS
print("\n[RULES & HOOKS]")
rule = PROJECT / ".claude" / "rules" / "strategy-cut-prompt.md"
hook = PROJECT / ".claude" / "hooks" / "validate_strategy_cut_dna.py"
agent = PROJECT / ".claude" / "agents" / "strategy-cut-agent.md"
for name, p in [("rule", rule), ("hook", hook), ("agent", agent)]:
    ok = p.exists()
    print(f"  {name}: {'OK' if ok else 'MISSING'}")
    if not ok:
        errors.append(f"RH: {name} missing")

if rule.exists():
    c = rule.read_text(encoding="utf-8")
    rules5 = ["JSON", "K-pop", "3", "AI", "가이드"]
    found = sum(1 for r in rules5 if r in c)
    print(f"  5 rules keywords: {found}/5")

# Skills check
print("\n[SKILLS]")
skill_names = [
    "전략컷크롤링",
    "전략컷DNA분석",
    "전략컷프롬프트",
    "전략컷생성",
    "전략컷검수",
    "힉스필드",
]
for sn in skill_names:
    dirs = list((PROJECT / ".claude" / "skills").glob(f"{sn}*"))
    ok = bool(dirs) and (dirs[0] / "SKILL.md").exists() if dirs else False
    print(f"  {sn}: {'OK' if ok else 'MISSING'}")
    if not ok:
        errors.append(f"SK: {sn} missing")
sk = "PASS" if not any("SK" in e for e in errors) else "FAIL"
rh = "PASS" if not any("RH" in e for e in errors) else "FAIL"

# SUMMARY
print(f"\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")
results_map = {
    "Step 1 Crawl": s1,
    "Step 2 DNA": s2,
    "Step 3 Prompt": s3,
    "Step 4 Generate": s4,
    "Step 5 Inspect": s5,
    "Rules/Hooks": rh,
    "Skills": sk,
}
for name, status in results_map.items():
    print(f"  {'PASS' if status == 'PASS' else 'FAIL'} {name}")

total = sum(1 for v in results_map.values() if v == "PASS")
print(f"\n  {total}/{len(results_map)} PASS")
if errors:
    print(f"\n  ERRORS ({len(errors)}):")
    for e in errors:
        print(f"    - {e}")
else:
    print("\n  ALL CLEAR - Pipeline ready for production!")
