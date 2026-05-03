"""Step C+ Virtual Try-On — dual-engine.

Engine A: Gemini-3-pro-image-preview (via external `core/virtual_tryon` module
          at c:/python/venv/fnf-image-gen-mcp-deploy)
Engine B: GPT-image-2 (OpenAI images.edit with multi-image input)

Both engines receive the SAME (model_image, product_image, prompt) tuple so
output quality can be compared cell-by-cell in the gallery.

Used by run_campaign_pipeline.py Step C+. See plan file for design details.
"""
from __future__ import annotations

import base64
import io
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Iterable

from PIL import Image
from dotenv import load_dotenv

load_dotenv()


# ---------- External virtual_tryon (Gemini engine) imports ------------------

_VTON_ROOT = Path(os.getenv(
    "F_AND_F_VTON_ROOT",
    r"c:/python/venv/fnf-image-gen-mcp-deploy",
))
_VTON_AVAILABLE = False
_vt_analyze_product = None
_vt_analyze_model = None
_vt_generate_tryon = None
_vt_get_aspect = None
_vt_build_prompt = None

_vt_generate_multi_tryon = None
_vt_build_multi_prompt = None

try:
    if _VTON_ROOT.exists() and str(_VTON_ROOT) not in sys.path:
        sys.path.insert(0, str(_VTON_ROOT))
    from core.virtual_tryon import (  # noqa: E402
        analyze_product as _vt_analyze_product,
        analyze_model as _vt_analyze_model,
        generate_tryon as _vt_generate_tryon,
        generate_multi_tryon as _vt_generate_multi_tryon,
        get_closest_aspect_ratio as _vt_get_aspect,
        build_tryon_prompt as _vt_build_prompt,
        build_multi_tryon_prompt as _vt_build_multi_prompt,
    )
    _VTON_AVAILABLE = True
except Exception as e:  # noqa: BLE001
    print(f"[tryon] external virtual_tryon unavailable: "
          f"{type(e).__name__}: {e}")


# ---------- Gemini client (lazy) --------------------------------------------

def _gemini_client():
    from google import genai
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    return genai.Client(api_key=key)


# ---------- OpenAI client (lazy) --------------------------------------------

def _openai_client():
    from openai import OpenAI
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    return OpenAI(api_key=key)


# ---------- Engine A: Gemini-3-pro-image-preview ----------------------------

def _apply_tryon_gemini(
    model_path: Path,
    product_path: Path,
    out_path: Path,
    *,
    product_analysis,
    model_analysis_cache: dict,
    aspect_ratio: str = "3:4",
) -> dict:
    """Single try-on via Gemini, using prompt from external virtual_tryon."""
    if not _VTON_AVAILABLE:
        return {"status": "skip", "engine": "gemini",
                "error": "virtual_tryon module unavailable"}
    t0 = time.time()
    client = _gemini_client()
    model_pil = Image.open(model_path).convert("RGB")
    product_pil = Image.open(product_path).convert("RGB")

    # Cache model_analysis per model_image (same image used twice — once per engine)
    cache_key = str(model_path)
    model_analysis = model_analysis_cache.get(cache_key)
    if model_analysis is None:
        try:
            model_analysis = _vt_analyze_model(client, model_pil)
            model_analysis_cache[cache_key] = model_analysis
        except Exception as e:  # noqa: BLE001
            return {"status": "fail", "engine": "gemini",
                    "error": f"analyze_model: {type(e).__name__}: {e}"}

    try:
        prompt = _vt_build_prompt(product_analysis, model_analysis,
                                   enhancement_text="")
    except Exception as e:  # noqa: BLE001
        return {"status": "fail", "engine": "gemini",
                "error": f"build_prompt: {type(e).__name__}: {e}"}

    try:
        result = _vt_generate_tryon(
            client=client,
            model_image=model_pil,
            product_image=product_pil,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            temperature=0.2,
            image_size="2K",
            max_retries=3,
        )
    except Exception as e:  # noqa: BLE001
        return {"status": "fail", "engine": "gemini",
                "error": f"generate_tryon: {type(e).__name__}: {e}"}

    if result is None:
        return {"status": "fail", "engine": "gemini",
                "error": "no image returned (safety/timeout)"}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(out_path)
    return {"status": "ok", "engine": "gemini",
            "image": str(out_path).replace("\\", "/"),
            "elapsed_sec": round(time.time() - t0, 2)}


