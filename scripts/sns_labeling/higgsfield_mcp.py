"""Higgsfield MCP handoff plan for product-grounded IMC generation.

The desktop session may not always expose `mcp__higgsfield__...` tools. This
module still lets the pipeline treat HF GPT-image 2 and HF Marketing Studio as
first-class provider options by writing a deterministic MCP execution plan.
When Higgsfield MCP is connected, the plan contains every prompt, media input,
model id, and expected output path needed to fill the gallery cells.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from sns_labeling.image_gen import build_prompt_from_imc_scene
from sns_labeling.product_grounding import product_image_paths


HF_PROVIDER_MODELS = {
    "hf_gpt": {
        "model": "gpt_image_2",
        "label": "HF GPT-image 2",
        "suffix": "_hf_gpt.png",
    },
    "hf_mkt": {
        "model": "marketing_studio_image",
        "label": "HF Marketing Studio",
        "suffix": "_hf_mkt.png",
    },
}


def _norm(path: Path | str) -> str:
    return str(Path(path)).replace("\\", "/")


def write_hf_mcp_plan(
    spec,
    refs_by_scene: dict[str, list[dict]],
    out_dir: Path,
    *,
    providers: list[str],
    moments_by_key: Optional[dict[str, str]] = None,
    outfit_manifest: Optional[dict] = None,
) -> dict:
    """Write JSON/Markdown plans for Higgsfield MCP execution."""
    hf_providers = [p for p in providers if p in HF_PROVIDER_MODELS]
    moments_by_key = moments_by_key or {}
    products = product_image_paths(outfit_manifest)
    tasks: list[dict] = []

    for scene in spec.scenes:
        for ref in refs_by_scene.get(scene.slug, []) or []:
            rank = ref.get("rank") or 1
            unit_id = f"{scene.slug}_R{rank:02d}"
            prompt = build_prompt_from_imc_scene(
                scene,
                spec,
                ref,
                moment=moments_by_key.get(f"{scene.slug}__{ref.get('post_id')}"),
                outfit_manifest=outfit_manifest,
            )
            prompt_path = out_dir / f"{unit_id}_prompt.txt"
            if not prompt_path.exists():
                prompt_path.write_text(prompt, encoding="utf-8")

            media_paths = [Path(ref.get("image") or ""), *products]
            media_paths = [p for p in media_paths if p.exists()]
            for provider in hf_providers:
                meta = HF_PROVIDER_MODELS[provider]
                output_path = out_dir / f"{unit_id}{meta['suffix']}"
                tasks.append({
                    "unit_id": unit_id,
                    "scene_id": scene.slug,
                    "rank": rank,
                    "provider": provider,
                    "provider_label": meta["label"],
                    "model": meta["model"],
                    "aspect_ratio": "3:4",
                    "prompt_file": _norm(prompt_path),
                    "prompt": prompt,
                    "media_order": [
                        "image_1_influencer_reference_pose_composition",
                        "image_2_selected_product_fit_length_only",
                    ][:len(media_paths)],
                    "media_paths": [_norm(p) for p in media_paths],
                    "expected_output": _norm(output_path),
                })

    plan = {
        "schema_version": "higgsfield-mcp-plan-1.0",
        "status": "pending_mcp_execution",
        "reason": "Higgsfield MCP tools are not exposed in this session; run this plan in a session with mcp__higgsfield__ tools.",
        "campaign_id": spec.campaign_id,
        "brand": spec.brand,
        "season": spec.season,
        "providers": hf_providers,
        "models": {p: HF_PROVIDER_MODELS[p]["model"] for p in hf_providers},
        "instructions": [
            "Call mcp__higgsfield__balance before starting.",
            "Upload all unique media_paths via mcp__higgsfield__media_upload, PUT bytes, then media_confirm.",
            "For each task, call mcp__higgsfield__generate_image with params.model, params.prompt, aspect_ratio='3:4', and medias in media_order.",
            "Poll mcp__higgsfield__job_status(sync=true).",
            "Download results.rawUrl to expected_output.",
            "Re-run python scripts/build_run_gallery.py --run-dir <run_dir> --imc --no-open.",
        ],
        "tasks": tasks,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "higgsfield_mcp_plan.json"
    md_path = out_dir / "higgsfield_mcp_plan.md"
    json_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Higgsfield MCP Plan",
        "",
        f"- Campaign: `{spec.campaign_id}`",
        f"- Providers: `{', '.join(hf_providers)}`",
        f"- Tasks: `{len(tasks)}`",
        "",
        "## Models",
    ]
    for p in hf_providers:
        lines.append(f"- `{p}` → `{HF_PROVIDER_MODELS[p]['model']}` ({HF_PROVIDER_MODELS[p]['label']})")
    lines += [
        "",
        "## MCP Sequence",
        "1. `mcp__higgsfield__balance`",
        "2. `mcp__higgsfield__media_upload` for all unique media paths",
        "3. PUT each local file to its signed upload URL",
        "4. `mcp__higgsfield__media_confirm(type=\"image\", media_ids=[...])`",
        "5. `mcp__higgsfield__generate_image` for each task, max 4 concurrent",
        "6. `mcp__higgsfield__job_status(sync=true)`",
        "7. Download `rawUrl` to `expected_output`",
        "8. Rebuild gallery",
        "",
        "## Tasks",
    ]
    for t in tasks:
        lines += [
            f"### {t['unit_id']} · {t['provider_label']}",
            f"- model: `{t['model']}`",
            f"- output: `{t['expected_output']}`",
            f"- prompt: `{t['prompt_file']}`",
            "- media:",
            *[f"  - `{role}`: `{path}`" for role, path in zip(t["media_order"], t["media_paths"])],
            "",
        ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    plan["plan_json"] = _norm(json_path)
    plan["plan_md"] = _norm(md_path)
    return plan


__all__ = ["HF_PROVIDER_MODELS", "write_hf_mcp_plan"]
