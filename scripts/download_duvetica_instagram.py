# WORKFLOW_BYPASS_OK: strategy-cut-builder data collection (2026-04-30)
"""Download Duvetica Korea Instagram images via embed/oembed API

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/download_duvetica_instagram.py
"""

import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

session = requests.Session()
session.headers.update(HEADERS)


def download_via_oembed(shortcode: str, idx: int) -> dict:
    """Try to get image via Instagram oEmbed API."""
    post_url = f"https://www.instagram.com/p/{shortcode}/"
    oembed_url = f"https://graph.facebook.com/v18.0/instagram_oembed?url={post_url}&access_token=DUMMY"

    result = {"shortcode": shortcode, "idx": idx, "images": []}

    # Method 1: Direct page fetch + og:image extraction
    try:
        resp = session.get(post_url, timeout=15)
        if resp.status_code == 200:
            html = resp.text
            # Extract og:image
            import re

            og_match = re.search(r'property="og:image"\s+content="([^"]+)"', html)
            if og_match:
                img_url = og_match.group(1).replace("&amp;", "&")
                save_path = OUTPUT_DIR / f"insta_{idx:03d}_{shortcode}.jpg"
                try:
                    img_resp = session.get(img_url, timeout=15)
                    if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                        save_path.write_bytes(img_resp.content)
                        result["images"].append(str(save_path.name))
                        print(f"  [{idx:02d}] {shortcode}: OK (og:image)")
                        return result
                except Exception:
                    pass

            # Method 2: Find image URLs in page source
            img_urls = re.findall(r'"display_url":"([^"]+)"', html)
            if not img_urls:
                img_urls = re.findall(r'"src":"(https://[^"]*scontent[^"]*)"', html)

            for i, img_url in enumerate(img_urls[:3]):
                img_url = img_url.replace("\\u0026", "&").replace("\\", "")
                save_path = OUTPUT_DIR / f"insta_{idx:03d}_{shortcode}_{i+1}.jpg"
                try:
                    img_resp = session.get(img_url, timeout=15)
                    if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                        save_path.write_bytes(img_resp.content)
                        result["images"].append(str(save_path.name))
                except Exception:
                    pass

            if result["images"]:
                print(
                    f"  [{idx:02d}] {shortcode}: OK ({len(result['images'])} images from source)"
                )
                return result

    except Exception as e:
        pass

    # Method 3: Embed page
    try:
        embed_url = f"https://www.instagram.com/p/{shortcode}/embed/"
        resp = session.get(embed_url, timeout=15)
        if resp.status_code == 200:
            import re

            img_matches = re.findall(
                r'"(https://[^"]*scontent[^"]*\.jpg[^"]*)"', resp.text
            )
            if not img_matches:
                img_matches = re.findall(
                    r'src="(https://[^"]*scontent[^"]*)"', resp.text
                )

            for i, img_url in enumerate(img_matches[:3]):
                img_url = (
                    img_url.replace("\\u0026", "&")
                    .replace("\\", "")
                    .replace("&amp;", "&")
                )
                save_path = OUTPUT_DIR / f"insta_{idx:03d}_{shortcode}_{i+1}.jpg"
                try:
                    img_resp = session.get(img_url, timeout=15)
                    if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                        save_path.write_bytes(img_resp.content)
                        result["images"].append(str(save_path.name))
                except Exception:
                    pass

            if result["images"]:
                print(
                    f"  [{idx:02d}] {shortcode}: OK ({len(result['images'])} via embed)"
                )
                return result
    except Exception:
        pass

    print(f"  [{idx:02d}] {shortcode}: FAILED")
    return result


def main():
    print("=" * 60)
    print(f"DUVETICA Instagram Downloader")
    print(f"Posts: {len(POST_CODES)}")
    print("=" * 60)

    results = []
    for idx, code in enumerate(POST_CODES, 1):
        result = download_via_oembed(code, idx)
        results.append(result)
        time.sleep(1)

    total_images = sum(len(r["images"]) for r in results)
    success = sum(1 for r in results if r["images"])
    failed = sum(1 for r in results if not r["images"])

    manifest_path = OUTPUT_DIR / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"DONE - Success: {success}/{len(POST_CODES)}, Images: {total_images}")
    print(f"Failed: {failed}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
