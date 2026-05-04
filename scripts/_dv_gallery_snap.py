"""Headless Chromium → screenshot of gallery.html for visual sanity check."""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

_DEFAULT = ("d:/ralph_kaphacy/ST)MKT_builder_for_fnf/st_cut-dev/results/dv/"
            "imc_driven/20260503_DV_27SS_20260503_231654/gallery.html")
GALLERY = Path(sys.argv[1] if len(sys.argv) > 1 else _DEFAULT).resolve()
OUT_DIR = GALLERY.parent / "_snapshots"
OUT_DIR.mkdir(exist_ok=True)


def main():
    if not GALLERY.exists():
        print(f"[ERROR] gallery not found: {GALLERY}", file=sys.stderr)
        return 2
    print(f"[snap] gallery → {GALLERY}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 1200},
            device_scale_factor=1,
        )
        page = ctx.new_page()
        url = GALLERY.as_uri()
        page.goto(url, wait_until="networkidle", timeout=60_000)
        # let images settle
        page.wait_for_timeout(2000)

        # full-page screenshot
        full = OUT_DIR / "gallery_full.png"
        page.screenshot(path=str(full), full_page=True)
        print(f"[ok] full-page → {full}")

        # also: just the first scene card (above-fold-ish)
        try:
            first = page.locator(".scene-card").first
            top = OUT_DIR / "gallery_scene01.png"
            first.screenshot(path=str(top))
            print(f"[ok] scene 01 → {top}")
        except Exception as e:
            print(f"[skip] scene 01 capture: {type(e).__name__}: {e}")

        # tile of 3 scene heads
        try:
            page.set_viewport_size({"width": 1920, "height": 4000})
            page.wait_for_timeout(500)
            tile = OUT_DIR / "gallery_top.png"
            page.screenshot(path=str(tile), clip={"x": 0, "y": 0, "width": 1920, "height": 4000})
            print(f"[ok] top viewport → {tile}")
        except Exception as e:
            print(f"[skip] top crop: {type(e).__name__}: {e}")

        browser.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
