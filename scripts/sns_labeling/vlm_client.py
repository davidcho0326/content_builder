"""Self-contained Gemini VLM client for SNS labeling.

No dependency on `core.api` / `core.config`. Uses google-genai SDK directly.

Env:
    GEMINI_API_KEY              - required
    F_AND_F_VISION_MODEL        - optional, default "gemini-2.5-flash"

Public API:
    call_vlm_json(prompt: str, img: PIL.Image, *, retries=3, temperature=0.1)
        -> {"data": dict, "usage": {...}, "model": str, "raw_text": str}
"""
from __future__ import annotations

import json
import os
import time
from io import BytesIO
from typing import Optional

from PIL import Image
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

DEFAULT_MODEL = os.getenv("F_AND_F_VISION_MODEL", "gemini-2.5-flash")
MAX_IMAGE_DIM = 1024


class VLMError(RuntimeError):
    pass


def _client() -> "genai.Client":
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise VLMError("GEMINI_API_KEY not set in env or .env")
    return genai.Client(api_key=key)


def preprocess(img_path) -> Image.Image:
    """Open + RGB + thumbnail to MAX_IMAGE_DIM."""
    img = Image.open(img_path).convert("RGB")
    if max(img.size) > MAX_IMAGE_DIM:
        img.thumbnail((MAX_IMAGE_DIM, MAX_IMAGE_DIM), Image.LANCZOS)
    return img


def _pil_to_part(img: Image.Image) -> types.Part:
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return types.Part(
        inline_data=types.Blob(mime_type="image/jpeg", data=buf.getvalue())
    )


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        # remove first fence line
        first_nl = t.find("\n")
        if first_nl >= 0:
            t = t[first_nl + 1 :]
    if t.endswith("```"):
        t = t[:-3]
    return t.strip()


def call_vlm_json(
    prompt: str,
    img: Image.Image,
    *,
    model: Optional[str] = None,
    retries: int = 3,
    temperature: float = 0.1,
) -> dict:
    """Call Gemini VLM expecting a JSON response. Returns parsed dict + usage."""
    model_name = model or DEFAULT_MODEL
    client = _client()
    contents = [
        types.Content(
            role="user",
            parts=[types.Part(text=prompt), _pil_to_part(img)],
        )
    ]
    cfg = types.GenerateContentConfig(
        temperature=temperature,
        response_modalities=["TEXT"],
    )
    last_err = None
    last_text = ""
    for attempt in range(1, retries + 1):
        try:
            resp = client.models.generate_content(
                model=model_name, contents=contents, config=cfg
            )
            last_text = resp.text or ""
            cleaned = _strip_fences(last_text)
            data = json.loads(cleaned)
            usage = {}
            try:
                u = resp.usage_metadata
                usage = {
                    "input_tokens": getattr(u, "prompt_token_count", None),
                    "output_tokens": getattr(u, "candidates_token_count", None),
                    "total_tokens": getattr(u, "total_token_count", None),
                }
            except Exception:
                pass
            return {
                "data": data,
                "usage": usage,
                "model": model_name,
                "raw_text": last_text,
            }
        except json.JSONDecodeError as e:
            last_err = e
            if attempt < retries:
                time.sleep(2 * attempt)
                continue
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            # backoff longer on rate-limit / 5xx
            wait = 5 * attempt if any(x in msg for x in ("429", "rate", "503", "500")) else 2 * attempt
            if attempt < retries:
                time.sleep(wait)
                continue
    raise VLMError(
        f"VLM JSON call failed after {retries} attempts: {last_err}\n"
        f"raw[:300]: {last_text[:300]}"
    )


__all__ = [
    "DEFAULT_MODEL",
    "VLMError",
    "preprocess",
    "call_vlm_json",
]
