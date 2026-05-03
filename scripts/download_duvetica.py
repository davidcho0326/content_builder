# WORKFLOW_BYPASS_OK: strategy-cut-builder data collection (2026-04-30)
"""Download Duvetica official site images — fetch each product page, extract & download images

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/download_duvetica.py
"""

import json
import re
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "db" / "strategy-cut-builder" / "duvetica" / "official-site"

BASE_URL = "https://www.duvetica.co.kr"
CDN_BASE = "https://static-resource.duvetica.co.kr"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    "Referer": "https://www.duvetica.co.kr/",
}

PRODUCTS = [
    ("VDDH36061-GRL", "euripide_sugar_N", "women"),
    ("VDDJ36461-IVD", "barletta", "women"),
    ("VDWJ11961-BKS", "casalina_BKS", "women"),
    ("VDWJ14461-BRD", "osilo", "women"),
    ("VDRS16063-IVL", "messina", "women"),
    ("VDRS18063-IVL", "montellino", "women"),
    ("VDWJ11961-BGS", "casalina_BGS", "women"),
    ("VDWJ31461-BGS", "regia", "women"),
    ("VDKP12161-CRS", "achillia", "women"),
    ("VDSL17163-IVL", "rocara", "women"),
    ("VDVT12163-NYD", "gaeta_light_NYD", "women"),
    ("VDVT12163-PKL", "gaeta_light_PKL", "women"),
    ("VDKC12763-IVL", "pontinia_IVL", "women"),
    ("VDKC12763-NYD", "pontinia_NYD", "women"),
    ("VDSP12763-NYD", "bagnone_shorts_NYD", "women"),
    ("VDSP12763-PKS", "bagnone_shorts_PKS", "women"),
    ("VDPT12863-INL", "conili_INL", "women"),
    ("VDPT12863-INS", "conili_INS", "women"),
    ("VDSP14763-BRD", "trena_shorts_BRD", "women"),
    ("VDSP14763-RBL", "trena_shorts_RBL", "women"),
    ("VUPT13361-BGD", "palomonte", "men"),
    ("VUPT13161-KAS", "golorice", "men"),
    ("VURS18063-BKS", "montaguto", "men"),
    ("VURS16963-CGD", "cutro", "men"),
    ("VUTS15761-IVL", "nevegal", "men"),
    ("VUTS20463-BKS", "norcha", "men"),
    ("VURS17063-SBL", "braies", "men"),
    ("VUPT13761-IVS", "pisciano", "men"),
    ("VUKP17863-CRS", "ascoli", "men"),
    ("VUKP16263-BKS", "fosano", "men"),
]

session = requests.Session()
session.headers.update(HEADERS)


def fetch_product_images(sku: str) -> list[str]:
    """Fetch product page HTML and extract image URLs via regex."""
    url = f"{BASE_URL}/product-detail/{sku}"
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        print(f"  [ERROR] fetch {sku}: {e}")
        return []

    pattern = re.compile(
        r"https://static-resource\.duvetica\.co\.kr"
        r"(?:/cdn-cgi/image/[^/]+)?"
        r"/images/goods/ec/[^\"'\s)]+\.(?:jpg|jpeg|png|webp)",
        re.IGNORECASE,
    )
    raw_urls = set(pattern.findall(html))

    clean_urls = set()
    for u in raw_urls:
        clean = re.sub(r"/cdn-cgi/image/[^/]+/", "/", u)
        if (
            "/thnail/" not in clean
            and "icon" not in clean.lower()
            and "logo" not in clean.lower()
        ):
            clean_urls.add(clean)

    return sorted(clean_urls)


def download_image(url: str, save_path: Path) -> bool:
    """Download a single image."""
    if save_path.exists() and save_path.stat().st_size > 1000:
        return True
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        if len(resp.content) < 1000:
            return False
        save_path.write_bytes(resp.content)
        return True
    except Exception as e:
        print(f"  [DL ERROR] {save_path.name}: {e}")
        return False


def main():
    print("=" * 60)
    print("DUVETICA Image Downloader")
    print(f"Products: {len(PRODUCTS)}")
    print("=" * 60)

    manifest = []
    all_downloads = []

    for sku, name, gender in PRODUCTS:
        images = fetch_product_images(sku)
        print(f"[{gender.upper()}] {sku} ({name}): {len(images)} images")

        product_dir = OUTPUT_DIR / gender / name
        product_dir.mkdir(parents=True, exist_ok=True)

        for i, img_url in enumerate(images):
            ext = ".png" if ".png" in img_url.lower() else ".jpg"
            filename = f"{name}_{i+1:02d}{ext}"
            save_path = product_dir / filename

            all_downloads.append((img_url, save_path))
            manifest.append(
                {
                    "sku": sku,
                    "name": name,
                    "gender": gender,
                    "filename": filename,
                    "url": img_url,
                    "path": str(save_path.relative_to(PROJECT_ROOT)),
                }
            )

        time.sleep(0.3)

    print(f"\n[DOWNLOAD] {len(all_downloads)} images total")

    downloaded = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(download_image, url, path): (url, path)
            for url, path in all_downloads
        }
        for future in as_completed(futures):
            if future.result():
                downloaded += 1
            else:
                failed += 1
            if (downloaded + failed) % 50 == 0:
                print(f"  Progress: {downloaded + failed}/{len(all_downloads)}")

    manifest_path = OUTPUT_DIR / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"DONE - Downloaded: {downloaded}, Failed: {failed}")
    print(f"Manifest: {manifest_path}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
