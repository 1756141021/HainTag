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


def build_messages(
    prompts: list[PromptEntry],
    examples: list[ExampleEntry],
    input_text: str,
    memory_mode: bool,
    ocs: list[OCEntry] | None = None,
) -> list[dict[str, str]]:
    active_input = extract_active_input(input_text, memory_mode)
    prompt_items = [item for item in prompts if item.enabled and item.content.strip()]
    example_items = [item for item in examples if item.description.strip() and item.tags.strip()]
    oc_items = [oc for oc in (ocs or []) if oc.enabled and oc.tags.strip()]

    entries: list = sorted(
        [*prompt_items, *example_items, *oc_items],
        key=lambda item: getattr(item, "order", 0),
    )

    depth_zero = [item for item in entries if getattr(item, "depth", 0) == 0]
    depth_nonzero = [item for item in entries if getattr(item, "depth", 0) > 0]

    # Track example index for formatting
    example_counter = 0
    messages: list[dict[str, str]] = []

    for entry in depth_zero:
        if isinstance(entry, PromptEntry):
            messages.append({"role": entry.role, "content": entry.content})
        elif isinstance(entry, OCEntry):
            desc = f"Character: {entry.character_name}" if entry.character_name else "Character reference"
            messages.append({"role": "user", "content": desc})
            messages.append({"role": "assistant", "content": entry.merged_tags()})
        else:
            example_counter += 1
            messages.append({"role": "assistant", "content": _format_example(entry, example_counter)})

    if active_input:
        messages.append({"role": "user", "content": active_input})

    # Insert depth>0 entries: group by depth, keep Order within each group,
    # then splice each group into the message list at once.
    from collections import defaultdict
    by_depth: dict[int, list[dict[str, str]]] = defaultdict(list)
    for entry in depth_nonzero:  # already sorted by Order ascending
        d = getattr(entry, "depth", 0)
        if isinstance(entry, PromptEntry):
            by_depth[d].append({"role": entry.role, "content": entry.content})
        elif isinstance(entry, OCEntry):
            desc = f"Character: {entry.character_name}" if entry.character_name else "Character reference"
            by_depth[d].append({"role": "user", "content": desc})
            by_depth[d].append({"role": "assistant", "content": entry.merged_tags()})
        else:
            example_counter += 1
            by_depth[d].append({"role": "assistant", "content": _format_example(entry, example_counter)})
    # Insert largest depth first (farthest from user input) so positions stay stable
    for depth in sorted(by_depth, reverse=True):
        group = by_depth[depth]
        insert_at = max(0, len(messages) - depth)
        messages[insert_at:insert_at] = group  # splice the whole group at once

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
