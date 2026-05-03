# WORKFLOW_BYPASS_OK: strategy-cut-builder data collection (2026-04-30)
"""Crawl Duvetica official site - download product & marketing images

Usage:
    PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/crawl_duvetica.py
"""

import json
import re
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "db" / "strategy-cut-builder" / "duvetica" / "official-site"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://www.duvetica.co.kr"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

CATEGORIES = {
    "women": "/display/DVMB01",
    "men": "/display/DVMB02",
}

session = requests.Session()
session.headers.update(HEADERS)


def get_product_list(category_path: str) -> list[dict]:
    """Fetch product listing page and extract product URLs + thumbnail images."""
    url = f"{BASE_URL}{category_path}"
    print(f"[FETCH] Listing: {url}")
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    products = []
    seen_hrefs = set()
    for a_tag in soup.select('a[href*="/product-detail/"]'):
        href = a_tag.get("href", "")
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)

        img = a_tag.select_one("img")
        thumb_url = ""
        if img:
            thumb_url = (
                img.get("src") or img.get("data-src") or img.get("data-lazy") or ""
            )

        sku = (
            href.split("/product-detail/")[-1].split("?")[0]
            if "/product-detail/" in href
            else ""
        )

        name_el = a_tag.find_next(string=True, attrs=None)
        alt_text = img.get("alt", "") if img else ""

        products.append(
            {
                "href": href,
                "sku": sku,
                "name": alt_text or sku,
                "thumb_url": thumb_url,
                "full_url": urljoin(BASE_URL, href),
            }
        )

    print(f"  Found {len(products)} products")
    return products


def get_product_images(product: dict) -> list[dict]:
    """Fetch a product detail page and extract all images."""
    url = product["full_url"]
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"  [ERROR] {product['sku']}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    images = []
    seen_urls = set()

    for img in soup.select("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy") or ""
        if not src or src in seen_urls:
            continue
        if "static-resource.duvetica.co.kr" not in src and "images/goods" not in src:
            continue
        if "icon" in src.lower() or "logo" in src.lower() or "banner" in src.lower():
            continue

        seen_urls.add(src)
        alt = img.get("alt", "")
        is_marketing = _is_marketing_image(src, alt)
        images.append(
            {
                "url": src,
                "alt": alt,
                "type": "marketing" if is_marketing else "product",
            }
        )

    for source in soup.select("source"):
        srcset = source.get("srcset", "")
        if srcset and "static-resource.duvetica.co.kr" in srcset:
            urls = [u.strip().split(" ")[0] for u in srcset.split(",")]
            for u in urls:
                if u and u not in seen_urls:
                    seen_urls.add(u)
                    images.append({"url": u, "alt": "", "type": "product"})

    return images


def _is_marketing_image(url: str, alt: str) -> bool:
    """Heuristic: marketing images tend to be lifestyle/campaign shots."""
    marketing_hints = [
        "campaign",
        "look",
        "life",
        "mood",
        "editorial",
        "visual",
        "main",
        "banner",
    ]
    product_hints = ["detail", "thnail", "color", "swatch", "zoom"]
    url_lower = url.lower()
    for hint in product_hints:
        if hint in url_lower:
            return False
    for hint in marketing_hints:
        if hint in url_lower or hint in alt.lower():
            return True
    return False


def download_image(url: str, save_path: Path) -> bool:
    """Download a single image."""
    if save_path.exists():
        return True
    try:
        clean_url = re.sub(r"/cdn-cgi/image/[^/]+/", "/", url)
        if not clean_url.startswith("http"):
            clean_url = url
        resp = session.get(clean_url, timeout=30)
        resp.raise_for_status()
        if len(resp.content) < 1000:
            return False
        save_path.write_bytes(resp.content)
        return True
    except Exception:
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            if len(resp.content) < 1000:
                return False
            save_path.write_bytes(resp.content)
            return True
        except Exception as e:
            print(f"  [DOWNLOAD ERROR] {save_path.name}: {e}")
            return False


def crawl_category(category_name: str, category_path: str):
    """Crawl all products in a category."""
    cat_dir = OUTPUT_DIR / category_name
    product_dir = cat_dir / "product"
    marketing_dir = cat_dir / "marketing"
    product_dir.mkdir(parents=True, exist_ok=True)
    marketing_dir.mkdir(parents=True, exist_ok=True)

    products = get_product_list(category_path)
    all_images = []
    manifest = []

    print(f"\n[CRAWL] {category_name}: {len(products)} products")

    def fetch_product(p):
        imgs = get_product_images(p)
        return p, imgs

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_product, p): p for p in products}
        for future in as_completed(futures):
            product, imgs = future.result()
            print(f"  {product['sku']}: {len(imgs)} images")
            for i, img_info in enumerate(imgs):
                ext = ".jpg"
                if ".png" in img_info["url"].lower():
                    ext = ".png"
                elif ".webp" in img_info["url"].lower():
                    ext = ".webp"

                img_type = img_info["type"]
                filename = f"{product['sku']}_{i+1:02d}{ext}"
                save_dir = marketing_dir if img_type == "marketing" else product_dir
                save_path = save_dir / filename

                all_images.append(
                    {
                        "url": img_info["url"],
                        "save_path": str(save_path),
                        "sku": product["sku"],
                        "name": product["name"],
                        "type": img_type,
                        "alt": img_info["alt"],
                    }
                )

                manifest.append(
                    {
                        "sku": product["sku"],
                        "name": product["name"],
                        "filename": filename,
                        "type": img_type,
                        "url": img_info["url"],
                    }
                )

    print(f"\n[DOWNLOAD] {len(all_images)} images total")
    downloaded = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {}
        for img in all_images:
            f = executor.submit(download_image, img["url"], Path(img["save_path"]))
            futures[f] = img

        for future in as_completed(futures):
            if future.result():
                downloaded += 1
            else:
                failed += 1

    print(f"  Downloaded: {downloaded}, Failed: {failed}")

    manifest_path = cat_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"  Manifest: {manifest_path}")

    return manifest


def main():
    print("=" * 60)
    print("DUVETICA Official Site Crawler")
    print("=" * 60)

    all_manifests = {}
    for cat_name, cat_path in CATEGORIES.items():
        manifest = crawl_category(cat_name, cat_path)
        all_manifests[cat_name] = manifest
        time.sleep(1)

    total_product = sum(
        1 for m in all_manifests.values() for item in m if item["type"] == "product"
    )
    total_marketing = sum(
        1 for m in all_manifests.values() for item in m if item["type"] == "marketing"
    )

    print("\n" + "=" * 60)
    print(f"DONE - Product: {total_product}, Marketing: {total_marketing}")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
