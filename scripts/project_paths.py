"""Project-local path helpers for Strategy Cut Builder.

The original pipeline was usually nested as ``st_cut-dev/scripts`` inside a
larger workspace. This repo is also useful as a standalone checkout, so every
runtime path should resolve from the nearest folder that actually contains the
project assets.
"""
from __future__ import annotations

import os
from pathlib import Path


def find_project_root(start: str | Path | None = None) -> Path:
    """Return the repo/project root containing ``scripts`` and ``brand-dna``.

    ``start`` can be a file or directory. The function walks upward and picks
    the first directory that looks like this project. It intentionally avoids
    assuming a folder name such as ``st_cut-dev`` or ``content_builder``.
    """
    p = Path(start or __file__).resolve()
    if p.is_file():
        p = p.parent

    for cur in (p, *p.parents):
        if (cur / "scripts").is_dir() and (cur / "brand-dna").is_dir():
            return cur

    # Conservative fallback for unusual packaging. From scripts/project_paths.py
    # this lands at the checkout root.
    return Path(__file__).resolve().parents[1]


PROJECT_ROOT = find_project_root(__file__)


def env_path(name: str, default: Path) -> Path:
    """Resolve a path override from an environment variable, if set."""
    raw = os.getenv(name)
    if not raw:
        return default
    return Path(raw).expanduser().resolve()


BRAND_DNA_DIR = env_path("STRATEGY_CUT_BRAND_DNA_DIR", PROJECT_ROOT / "brand-dna")
RESULTS_DIR = env_path("STRATEGY_CUT_RESULTS_DIR", PROJECT_ROOT / "results")
SOURCE_DIR = env_path(
    "STRATEGY_CUT_SOURCE_DIR",
    PROJECT_ROOT / "source" / "sns-influencer-output",
)
PRODUCTS_DIR = env_path("STRATEGY_CUT_PRODUCTS_DIR", PROJECT_ROOT / "products_resource")


def resolve_project_path(path: str | Path, *, base: Path | None = None) -> Path:
    """Resolve relative paths from ``base`` or the project root."""
    p = Path(path)
    if p.is_absolute():
        return p
    return (base or PROJECT_ROOT) / p


__all__ = [
    "PROJECT_ROOT",
    "BRAND_DNA_DIR",
    "RESULTS_DIR",
    "SOURCE_DIR",
    "PRODUCTS_DIR",
    "env_path",
    "find_project_root",
    "resolve_project_path",
]
