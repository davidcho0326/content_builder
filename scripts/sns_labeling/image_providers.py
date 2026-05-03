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


__all__ = [
    "GEMINI_MODEL",
    "DEFAULT_GPT_MODEL",
    "PROVIDER_FUNCS",
    "generate_campaign_multi",
    "generate_scene_gpt",
    "generate_scene_higgsfield",
]