# ---------- Engine A (multi): Gemini-3-pro-image, top + bottom --------------

def _apply_multi_tryon_gemini(
    model_path: Path,
    top_path: Path,
    bottom_path: Path,
    out_path: Path,
    *,
    top_analysis,
    bottom_analysis,
    model_analysis_cache: dict,
    aspect_ratio: str = "3:4",
) -> dict:
    """Multi-garment try-on via Gemini (top + bottom simultaneously)."""
    if not _VTON_AVAILABLE or _vt_generate_multi_tryon is None:
        return {"status": "skip", "engine": "gemini",
                "error": "external virtual_tryon multi unavailable"}
    t0 = time.time()
    client = _gemini_client()
    model_pil = Image.open(model_path).convert("RGB")
    top_pil = Image.open(top_path).convert("RGB")
    bottom_pil = Image.open(bottom_path).convert("RGB")

    cache_key = str(model_path)
    model_analysis = model_analysis_cache.get(cache_key)
    if model_analysis is None:
        try:
            model_analysis = _vt_analyze_model(client, model_pil)
            model_analysis_cache[cache_key] = model_analysis
        except Exception as e:  # noqa: BLE001
            return {"status": "fail", "engine": "gemini",
                    "error": f"analyze_model: {type(e).__name__}: {e}"}

    try:
        prompt = _vt_build_multi_prompt(
            product_analyses=[top_analysis, bottom_analysis],
            model_analysis=model_analysis,
            enhancement_text="",
            styling_instruction="",
        )
    except Exception as e:  # noqa: BLE001
        return {"status": "fail", "engine": "gemini",
                "error": f"build_multi_prompt: {type(e).__name__}: {e}"}

    try:
        result = _vt_generate_multi_tryon(
            client=client,
            model_image=model_pil,
            product_images=[top_pil, bottom_pil],
            product_analyses=[top_analysis, bottom_analysis],
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            temperature=0.2,
            image_size="2K",
            max_retries=3,
        )
    except Exception as e:  # noqa: BLE001
        return {"status": "fail", "engine": "gemini",
                "error": f"generate_multi: {type(e).__name__}: {e}"}

    if result is None:
        return {"status": "fail", "engine": "gemini",
                "error": "no image (safety/timeout)"}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(out_path)
    return {"status": "ok", "engine": "gemini", "mode": "multi",
            "image": str(out_path).replace("\\", "/"),
            "elapsed_sec": round(time.time() - t0, 2)}


# ---------- Engine B: GPT-image-2 multi-image edit --------------------------

# Compact try-on prompt for GPT-image-2 (it accepts shorter prompts more
# reliably; we still inject product_analysis details for accuracy).
_GPT_TRYON_HEADER = """VIRTUAL TRY-ON: replace ONLY the model's clothing with the garment from the second attached image.

ABSOLUTE PRESERVATION (DO NOT CHANGE):
- The model's face: identical features, expression, gaze, skin tone, hair, makeup
- The model's pose: every joint angle, weight distribution, body angle, head tilt — pixel identical
- The background: same environment, same objects, same lighting, same depth of field
- The camera angle, framing, and composition

OUTFIT REPLACEMENT:
- Replace the current clothing with the garment shown in the SECOND attached image
- The new garment must drape and fit naturally on the existing pose
- COLOR/PATTERN/LOGO/MATERIAL must match the product image EXACTLY
- Lighting on the new garment must match the scene's existing lighting

PRODUCT DETAILS (for accuracy):
{product_details}

DO NOT change face/hair/pose/background. Output: photorealistic editorial-quality image."""


_GPT_MULTI_TRYON_HEADER = """VIRTUAL TRY-ON: replace the model's TOP with the second attached image and the model's BOTTOM with the third attached image.

ABSOLUTE PRESERVATION (DO NOT CHANGE):
- The model's face: identical features, expression, gaze, skin tone, hair, makeup
- The model's pose: every joint angle, weight distribution, body angle, head tilt — pixel identical
- The background: same environment, same objects, same lighting, same depth of field
- The camera angle, framing, and composition

OUTFIT REPLACEMENT (TOP + BOTTOM):
- Replace the current top with the garment shown in the SECOND attached image
- Replace the current bottom with the garment shown in the THIRD attached image
- Both garments must drape and fit naturally on the existing pose
- COLOR/PATTERN/LOGO/MATERIAL must match each product image EXACTLY
- The waist transition between top and bottom must be seamless

TOP DETAILS:
{top_details}

BOTTOM DETAILS:
{bottom_details}

DO NOT change face/hair/pose/background. Output: photorealistic editorial-quality image."""


