"""Download HF generation results into 03_images/{unit_id}_hf_{model}.png.

Usage: python _dv_hf_download.py <urls_json>
where urls_json maps unit_label (e.g. 'S01_R01_gpt') -> rawUrl.
"""
import sys
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

sys.stdout.reconfigure(encoding="utf-8")

IMGS_DIR = Path(sys.argv[2] if len(sys.argv) > 2 else "st_cut-dev/results/dv/imc_driven/20260503_DV_27SS_20260503_231654/03_images")

MODEL_SUFFIX = {
    "gpt": "hf_gpt",
    "nano": "hf_nano",
    "mkt": "hf_mkt",
}


def download_one(label, url):
    # label like "S01_R01_gpt" → unit_id="S01_R01...", model_key="gpt"
    parts = label.rsplit("_", 1)
    base_unit = parts[0]
    model_key = parts[1]
    suffix = MODEL_SUFFIX[model_key]

    # Resolve full unit_id from any *_prompt.txt in the dir matching base_unit
    candidates = list(IMGS_DIR.glob(f"{base_unit.split('_R')[0]}_*_R{base_unit.split('_R')[1]}_prompt.txt"))
    if not candidates:
        # Fallback: match by R suffix
        rank = base_unit.split("_R")[1]
        scene_prefix = base_unit.split("_R")[0]
        candidates = [p for p in IMGS_DIR.glob("*_prompt.txt")
                      if p.name.startswith(scene_prefix) and f"_R{rank}_prompt.txt" in p.name]
    if not candidates:
        return (label, "no_unit_id", None)

    full_unit = candidates[0].name.replace("_prompt.txt", "")
    out_path = IMGS_DIR / f"{full_unit}_{suffix}.png"
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        out_path.write_bytes(r.content)
        return (label, "ok", str(out_path))
    except Exception as e:
        return (label, f"fail: {type(e).__name__}: {e}", None)


def main():
    urls = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    results = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(download_one, lbl, url)
                for lbl, url in urls.items() if url]
        for fu in as_completed(futs):
            results.append(fu.result())

    ok = sum(1 for _, s, _ in results if s == "ok")
    print(f"Downloaded {ok}/{len(results)}")
    for lbl, s, p in results:
        if s != "ok":
            print(f"  {lbl}: {s}")


if __name__ == "__main__":
    main()
