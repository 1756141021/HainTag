from __future__ import annotations

import json
from pathlib import Path

from ..models import PromptEntry


class PromptStorage:
    def export_prompts(self, prompts: list[PromptEntry], target_path: str) -> None:
        data = [item.to_dict() for item in prompts]
        Path(target_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def import_prompts(self, source_path: str) -> list[PromptEntry]:
        data = json.loads(Path(source_path).read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("Prompt file must be a JSON array.")
        prompts: list[PromptEntry] = []
        for item in data:
            if not isinstance(item, dict):
                raise ValueError("Prompt entries must be JSON objects.")
            prompts.append(PromptEntry.from_dict(item))
        return prompts
