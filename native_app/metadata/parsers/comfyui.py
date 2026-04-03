from __future__ import annotations

import json
from typing import Any

from ..models import GeneratorType, ImageMetadata
from .base import BaseMetadataParser


class ComfyUIParser(BaseMetadataParser):
    """Parser for ComfyUI metadata.

    ComfyUI stores two tEXt chunks:
    - ``prompt``: JSON dict mapping node IDs to node definitions
      (class_type, inputs). This is the *execution graph*.
    - ``workflow``: Full workflow JSON (optional, much larger).
    """

    def can_parse(self, chunks: dict[str, str]) -> bool:
        prompt_str = chunks.get("prompt", "")
        if not prompt_str:
            return False
        try:
            data = json.loads(prompt_str)
            if not isinstance(data, dict):
                return False
            # ComfyUI prompt JSON has node IDs as keys, each with class_type
            sample = next(iter(data.values()), None)
            return isinstance(sample, dict) and "class_type" in sample
        except (json.JSONDecodeError, StopIteration):
            return False

    def parse(self, chunks: dict[str, str], image_path: str = "") -> ImageMetadata:
        prompt_str = chunks.get("prompt", "")
        workflow_str = chunks.get("workflow", "")
        nodes: dict[str, Any] = {}
        try:
            nodes = json.loads(prompt_str)
        except json.JSONDecodeError:
            pass

        positive = ""
        negative = ""
        params: dict[str, str] = {}
        model_name = ""

        # Walk nodes to extract meaningful data
        for node_id, node in nodes.items():
            if not isinstance(node, dict):
                continue
            class_type = node.get("class_type", "")
            inputs = node.get("inputs", {})

            # KSampler / KSamplerAdvanced — generation parameters
            if "KSampler" in class_type:
                for key in ("steps", "cfg", "sampler_name", "scheduler", "seed", "denoise"):
                    val = inputs.get(key)
                    if val is not None and not isinstance(val, (list, dict)):
                        params[key] = str(val)

                # Resolve positive/negative conditioning nodes
                pos_ref = inputs.get("positive")
                neg_ref = inputs.get("negative")
                if isinstance(pos_ref, list) and pos_ref:
                    positive = positive or self._resolve_text(nodes, pos_ref[0])
                if isinstance(neg_ref, list) and neg_ref:
                    negative = negative or self._resolve_text(nodes, neg_ref[0])

            # CLIPTextEncode — direct text (fallback if not resolved via KSampler)
            if class_type == "CLIPTextEncode" and not positive:
                text = inputs.get("text", "")
                if isinstance(text, str) and text:
                    positive = text

            # Checkpoint loader — model name
            if "CheckpointLoader" in class_type or "CheckpointLoaderSimple" in class_type:
                ckpt = inputs.get("ckpt_name", "")
                if isinstance(ckpt, str) and ckpt:
                    model_name = model_name or ckpt

        return ImageMetadata(
            generator=GeneratorType.COMFYUI,
            positive_prompt=positive,
            negative_prompt=negative,
            parameters=params,
            model_name=model_name,
            raw_chunks=dict(chunks),
            workflow_json=workflow_str,
        )

    @staticmethod
    def _resolve_text(nodes: dict[str, Any], node_id: str) -> str:
        """Follow a node reference to extract text content."""
        node = nodes.get(str(node_id), {})
        if not isinstance(node, dict):
            return ""
        inputs = node.get("inputs", {})
        text = inputs.get("text", "")
        if isinstance(text, str):
            return text
        # text might be a reference to another node (e.g. string concat)
        if isinstance(text, list) and text:
            return ComfyUIParser._resolve_text(nodes, str(text[0]))
        return ""