def _format_product_details(pa) -> str:
    """Compact 6-line summary from ProductAnalysis dataclass for GPT prompt."""
    if pa is None:
        return "(use second attached image as visual reference)"
    bits = []
    g = getattr(pa, "garment_type", None) or ""
    cat = getattr(pa, "category", None) or ""
    if g or cat:
        bits.append(f"- Type: {g} / {cat}")
    pc = getattr(pa, "primary_color", None)
    if pc:
        bits.append(f"- Primary color: {pc}")
    sc = getattr(pa, "secondary_colors", None)
    if sc:
        sc_text = ", ".join(sc) if isinstance(sc, list) else str(sc)
        bits.append(f"- Secondary colors: {sc_text}")
    pat = getattr(pa, "pattern", None)
    if pat:
        bits.append(f"- Pattern: {pat}")
    mat = getattr(pa, "material_appearance", None) or getattr(pa, "material", None)
    if mat:
        bits.append(f"- Material: {mat}")
    fit = getattr(pa, "fit_style", None) or getattr(pa, "fit", None)
    if fit:
        bits.append(f"- Fit: {fit}")
    logo = getattr(pa, "logo", None)
    if logo:
        bits.append(f"- Logo: {logo}")
    details = getattr(pa, "key_details", None)
    if details:
        d_text = "; ".join(details) if isinstance(details, list) else str(details)
        bits.append(f"- Details: {d_text}")
    return "\n".join(bits) or "(use second attached image as visual reference)"


