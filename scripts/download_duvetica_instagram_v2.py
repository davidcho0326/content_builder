# WORKFLOW_BYPASS_OK: strategy-cut-builder data collection (2026-04-30)
"""Download Duvetica Korea Instagram images - FULL RESOLUTION (not og:image square crop)

Parses post page HTML for display_url / display_resources to get original aspect ratio.

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/download_duvetica_instagram_v2.py
"""

import json
import re
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "db" / "strategy-cut-builder" / "duvetica" / "instagram"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

POST_CODES = [
    "DXYGg7WETSS",
    "DXYF9BAETZs",
    "DXYFX0bkWFw",
    "DXv61kvEVHX",
    "DXv6Qd9kXFE",
    "DXv5xcQkdLl",
    "DXqxSrqERLB",
    "DXqwtpvkSVz",
    "DXqwHXmEezi",
    "DXdPixyCcF8",
    "DXdO7UDj-98",
    "DXLMyMUCcBK",
    "DXLMNX-Ccwq",
    "DXGDwtCkarB",
    "DXGDM4skWI0",
    "DXGCqRNkVc9",
    "DW0rHxPERxp",
    "DW0rA9akfYv",
    "DW0q1HQEbuF",
    "DWipps-kaEt",
    "DWipjFhEU5v",
    "DWipVWBEaEE",
    "DWVIRAviUap",
    "DWVIJlhiUEZ",
    "DWP-ru6CT2x",
    "DWP-mDPCa0k",
    "DWP-gOsif5i",
    "DV-miEGk2kj",
    "DV-mWoOE3op",
    "DV-mIQKk1tm",
    "DVuYuMQEzs7",
    "DVuYfQbEzjv",
    "DVuYSuaEy-j",
    "DVZ6AkhkoWt",
    "DVZ58fLks_c",
    "DVZ55xcEl_u",
    "DVH4WKzidTl",
    "DVH4QLSCZWh",
    "DU-OfSyEfHc",
    "DU-OaNGkTkO",
    "DU7poT4kQyP",
    "DU7pgg0kSoY",
    "DU7pZ-bkUma",
    "DUrjs31CbPI",
    "DUrjlvMCZX8",
    "DUrjaNSibM1",
    "DUmaFvHEtrI",
    "DUmaBEMElWI",
    "DUmZ7ycEmJd",
    "DUW93tQiRVg",
    "DUW9xRWiUJL",
    "DURzsYdCSrK",
    "DURzoBEiSi8",
    "DURzjvgCf73",
]

session = requests.Session()
session.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    }
)


