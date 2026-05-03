"""Multi-provider image generation: Gemini + GPT (+ Higgsfield placeholder).

Conforms to project-docs/prompt-strategy.md §3 — 3-model parallel as the
standard. Each provider renders the SAME scene from the SAME proposal, so
results land in the run dir as `{scene_id}_{provider}.png`.

Providers:
  * gemini  — google.genai (gemini-3-pro-image-preview)
  * gpt     — openai (gpt-image-1, reference-guided via images.edit)
  * higgsfield — placeholder (TODO: hook to MCP / REST when available)

CLI is exposed via run_campaign_pipeline.py; this module is import-only.
"""
from __future__ import annotations

import base64
import io
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from PIL import Image

from sns_labeling.image_gen import (
    BRAND_MODEL_KEYWORDS,
    DEFAULT_IMAGE_MODEL as GEMINI_MODEL,
    build_prompt_from_scene,
    generate_scene as generate_scene_gemini,  # re-export
)


# ----------------------------- GPT ---------------------------------------

DEFAULT_GPT_MODEL = os.getenv("F_AND_F_GPT_IMAGE_MODEL", "gpt-image-2")


def _openai_client():
    from openai import OpenAI  # lazy import
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    return OpenAI(api_key=key)


def generate_scene_gpt(
    scene: dict,
    campaign: dict,
    out_dir: Path,
    *,
    model: Optional[str] = None,
    retries: int = 2,
    size: str = "1024x1536",
) -> dict:
    """Reference-guided gen via OpenAI images.edit (gpt-image-1)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    sid = scene["scene_id"]
    ref_path = Path(scene["reference"]["image"]) if scene["reference"].get("image") else None
    if not (ref_path and ref_path.exists()):
        return {"scene_id": sid, "provider": "gpt", "status": "skip",
                "error": f"reference image missing: {ref_path}"}

    prompt = build_prompt_from_scene(scene, campaign)
    (out_dir / f"{sid}_prompt.txt").write_text(prompt, encoding="utf-8")

    # OpenAI images.edit needs a square/portrait png with alpha; convert ref
    ref_img = Image.open(ref_path).convert("RGB")
    ref_img.thumbnail((1024, 1024), Image.LANCZOS)
    buf = io.BytesIO()
    ref_img.save(buf, format="PNG")
    buf.seek(0)
    buf.name = f"{sid}_ref.png"

    model_name = model or DEFAULT_GPT_MODEL
    client = _openai_client()

    last_err: Optional[BaseException] = None
    t0 = time.time()
    for attempt in range(1, retries + 1):
        try:
            buf.seek(0)
            result = client.images.edit(
                model=model_name,
                image=buf,
                prompt=prompt[:4000],
                size=size,
                n=1,
            )
            data = result.data[0]
            img_bytes = (
                base64.b64decode(data.b64_json)
                if getattr(data, "b64_json", None)
                else None
            )
            if img_bytes is None and getattr(data, "url", None):
                import urllib.request
                with urllib.request.urlopen(data.url) as resp:  # noqa: S310
                    img_bytes = resp.read()
            if not img_bytes:
                raise RuntimeError("no image in OpenAI response")
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            out = out_dir / f"{sid}_gpt.png"
            img.save(out)
            return {
                "scene_id": sid, "provider": "gpt", "status": "ok",
                "model": model_name,
                "image": str(out).replace("\\", "/"),
                "elapsed_sec": round(time.time() - t0, 2),
            }
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(5 * attempt)
                continue
    return {
        "scene_id": sid, "provider": "gpt", "status": "fail",
        "model": model_name,
        "error": f"{type(last_err).__name__}: {last_err}" if last_err else "unknown",
    }


# --------------------------- Higgsfield ----------------------------------
# Reserved hook. Higgsfield uses an MCP server (https://higgsfield.ai/mcp);
# Python-side direct calls require an API key + REST endpoint that may or may
# not be public. Until that's confirmed, mark as "skip" so the rest of the
# pipeline continues, and tell the user how to enable.

def generate_scene_higgsfield(
    scene: dict,
    campaign: dict,
    out_dir: Path,
    *,
    model: Optional[str] = None,
    **_kw,
) -> dict:
    """Stub — wire up to MCP/REST when key is available."""
    sid = scene["scene_id"]
    return {
        "scene_id": sid, "provider": "higgsfield", "status": "skip",
        "model": model or "soul_2",
        "error": "higgsfield provider not configured — register MCP server "
                  "or set HIGGSFIELD_API_KEY + HIGGSFIELD_ENDPOINT",
    }


# --------------------------- Orchestrator -------------------------------

PROVIDER_FUNCS = {
    "gemini": generate_scene_gemini,
    "gpt": generate_scene_gpt,
    "higgsfield": generate_scene_higgsfield,
}


def generate_campaign_multi(
    proposal: dict,
    out_dir: Path,
    *,
    providers: list[str],
    max_workers: int = 4,
) -> dict:
    """Render every scene with every requested provider in parallel."""
    campaign = proposal["campaign"]
    scenes = proposal["scene_plan"]
    results: list[dict] = []
    jobs = []
    for s in scenes:
        for p in providers:
            fn = PROVIDER_FUNCS.get(p)
            if fn is None:
                continue
            jobs.append((p, s, fn))
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(fn, s, campaign, out_dir): (p, s["scene_id"]) for (p, s, fn) in jobs}
        for fu in as_completed(futs):
            r = fu.result()
            results.append(r)
            tag = (r.get("provider") or "?").upper()
            extra = r.get("image") or r.get("error") or ""
            print(f"  [{r['status'].upper()}/{tag}] {r['scene_id']}  ::  {extra}")

    summary_by_provider = {}
    for p in providers:
        rs = [r for r in results if r.get("provider") == p or
              (p == "gemini" and r.get("model", "").startswith("gemini"))]
        summary_by_provider[p] = {
            "ok": sum(1 for r in rs if r["status"] == "ok"),
            "fail": sum(1 for r in rs if r["status"] == "fail"),
            "skip": sum(1 for r in rs if r["status"] == "skip"),
        }
    return {
        "providers": providers,
        "n_scenes": len(scenes),
        "by_provider": summary_by_provider,
        "results": results,
    }


# --------------------------- IMC-driven generation (v3) -------------------

from sns_labeling.image_gen import build_prompt_from_imc_scene


def _save_prompt(out_dir: Path, unit_id: str, prompt: str) -> None:
    (out_dir / f"{unit_id}_prompt.txt").write_text(prompt, encoding="utf-8")


def _gemini_call(prompt: str, ref_path: Path, out: Path,
                 *, model: Optional[str] = None, retries: int = 2) -> dict:
    """Direct Gemini image-edit call using the IMC prompt + ref image."""
    from google import genai as _genai
    from google.genai import types as _types

    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    client = _genai.Client(api_key=key)

    img = Image.open(ref_path).convert("RGB")
    if max(img.size) > 1024:
        img.thumbnail((1024, 1024), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    img_part = _types.Part(inline_data=_types.Blob(mime_type="image/jpeg",
                                                    data=buf.getvalue()))
    text_part = _types.Part(text=prompt)
    model_name = model or GEMINI_MODEL

    last_err: Optional[BaseException] = None
    t0 = time.time()
    for attempt in range(1, retries + 1):
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=[text_part, img_part],
            )
            for cand in (resp.candidates or []):
                for part in (cand.content.parts or []):
                    inline = getattr(part, "inline_data", None)
                    if inline and inline.data:
                        out.parent.mkdir(parents=True, exist_ok=True)
                        Image.open(io.BytesIO(inline.data)).convert("RGB").save(out)
                        return {"status": "ok", "model": model_name,
                                "image": str(out).replace("\\", "/"),
                                "elapsed_sec": round(time.time() - t0, 2)}
            raise RuntimeError("no inline image in Gemini response")
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(5 * attempt)
    return {"status": "fail", "model": model_name,
            "error": f"{type(last_err).__name__}: {last_err}"}


def generate_imc_unit_gemini(
    scene, spec, ref: dict, *,
    out_dir: Path, moment: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """Generate one image for (scene, ref) via Gemini using IMC prompt."""
    rank = ref.get("rank") or 1
    unit_id = f"{scene.slug}_R{rank:02d}"
    ref_path = Path(ref.get("image") or "")
    if not ref_path.exists():
        return {"unit_id": unit_id, "scene_id": scene.slug, "rank": rank,
                "provider": "gemini", "status": "skip",
                "error": f"reference image missing: {ref_path}"}
    prompt = build_prompt_from_imc_scene(scene, spec, ref, moment=moment)
    _save_prompt(out_dir, unit_id, prompt)
    out_path = out_dir / f"{unit_id}_gemini.png"
    res = _gemini_call(prompt, ref_path, out_path, model=model)
    res.update({"unit_id": unit_id, "scene_id": scene.slug, "rank": rank,
                "provider": "gemini"})
    return res


def generate_imc_unit_gpt(
    scene, spec, ref: dict, *,
    out_dir: Path, moment: Optional[str] = None,
    model: Optional[str] = None, size: str = "1024x1536", retries: int = 2,
) -> dict:
    """Generate one image for (scene, ref) via OpenAI images.edit."""
    rank = ref.get("rank") or 1
    unit_id = f"{scene.slug}_R{rank:02d}"
    ref_path = Path(ref.get("image") or "")
    if not ref_path.exists():
        return {"unit_id": unit_id, "scene_id": scene.slug, "rank": rank,
                "provider": "gpt", "status": "skip",
                "error": f"reference image missing: {ref_path}"}
    prompt = build_prompt_from_imc_scene(scene, spec, ref, moment=moment)
    _save_prompt(out_dir, unit_id, prompt)

    ref_img = Image.open(ref_path).convert("RGB")
    ref_img.thumbnail((1024, 1024), Image.LANCZOS)
    buf = io.BytesIO()
    ref_img.save(buf, format="PNG")
    buf.seek(0)
    buf.name = f"{unit_id}_ref.png"

    model_name = model or DEFAULT_GPT_MODEL
    client = _openai_client()
    last_err: Optional[BaseException] = None
    t0 = time.time()
    out_path = out_dir / f"{unit_id}_gpt.png"
    for attempt in range(1, retries + 1):
        try:
            buf.seek(0)
            result = client.images.edit(
                model=model_name, image=buf,
                prompt=prompt[:4000], size=size, n=1,
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
                raise RuntimeError("no image in OpenAI response")
            Image.open(io.BytesIO(img_bytes)).convert("RGB").save(out_path)
            return {"unit_id": unit_id, "scene_id": scene.slug, "rank": rank,
                    "provider": "gpt", "status": "ok", "model": model_name,
                    "image": str(out_path).replace("\\", "/"),
                    "elapsed_sec": round(time.time() - t0, 2)}
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(5 * attempt)
    return {"unit_id": unit_id, "scene_id": scene.slug, "rank": rank,
            "provider": "gpt", "status": "fail", "model": model_name,
            "error": f"{type(last_err).__name__}: {last_err}"}


IMC_PROVIDER_FUNCS = {
    "gemini": generate_imc_unit_gemini,
    "gpt": generate_imc_unit_gpt,
}


def generate_campaign_imc(
    spec,                                    # CampaignSpec
    refs_by_scene: dict[str, list[dict]],
    out_dir: Path,
    *,
    providers: list[str],
    moments_by_key: Optional[dict[str, str]] = None,
    max_workers: int = 4,
) -> dict:
    """IMC orchestrator: render every (scene, ref) with every provider."""
    moments_by_key = moments_by_key or {}
    jobs = []
    for scene in spec.scenes:
        for ref in refs_by_scene.get(scene.slug, []) or []:
            mom = moments_by_key.get(f"{scene.slug}__{ref.get('post_id')}")
            for p in providers:
                fn = IMC_PROVIDER_FUNCS.get(p)
                if fn is None:
                    continue
                jobs.append((p, scene, ref, mom, fn))

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {
            ex.submit(fn, scene, spec, ref, out_dir=out_dir, moment=mom):
                (p, scene.slug, ref.get("rank"))
            for (p, scene, ref, mom, fn) in jobs
        }
        for fu in as_completed(futs):
            r = fu.result()
            results.append(r)
            tag = (r.get("provider") or "?").upper()
            extra = r.get("image") or r.get("error") or ""
            print(f"  [{r['status'].upper()}/{tag}] {r.get('unit_id', r.get('scene_id'))}  ::  {extra}")

    by_provider = {}
    for p in providers:
        rs = [r for r in results if r.get("provider") == p]
        by_provider[p] = {
            "ok": sum(1 for r in rs if r["status"] == "ok"),
            "fail": sum(1 for r in rs if r["status"] == "fail"),
            "skip": sum(1 for r in rs if r["status"] == "skip"),
        }
    return {
        "providers": providers,
        "n_scenes": len(spec.scenes),
        "n_units": len(jobs) // max(1, len(providers)),
        "by_provider": by_provider,
        "results": results,
    }


__all__ = [
    "GEMINI_MODEL",
    "DEFAULT_GPT_MODEL",
    "PROVIDER_FUNCS",
    "IMC_PROVIDER_FUNCS",
    "generate_campaign_multi",
    "generate_campaign_imc",
    "generate_scene_gpt",
    "generate_scene_higgsfield",
    "generate_imc_unit_gemini",
    "generate_imc_unit_gpt",
]
