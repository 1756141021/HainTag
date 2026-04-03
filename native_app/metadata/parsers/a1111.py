from __future__ import annotations

import re

from ..models import GeneratorType, ImageMetadata
from .base import BaseMetadataParser

_LORA_RE = re.compile(r"<lora:([^:>]+):([^>]+)>")


class A1111Parser(BaseMetadataParser):
    """Parser for Stable Diffusion WebUI (A1111 / Forge) metadata.

    A1111 stores everything in a single ``parameters`` tEXt chunk:

        {positive prompt}
        Negative prompt: {negative prompt}
        Steps: {steps}, Sampler: {sampler}, CFG scale: {cfg}, Seed: {seed}, ...
    """

    def can_parse(self, chunks: dict[str, str]) -> bool:
        text = chunks.get("parameters", "")
        return bool(text and "Steps:" in text)

    def parse(self, chunks: dict[str, str], image_path: str = "") -> ImageMetadata:
        text = chunks.get("parameters", "")

        positive = ""
        negative = ""
        params: dict[str, str] = {}
        loras: list[dict[str, str]] = []

        # Split on the last "Steps: " line to separate params from prompts
        steps_idx = text.rfind("\nSteps:")
        if steps_idx == -1:
            steps_idx = text.rfind("Steps:")
        if steps_idx != -1:
            prompt_block = text[:steps_idx].strip()
            params_line = text[steps_idx:].strip()
        else:
            prompt_block = text.strip()
            params_line = ""

        # Split prompt block into positive / negative
        neg_marker = "\nNegative prompt:"
        neg_idx = prompt_block.find(neg_marker)
        if neg_idx == -1:
            neg_marker = "Negative prompt:"
            neg_idx = prompt_block.find(neg_marker)
        if neg_idx != -1:
            positive = prompt_block[:neg_idx].strip()
            negative = prompt_block[neg_idx + len(neg_marker):].strip()
        else:
            positive = prompt_block

        # Parse params key-value pairs: "Steps: 50, Sampler: Euler a, CFG scale: 2.8, ..."
        # Handle quoted values (e.g. Lora hashes: "name: hash, name2: hash2")
        if params_line:
            for match in re.finditer(
                r'([\w][\w ]*?):\s*("(?:[^"\\]|\\.)*"|[^,]*?)(?:,\s*(?=[\w][\w ]*?:)|$)',
                params_line,
            ):
                key = match.group(1).strip()
                value = match.group(2).strip()
                params[key] = value

        # Extract LoRAs from positive prompt
        for match in _LORA_RE.finditer(positive):
            loras.append({"name": match.group(1), "weight": match.group(2)})

        # Extract LoRA hashes if present — value is quoted: "name: hash, name2: hash2"
        lora_hashes_str = params.pop("Lora hashes", "")
        if lora_hashes_str:
            # Strip surrounding quotes
            inner = lora_hashes_str.strip('"')
            # Split on ", " followed by a non-hex char (hash values are hex)
            for item in re.split(r",\s*(?=[^0-9a-fA-F])", inner):
                item = item.strip()
                if ":" in item:
                    name, _, hash_val = item.partition(":")
                    name = name.strip()
                    hash_val = hash_val.strip()
                    for lora in loras:
                        if lora["name"] == name:
                            lora["hash"] = hash_val
                            break

        return ImageMetadata(
            generator=GeneratorType.A1111,
            positive_prompt=positive,
            negative_prompt=negative,
            parameters=params,
            loras=loras,
            model_name=params.get("Model", ""),
            model_hash=params.get("Model hash", ""),
            raw_chunks=dict(chunks),
            workflow_json=chunks.get("workflow", ""),
        )