def download_post(shortcode: str, idx: int) -> dict:
    """Download full-res images from a single Instagram post."""
    result = {"shortcode": shortcode, "idx": idx, "images": [], "method": ""}

    post_url = f"https://www.instagram.com/p/{shortcode}/"

    try:
        resp = session.get(post_url, timeout=20)
        if resp.status_code != 200:
            print(f"  [{idx:02d}] {shortcode}: HTTP {resp.status_code}")
            return result

        html = resp.text

        # Method 1: display_url from embedded JSON (highest quality, original aspect)
        display_urls = re.findall(r'"display_url"\s*:\s*"([^"]+)"', html)
        if display_urls:
            for i, raw_url in enumerate(display_urls):
                img_url = raw_url.replace("\\u0026", "&").replace("\\", "")
                filename = f"insta_{idx:03d}_{shortcode}_{i+1}.jpg"
                save_path = OUTPUT_DIR / filename
                if _download_img(img_url, save_path):
                    result["images"].append(filename)
            if result["images"]:
                result["method"] = "display_url"
                print(
                    f"  [{idx:02d}] {shortcode}: {len(result['images'])} imgs (display_url)"
                )
                return result

        # Method 2: display_resources (multiple resolutions, pick largest)
        resource_blocks = re.findall(
            r'"display_resources"\s*:\s*\[(.*?)\]', html, re.DOTALL
        )
        if resource_blocks:
            for block in resource_blocks:
                urls_with_size = re.findall(
                    r'"src"\s*:\s*"([^"]+)".*?"config_width"\s*:\s*(\d+)', block
                )
                if urls_with_size:
                    best = max(urls_with_size, key=lambda x: int(x[1]))
                    img_url = best[0].replace("\\u0026", "&").replace("\\", "")
                    filename = (
                        f"insta_{idx:03d}_{shortcode}_{len(result['images'])+1}.jpg"
                    )
                    save_path = OUTPUT_DIR / filename
                    if _download_img(img_url, save_path):
                        result["images"].append(filename)
            if result["images"]:
                result["method"] = "display_resources"
                print(
                    f"  [{idx:02d}] {shortcode}: {len(result['images'])} imgs (resources)"
                )
                return result

        # Method 3: largest image URL from any pattern
        all_img_urls = re.findall(r'"(https://scontent[^"]+)"', html)
        if not all_img_urls:
            all_img_urls = re.findall(r'"(https://instagram[^"]+\.jpg[^"]*)"', html)

        seen = set()
        for raw_url in all_img_urls:
            img_url = raw_url.replace("\\u0026", "&").replace("\\", "")
            base = img_url.split("?")[0]
            if base in seen:
                continue
            seen.add(base)
            filename = f"insta_{idx:03d}_{shortcode}_{len(result['images'])+1}.jpg"
            save_path = OUTPUT_DIR / filename
            if _download_img(img_url, save_path):
                result["images"].append(filename)
                if len(result["images"]) >= 5:
                    break

        if result["images"]:
            result["method"] = "regex_fallback"
            print(f"  [{idx:02d}] {shortcode}: {len(result['images'])} imgs (regex)")
            return result

        # Method 4: og:image fallback (square but better than nothing)
        og_match = re.search(r'property="og:image"\s+content="([^"]+)"', html)
        if og_match:
            img_url = og_match.group(1).replace("&amp;", "&")
            filename = f"insta_{idx:03d}_{shortcode}.jpg"
            save_path = OUTPUT_DIR / filename
            if _download_img(img_url, save_path):
                result["images"].append(filename)
                result["method"] = "og:image_fallback"
                print(f"  [{idx:02d}] {shortcode}: 1 img (og:image fallback - square)")
                return result

        print(f"  [{idx:02d}] {shortcode}: FAILED")

    except Exception as e:
        print(f"  [{idx:02d}] {shortcode}: ERROR {e}")

    return result


def _download_img(url: str, save_path: Path) -> bool:
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code == 200 and len(resp.content) > 2000:
            save_path.write_bytes(resp.content)
            return True
    except Exception:
        pass
    return False


def main():
    # Clean old square images first
    old_files = list(OUTPUT_DIR.glob("insta_*.jpg"))
    if old_files:
        print(f"Removing {len(old_files)} old square images...")
        for f in old_files:
            f.unlink()

    print(f"{'=' * 60}")
    print(f"DUVETICA Instagram v2 (Full Resolution)")
    print(f"Posts: {len(POST_CODES)}")
    print(f"{'=' * 60}")

    results = []
    for idx, code in enumerate(POST_CODES, 1):
        r = download_post(code, idx)
        results.append(r)
        time.sleep(1.5)

    total_imgs = sum(len(r["images"]) for r in results)
    methods = {}
    for r in results:
        m = r.get("method", "failed")
        methods[m] = methods.get(m, 0) + 1

    # Check dimensions of first few images
    from PIL import Image as PILImage

    sizes = []
    for f in sorted(OUTPUT_DIR.glob("insta_001_*.jpg"))[:3]:
        img = PILImage.open(f)
        sizes.append(f"{f.name}: {img.size[0]}x{img.size[1]}")

    manifest_path = OUTPUT_DIR / "manifest_v2.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"DONE - {total_imgs} images from {len(POST_CODES)} posts")
    print(f"Methods: {json.dumps(methods)}")
    print(f"Sample sizes: {sizes}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
