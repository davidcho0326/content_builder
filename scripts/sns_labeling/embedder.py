"""Gemini text-embedding helper + cache loader.

No image input — pure text. Used by:
  - embed_pool.py (one-time encode of 5,774 SNS records)
  - mood_query (query-time encoding of brand_dna text)

Env:
    GEMINI_API_KEY                — required
    F_AND_F_EMBEDDING_MODEL       — default "gemini-embedding-2"
                                    (GA 2026-03, 3072-dim, Matryoshka 128~3072)
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import types

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from project_paths import SOURCE_DIR

load_dotenv()

DEFAULT_MODEL = os.getenv("F_AND_F_EMBEDDING_MODEL", "gemini-embedding-2")
CACHE_PATH = SOURCE_DIR / "_pool_embeddings.npz"


class EmbedderError(RuntimeError):
    pass


def _client():
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise EmbedderError("GEMINI_API_KEY not set")
    return genai.Client(api_key=key)


def embed_texts(texts: list[str], *, model: Optional[str] = None,
                task_type: str = "SEMANTIC_SIMILARITY",
                batch_size: int = 100, retries: int = 3) -> np.ndarray:
    """Embed a list of texts → np.float32 (N, D) array.

    Gemini embed_content supports batching internally; we still chunk to keep
    per-call latency bounded and to recover from partial errors.
    """
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    model_name = model or DEFAULT_MODEL
    client = _client()
    cfg = types.EmbedContentConfig(task_type=task_type)

    out: list[np.ndarray] = []
    for start in range(0, len(texts), batch_size):
        chunk = texts[start: start + batch_size]
        last_err: Optional[Exception] = None
        for attempt in range(1, retries + 1):
            try:
                resp = client.models.embed_content(
                    model=model_name, contents=chunk, config=cfg,
                )
                vecs = [np.array(e.values, dtype=np.float32) for e in resp.embeddings]
                out.append(np.stack(vecs))
                break
            except Exception as e:
                last_err = e
                msg = str(e).lower()
                wait = 5 * attempt if any(x in msg for x in ("429", "rate", "503", "500")) else 2 * attempt
                if attempt < retries:
                    time.sleep(wait)
        else:
            raise EmbedderError(f"embed_content failed after {retries}: {last_err}")

    return np.vstack(out)


def embed_text(text: str, *, model: Optional[str] = None,
               task_type: str = "SEMANTIC_SIMILARITY") -> np.ndarray:
    """Single-text convenience wrapper."""
    arr = embed_texts([text], model=model, task_type=task_type, batch_size=1)
    return arr[0] if len(arr) > 0 else np.zeros(0, dtype=np.float32)


def load_cache(path: Path | str = CACHE_PATH) -> tuple[dict[str, int], np.ndarray]:
    """Load post_id → row_index map and N×D embedding matrix.

    Returns ({}, empty) if cache missing — callers fall back to discrete-only.
    """
    p = Path(path)
    if not p.exists():
        return {}, np.zeros((0, 0), dtype=np.float32)
    data = np.load(p, allow_pickle=False)
    ids = list(data["post_ids"])
    vecs = data["vectors"].astype(np.float32, copy=False)
    return {pid: i for i, pid in enumerate(ids)}, vecs


def save_cache(post_ids: list[str], vectors: np.ndarray,
               path: Path | str = CACHE_PATH) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(p, post_ids=np.array(post_ids), vectors=vectors)


def cosine_similarity(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Cosine similarity of one query vector vs N row vectors."""
    if query.size == 0 or matrix.size == 0:
        return np.zeros(matrix.shape[0] if matrix.ndim == 2 else 0, dtype=np.float32)
    q = query / (np.linalg.norm(query) + 1e-9)
    m_norm = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9
    return (matrix / m_norm) @ q


__all__ = [
    "DEFAULT_MODEL",
    "CACHE_PATH",
    "EmbedderError",
    "embed_text",
    "embed_texts",
    "load_cache",
    "save_cache",
    "cosine_similarity",
]
