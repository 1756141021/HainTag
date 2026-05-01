from __future__ import annotations

import math
import re
from typing import Iterable

from .models import ExampleEntry, OCEntry, PromptEntry


def normalize_api_base_url(raw: str) -> str:
    value = raw.strip().rstrip("/")
    if value.endswith("/chat/completions"):
        value = value[: -len("/chat/completions")]
    return value


def extract_active_input(text: str, memory_mode: bool) -> str:
    content = text.strip()
    if memory_mode:
        return content
    parts = [part.strip() for part in content.split("---")]
    return parts[-1] if parts else ""


def validate_examples(examples: Iterable[ExampleEntry]) -> list[str]:
    errors: list[str] = []
    for example in examples:
        has_desc = bool(example.description.strip())
        has_tags = bool(example.tags.strip())
        if has_desc != has_tags:
            errors.append("Each example must include both Description and Tags")
    return errors


def _format_example(entry: ExampleEntry, index: int) -> str:
    """Format an example entry as a single assistant message."""
    return f"例图{index}：\n画面描述：{entry.description.strip()}\n```\n{entry.tags.strip()}\n```"


def _entry_block(entry, example_index: int) -> tuple[list[dict[str, str]], int]:
    if isinstance(entry, PromptEntry):
        return ([{"role": entry.role, "content": entry.content}], example_index)
    if isinstance(entry, OCEntry):
        desc = f"Character: {entry.character_name}" if entry.character_name else "Character reference"
        return (
            [
                {"role": "user", "content": desc},
                {"role": "assistant", "content": entry.merged_tags()},
            ],
            example_index,
        )
    example_index += 1
    return ([{"role": "assistant", "content": _format_example(entry, example_index)}], example_index)


def build_messages(
    prompts: list[PromptEntry],
    examples: list[ExampleEntry],
    input_text: str,
    memory_mode: bool,
    ocs: list[OCEntry] | None = None,
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    active_input = extract_active_input(input_text, memory_mode)
    prompt_items = [item for item in prompts if item.enabled and item.content.strip()]
    example_items = [item for item in examples if item.description.strip() and item.tags.strip()]
    oc_items = [oc for oc in (ocs or []) if oc.enabled and oc.merged_tags().strip()]

    entries: list = sorted(
        [*prompt_items, *example_items, *oc_items],
        key=lambda item: getattr(item, "order", 0),
    )

    messages: list[dict[str, str]] = []

    if memory_mode and history:
        for item in history:
            role = str(item.get("role", "")).strip()
            content = str(item.get("content", "")).strip()
            if role in {"system", "user", "assistant"} and content:
                messages.append({"role": role, "content": content})

    history_floor = len(messages)

    if active_input:
        messages.append({"role": "user", "content": active_input})

    from collections import defaultdict
    by_depth: dict[int, list[dict[str, str]]] = defaultdict(list)
    example_counter = 0
    for entry in entries:
        d = max(0, getattr(entry, "depth", 0))
        block, example_counter = _entry_block(entry, example_counter)
        by_depth[d].extend(block)

    above_history_end = 0
    for depth in sorted(by_depth, reverse=True):
        group = by_depth[depth]
        raw = len(messages) - depth
        if raw >= history_floor:
            insert_at = raw
        else:
            insert_at = above_history_end
            above_history_end += len(group)
            history_floor += len(group)
        messages[insert_at:insert_at] = group

    return messages


_WORD_RE = re.compile(r"[A-Za-z0-9_'-]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def estimate_text_tokens(text: str) -> int:
    cjk_count = len(_CJK_RE.findall(text))
    word_count = len(_WORD_RE.findall(text))
    other_count = max(0, len(text) - cjk_count - sum(len(match.group(0)) for match in _WORD_RE.finditer(text)))
    estimate = cjk_count * 2.0 + word_count * 1.3 + other_count * 0.4
    return max(1, math.ceil(estimate)) if text.strip() else 0


def estimate_messages_tokens(messages: list[dict[str, str]]) -> int:
    total = 0
    for message in messages:
        total += 4
        total += estimate_text_tokens(message.get("content", ""))
    return total + 2 if messages else 0
