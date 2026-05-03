"""Filter classified images by Duvetica target categories: Woven Jacket / Setup (zip-up + shorts)"""

import json
from pathlib import Path

report_path = Path(
    "db/strategy-cut-builder/trend-images/_classified/duvetica/classification_report.json"
)
with open(report_path, encoding="utf-8") as f:
    data = json.load(f)

jacket_keywords = [
    "jacket",
    "blazer",
    "coat",
    "windbreaker",
    "anorak",
    "parka",
    "bomber",
]
setup_keywords = ["zip", "shorts", "romper", "set", "tracksuit", "hoodie"]

woven_jackets = []
setups = []
others = []

for item in data["results"]:
    gt = item["garment_type"].lower()
    file = item["file"]
    grade = item["grade"]

    is_jacket = any(kw in gt for kw in jacket_keywords)
    is_setup = any(kw in gt for kw in setup_keywords)

    entry = {
        "file": file,
        "grade": grade,
        "garment_type": item["garment_type"],
        "color": item["color_description"],
        "mood": item["overall_mood"],
        "fabric": item["fabric"],
        "fit": item["fit"],
        "sheen": item["sheen"],
        "weight": item["weight"],
        "lifestyle": item["lifestyle"],
        "outside": [f"{a[0]}={a[1]}" for a in item.get("outside_guardrail", [])],
        "far_outside": [
            f"{a[0]}={a[1]}" for a in item.get("far_outside_guardrail", [])
        ],
    }

    if is_jacket:
        woven_jackets.append(entry)
    elif is_setup:
        setups.append(entry)
    else:
        others.append(entry)

print("=" * 80)
print(f"WOVEN JACKET candidates: {len(woven_jackets)}")
print("=" * 80)
for i, j in enumerate(woven_jackets, 1):
    adj = (
        ", ".join(j["outside"] + j["far_outside"])
        if (j["outside"] or j["far_outside"])
        else "none"
    )
    print(f"  {i}. [{j['grade']}] {j['file']} - {j['garment_type']}")
    print(f"     Color: {j['color']} | Mood: {j['mood']}")
    print(
        f"     Attrs: fabric={j['fabric']} fit={j['fit']} sheen={j['sheen']} weight={j['weight']} life={j['lifestyle']}"
    )
    print(f"     Adjustments: {adj}")

print()
print("=" * 80)
print(f"SETUP (zip-up/shorts) candidates: {len(setups)}")
print("=" * 80)
for i, s in enumerate(setups, 1):
    adj = (
        ", ".join(s["outside"] + s["far_outside"])
        if (s["outside"] or s["far_outside"])
        else "none"
    )
    print(f"  {i}. [{s['grade']}] {s['file']} - {s['garment_type']}")
    print(f"     Color: {s['color']} | Mood: {s['mood']}")
    print(
        f"     Attrs: fabric={s['fabric']} fit={s['fit']} sheen={s['sheen']} weight={s['weight']} life={s['lifestyle']}"
    )
    print(f"     Adjustments: {adj}")

print()
print("=" * 80)
print(f"OTHER (not target category): {len(others)}")
print("=" * 80)
for i, o in enumerate(others, 1):
    print(f"  {i}. [{o['grade']}] {o['file']} - {o['garment_type']}")
