"""Infer ComfyUI model requirements from workflow API JSON."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from comfy_agent.runpod import RunPodError


MODEL_REGISTRY: dict[tuple[str, str], dict[str, str]] = {
    ("diffusion_models", "z_image_turbo_bf16.safetensors"): {
        "url": "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/diffusion_models/z_image_turbo_bf16.safetensors",
    },
    ("diffusion_models", "z_image_turbo_nvfp4.safetensors"): {
        "url": "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/diffusion_models/z_image_turbo_nvfp4.safetensors",
    },
    ("text_encoders", "qwen_3_4b.safetensors"): {
        "url": "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/text_encoders/qwen_3_4b.safetensors",
    },
    ("text_encoders", "qwen_3_4b_fp4_mixed.safetensors"): {
        "url": "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/text_encoders/qwen_3_4b_fp4_mixed.safetensors",
    },
    ("text_encoders", "qwen_3_4b_fp8_mixed.safetensors"): {
        "url": "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/text_encoders/qwen_3_4b_fp8_mixed.safetensors",
    },
    ("vae", "ae.safetensors"): {
        "url": "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/vae/ae.safetensors",
    },
}


LOADER_INPUTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "UNETLoader": ("diffusion_models", ("unet_name",)),
    "CLIPLoader": ("text_encoders", ("clip_name",)),
    "DualCLIPLoader": ("text_encoders", ("clip_name1", "clip_name2")),
    "TripleCLIPLoader": ("text_encoders", ("clip_name1", "clip_name2", "clip_name3")),
    "VAELoader": ("vae", ("vae_name",)),
    "LoraLoader": ("loras", ("lora_name",)),
    "CheckpointLoaderSimple": ("checkpoints", ("ckpt_name",)),
}


def comfy_model_path(comfy_dir: str, folder: str, filename: str) -> str:
    return str(Path(comfy_dir) / "models" / folder / filename)


def iter_workflow_model_refs(workflow: dict[str, Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type", ""))
        loader = LOADER_INPUTS.get(class_type)
        if not loader:
            continue
        folder, input_names = loader
        inputs = node.get("inputs") or {}
        for input_name in input_names:
            filename = inputs.get(input_name)
            if not isinstance(filename, str) or not filename:
                continue
            refs.append(
                {
                    "node_id": str(node_id),
                    "class_type": class_type,
                    "input_name": input_name,
                    "folder": folder,
                    "filename": filename,
                }
            )
    return refs


def extract_workflow_models(workflow: dict[str, Any], comfy_dir: str) -> list[dict[str, str]]:
    models: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    missing: list[str] = []

    for ref in iter_workflow_model_refs(workflow):
        folder = ref["folder"]
        filename = ref["filename"]
        key = (folder, filename)
        if key in seen:
            continue
        seen.add(key)
        registry_entry = MODEL_REGISTRY.get(key)
        if not registry_entry:
            missing.append(
                f"node {ref['node_id']} {ref['class_type']}.{ref['input_name']}: {folder}/{filename}"
            )
            continue
        models.append(
            {
                "name": Path(filename).stem,
                "path": comfy_model_path(comfy_dir, folder, filename),
                "url": registry_entry["url"],
                "source": f"workflow node {ref['node_id']} {ref['class_type']}.{ref['input_name']}",
            }
        )

    if missing:
        details = "\n".join(f"- {item}" for item in missing)
        raise RunPodError(f"workflow uses models that are not in MODEL_REGISTRY:\n{details}")
    return models