def _apply_tryon_gpt(
    model_path: Path,
    product_path: Path,
    out_path: Path,
    *,
    product_analysis,
    size: str = "1024x1536",
    model_name: str = "gpt-image-2",
    retries: int = 2,
) -> dict:
    """Multi-image GPT-image-2 edit: [model, product] → tryon image."""
    t0 = time.time()
    try:
        client = _openai_client()
    except Exception as e:  # noqa: BLE001
        return {"status": "fail", "engine": "gpt",
                "error": f"client: {type(e).__name__}: {e}"}

    # Pre-resize for safer upload
    def _to_png_buffer(p: Path, max_size: int) -> io.BytesIO:
        img = Image.open(p).convert("RGB")
        if max(img.size) > max_size:
            img.thumbnail((max_size, max_size), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    prompt = _GPT_TRYON_HEADER.format(
        product_details=_format_product_details(product_analysis)
    )

    last_err: Optional[BaseException] = None
    for attempt in range(1, retries + 1):
        try:
            model_buf = _to_png_buffer(model_path, 1536)
            product_buf = _to_png_buffer(product_path, 1024)
            model_buf.name = "model.png"
            product_buf.name = "product.png"
            result = client.images.edit(
                model=model_name,
                image=[model_buf, product_buf],
                prompt=prompt[:4000],
                size=size,
                n=1,
            )
            data = result.data[0]
            img_bytes = (
                base64.b64decode(data.b64_json)
                if getattr(data, "b64_json", None) else None
            )
            if img_bytes is None and getattr(data, "url", None):
                import urllib.request
                with urllib.request.urlopen(data.url) as resp:  # noqa: S310
                    img_bytes = resp.read()
            if not img_bytes:
                raise RuntimeError("no image bytes in OpenAI response")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            Image.open(io.BytesIO(img_bytes)).convert("RGB").save(out_path)
            return {"status": "ok", "engine": "gpt", "model": model_name,
                    "image": str(out_path).replace("\\", "/"),
                    "elapsed_sec": round(time.time() - t0, 2)}
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries:
                time.sleep(5 * attempt)
    return {"status": "fail", "engine": "gpt", "model": model_name,
            "error": f"{type(last_err).__name__}: {last_err}" if last_err else "unknown"}


def _apply_multi_tryon_gpt(
    model_path: Path,
    top_path: Path,
    bottom_path: Path,
    out_path: Path,
    *,
    top_analysis,
    bottom_analysis,
    size: str = "1024x1536",
    model_name: str = "gpt-image-2",
    retries: int = 2,
) -> dict:
    """Multi-garment GPT-image-2 edit: [model, top, bottom] → tryon."""
    t0 = time.time()
    try:
        client = _openai_client()
    except Exception as e:  # noqa: BLE001
        return {"status": "fail", "engine": "gpt",
                "error": f"client: {type(e).__name__}: {e}"}

    def _to_png_buffer(p: Path, max_size: int) -> io.BytesIO:
        img = Image.open(p).convert("RGB")
        if max(img.size) > max_size:
            img.thumbnail((max_size, max_size), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    prompt = _GPT_MULTI_TRYON_HEADER.format(
        top_details=_format_product_details(top_analysis),
        bottom_details=_format_product_details(bottom_analysis),
    )

    last_err: Optional[BaseException] = None
    for attempt in range(1, retries + 1):
        try:
            model_buf = _to_png_buffer(model_path, 1536)
            top_buf = _to_png_buffer(top_path, 1024)
            bottom_buf = _to_png_buffer(bottom_path, 1024)
            model_buf.name = "model.png"
            top_buf.name = "top.png"
            bottom_buf.name = "bottom.png"
            result = client.images.edit(
                model=model_name,
                image=[model_buf, top_buf, bottom_buf],
                prompt=prompt[:4000],
                size=size, n=1,
            )
            data = result.data[0]
            img_bytes = (
                base64.b64decode(data.b64_json)
                if getattr(data, "b64_json", None) else None
            )
            if img_bytes is None and getattr(data, "url", None):
                import urllib.request
                with urllib.request.urlopen(data.url) as resp:  # noqa: S310
                    img_bytes = resp.read()
            if not img_bytes:
                raise RuntimeError("no image bytes in OpenAI response")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            Image.open(io.BytesIO(img_bytes)).convert("RGB").save(out_path)
            return {"status": "ok", "engine": "gpt", "mode": "multi",
                    "model": model_name,
                    "image": str(out_path).replace("\\", "/"),
                    "elapsed_sec": round(time.time() - t0, 2)}
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries:
                time.sleep(5 * attempt)
    return {"status": "fail", "engine": "gpt", "mode": "multi",
            "model": model_name,
            "error": f"{type(last_err).__name__}: {last_err}" if last_err else "unknown"}


# ---------- Orchestrator ----------------------------------------------------

def run_tryon_step(
    spec,                                     # CampaignSpec
    refs_by_scene: dict,                      # {scene_slug: [refs]}
    gen_results: list[dict],                  # image_providers.generate_campaign_imc results
    out_dir: Path,                            # 03_images
    *,
    only_provider: str = "gpt",               # 'gpt' (default), 'all', or specific
    engines: Iterable[str] = ("gemini", "gpt"),
    max_workers: int = 3,
    product_match=None,                        # pre-resolved hero ProductMatch (top), or None to route now
    bottom_match=None,                         # optional ProductMatch for bottom (multi-tryon mode)
) -> dict:
    """Run try-on on every Direct gpt result with the chosen engines.

    Steps:
      1. Hero product routed once (if not provided).
      2. Pre-analyze the product image once via Gemini VLM (cached for engine A,
         and reused for engine B's prompt details).
      3. For each generated image matching `only_provider`, dispatch try-on
         calls in parallel.

    Returns:
      {
        'product_match': dict or None,
        'engines': list[str],
        'ok': int, 'fail': int, 'skip': int,
        'results': list[dict],    # per-call status records
      }
    """
    if product_match is None:
        from sns_labeling.product_router import route_hero_product
        product_match = route_hero_product(spec)
    if product_match is None:
        return {"product_match": None, "engines": list(engines),
                "ok": 0, "fail": 0, "skip": 0, "results": [],
                "note": "no hero product matched"}

    product_path = product_match.hero_image
    if not product_path.exists():
        return {"product_match": product_match.to_dict(),
                "engines": list(engines), "ok": 0, "fail": 0, "skip": 0,
                "results": [], "note": "product file missing"}

    # Filter generated results to the targeted provider(s)
    if only_provider == "all":
        target_providers = {"gpt", "hf_gpt", "hf_mkt"}
    else:
        target_providers = {only_provider}
    targets = [r for r in gen_results
               if r.get("status") == "ok" and r.get("provider") in target_providers]

    # Multi mode if bottom_match provided AND its file exists
    multi_mode = False
    bottom_path = None
    if bottom_match is not None and bottom_match.hero_image.exists():
        multi_mode = True
        bottom_path = bottom_match.hero_image
        print(f"  [tryon] multi-mode ON — top + bottom simultaneous swap")
    elif bottom_match is not None:
        print(f"  [tryon] bottom_match given but file missing; falling back to single mode")

    # Pre-analyze top product (once; reused by both engines)
    top_analysis = None
    bottom_analysis = None
    if _VTON_AVAILABLE and "gemini" in engines:
        try:
            client = _gemini_client()
            product_pil = Image.open(product_path).convert("RGB")
            top_analysis = _vt_analyze_product(client, product_pil)
            print(f"  [tryon] analyzed top: "
                  f"{getattr(top_analysis, 'garment_type', '')} / "
                  f"{getattr(top_analysis, 'primary_color', '')}")
            if multi_mode:
                bottom_pil = Image.open(bottom_path).convert("RGB")
                bottom_analysis = _vt_analyze_product(client, bottom_pil)
                print(f"  [tryon] analyzed bottom: "
                      f"{getattr(bottom_analysis, 'garment_type', '')} / "
                      f"{getattr(bottom_analysis, 'primary_color', '')}")
        except Exception as e:  # noqa: BLE001
            print(f"  [tryon] product analysis failed: "
                  f"{type(e).__name__}: {e}")
    # legacy alias
    product_analysis = top_analysis

    # Build job list
    model_analysis_cache: dict = {}
    jobs: list[tuple] = []
    for r in targets:
        unit_id = r.get("unit_id") or ""
        provider = r.get("provider")
        raw_path = Path(r.get("image") or "")
        if not raw_path.exists():
            continue
        for engine in engines:
            out_name = f"{unit_id}_{provider}_tryon_{engine}.png"
            out_path = out_dir / out_name
            jobs.append((engine, raw_path, out_path, unit_id, provider))

    print(f"  [tryon] dispatching {len(jobs)} jobs "
          f"({len(targets)} images × {len(list(engines))} engines)")

    results: list[dict] = []

    def _run_one(job):
        engine, raw_path, out_path, unit_id, provider = job
        if engine == "gemini":
            if multi_mode:
                res = _apply_multi_tryon_gemini(
                    raw_path, product_path, bottom_path, out_path,
                    top_analysis=top_analysis,
                    bottom_analysis=bottom_analysis,
                    model_analysis_cache=model_analysis_cache,
                )
            else:
                res = _apply_tryon_gemini(
                    raw_path, product_path, out_path,
                    product_analysis=top_analysis,
                    model_analysis_cache=model_analysis_cache,
                )
        elif engine == "gpt":
            if multi_mode:
                res = _apply_multi_tryon_gpt(
                    raw_path, product_path, bottom_path, out_path,
                    top_analysis=top_analysis,
                    bottom_analysis=bottom_analysis,
                )
            else:
                res = _apply_tryon_gpt(
                    raw_path, product_path, out_path,
                    product_analysis=top_analysis,
                )
        else:
            res = {"status": "skip", "engine": engine,
                   "error": f"unknown engine '{engine}'"}
        res.update({"unit_id": unit_id, "raw_provider": provider,
                    "mode": "multi" if multi_mode else "single"})
        return res

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_run_one, j): j for j in jobs}
        for fu in as_completed(futs):
            r = fu.result()
            results.append(r)
            tag = (r.get("engine") or "?").upper()
            extra = r.get("image") or r.get("error") or ""
            print(f"  [{r['status'].upper()}/TRYON-{tag}] "
                  f"{r.get('unit_id', '?')}_{r.get('raw_provider', '?')}  ::  {extra}")

    summary = {
        "mode": "multi" if multi_mode else "single",
        "product_match": product_match.to_dict(),
        "bottom_match": bottom_match.to_dict() if bottom_match is not None else None,
        "engines": list(engines),
        "ok": sum(1 for r in results if r["status"] == "ok"),
        "fail": sum(1 for r in results if r["status"] == "fail"),
        "skip": sum(1 for r in results if r["status"] == "skip"),
        "results": results,
    }
    return summary


__all__ = [
    "run_tryon_step",
    "_apply_tryon_gemini",
    "_apply_tryon_gpt",
    "_apply_multi_tryon_gemini",
    "_apply_multi_tryon_gpt",
]
