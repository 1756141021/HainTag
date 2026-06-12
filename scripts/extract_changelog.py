"""打印 CHANGELOG.md 中指定版本的段落（发版 workflow 用来生成 release body）。

用法：python scripts/extract_changelog.py 0.10.0
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: extract_changelog.py <version>", file=sys.stderr)
        return 2
    version = sys.argv[1].lstrip("vV")
    changelog = Path(__file__).resolve().parents[1] / "CHANGELOG.md"
    text = changelog.read_text(encoding="utf-8")
    match = re.search(
        rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        print(f"no CHANGELOG section for version {version}", file=sys.stderr)
        return 1
    sys.stdout.reconfigure(encoding="utf-8")
    print(match.group(1).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
