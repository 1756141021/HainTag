from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import IO


@dataclass(frozen=True)
class TagInfo:
    name: str
    translation: str
    category_id: int
    count: int
    aliases: tuple[str, ...]
    group: str
    subgroup: str


class TagDictionary:
    """Loads a Danbooru CSV tag dictionary and provides O(1) translation lookup.

    CSV format: tag_name, category_id, count, aliases, translation, group, subgroup
    Aliases are also indexed so looking up any alias returns the same translation.
    """

    def __init__(self) -> None:
        self._entries: dict[str, TagInfo] = {}
        self._alias_map: dict[str, str] = {}
        self._lazy_paths: list[Path] = []
        self._loaded: bool = False

    def queue_csv(self, path: str | Path) -> None:
        """Defer CSV load until first lookup. Multiple paths queue and merge on first use."""
        p = Path(path)
        if p.exists():
            self._lazy_paths.append(p)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        for p in self._lazy_paths:
            with open(p, 'r', encoding='utf-8-sig') as f:
                self._parse(f)
        self._lazy_paths.clear()

    def load_csv(self, path: str | Path) -> None:
        """Load a Danbooru CSV dictionary. Can be called multiple times to merge sources."""
        path = Path(path)
        if not path.exists():
            return
        with open(path, 'r', encoding='utf-8-sig') as f:
            self._parse(f)
        self._loaded = True

    def _parse(self, f: IO[str]) -> None:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 5:
                continue
            tag_name = self._normalize(row[0])
            if not tag_name:
                continue
            try:
                category_id = int(row[1])
            except (ValueError, IndexError):
                category_id = 0
            try:
                count = int(row[2])
            except (ValueError, IndexError):
                count = 0
            raw_aliases = row[3] if len(row) > 3 else ''
            translation = row[4].strip() if len(row) > 4 else ''
            group = row[5].strip() if len(row) > 5 else ''
            subgroup = row[6].strip() if len(row) > 6 else ''

            aliases = tuple(
                self._normalize(a) for a in raw_aliases.split(',') if self._normalize(a)
            )

            info = TagInfo(
                name=tag_name,
                translation=translation,
                category_id=category_id,
                count=count,
                aliases=aliases,
                group=group,
                subgroup=subgroup,
            )
            self._entries[tag_name] = info
            for alias in aliases:
                if alias not in self._entries:
                    self._alias_map[alias] = tag_name

    @staticmethod
    def _normalize(tag: str) -> str:
        return tag.strip().lower().replace(' ', '_')

    def translate(self, tag: str) -> str | None:
        """Return Chinese translation for a tag, or None if not found."""
        info = self.lookup(tag)
        return info.translation if info and info.translation else None

    def lookup(self, tag: str) -> TagInfo | None:
        """Return full TagInfo for a tag (including via alias lookup)."""
        self._ensure_loaded()
        key = self._normalize(tag)
        info = self._entries.get(key)
        if info is not None:
            return info
        canonical = self._alias_map.get(key)
        if canonical is not None:
            return self._entries.get(canonical)
        return None

    def search_prefix(self, prefix: str, limit: int = 15) -> list[TagInfo]:
        """Return tags matching *prefix*, ranked by count.

        ASCII queries: prefix-match `name` and `aliases` (English tag lookup).
        CJK queries: substring-match `translation` (Chinese has no natural prefix
        boundary — "女孩" should match both "1个女孩" and "女孩子").
        """
        self._ensure_loaded()
        if not prefix or not prefix.strip():
            return []
        if self._is_cjk(prefix):
            needle = prefix.strip()
            results: dict[str, TagInfo] = {}
            for name, info in self._entries.items():
                if info.translation and needle in info.translation:
                    results[name] = info
            ranked = sorted(results.values(), key=lambda t: t.count, reverse=True)
            return ranked[:limit]
        normalized = self._normalize(prefix)
        if not normalized:
            return []
        results = {}
        for name, info in self._entries.items():
            if name.startswith(normalized):
                results[name] = info
            else:
                for alias in info.aliases:
                    if alias.startswith(normalized):
                        results[name] = info
                        break
        ranked = sorted(results.values(), key=lambda t: t.count, reverse=True)
        return ranked[:limit]

    @staticmethod
    def _is_cjk(text: str) -> bool:
        for ch in text:
            o = ord(ch)
            # CJK Unified Ideographs, CJK Extension A, Hiragana, Katakana, Hangul
            if 0x3040 <= o <= 0x30FF or 0x3400 <= o <= 0x9FFF or 0xAC00 <= o <= 0xD7AF:
                return True
        return False

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, tag: str) -> bool:
        return self.lookup(tag) is not None
