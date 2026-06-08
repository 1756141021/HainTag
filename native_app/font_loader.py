from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtGui import QFont, QFontDatabase


FONT_PREFERENCE = [
    'LXGW WenKai Screen',
    'Noto Sans CJK SC',
    'Noto Sans SC',
    'Microsoft YaHei UI',
    'Segoe UI',
]

FONT_PROFILES: dict[str, list[str]] = {
    'default': ['Noto Sans CJK SC', 'Noto Sans SC', 'Microsoft YaHei UI', 'Segoe UI'],
    'wenkai': ['LXGW WenKai Screen', 'Noto Sans CJK SC', 'Microsoft YaHei UI'],
    'yahei': ['Microsoft YaHei UI', 'Segoe UI'],
    'segoe': ['Segoe UI', 'Microsoft YaHei UI'],
}


def _system_ui_families() -> list[str]:
    """The native UI / CJK font(s) for the running platform.

    Appended as a guaranteed fallback so the app uses the system font where a
    profile's fonts are absent (the profiles list Windows fonts like
    'Microsoft YaHei UI' that don't exist on macOS).
    """
    if sys.platform == 'darwin':
        return ['PingFang SC', 'Helvetica Neue']
    if sys.platform == 'win32':
        return ['Microsoft YaHei UI', 'Segoe UI']
    return ['Noto Sans CJK SC', 'Noto Sans SC']


def font_family_css(profile: str, custom_family: str = '') -> str:
    """Build a QSS font-family value using only installed families.

    Filtering to fonts that actually exist avoids Qt's 'missing font family'
    warning and the alias-population cost it triggers, and the platform system
    font is appended so there's always a real CJK fallback.
    """
    if custom_family:
        wanted = [custom_family]
    else:
        wanted = list(FONT_PROFILES.get(profile, FONT_PROFILES['default']))
    wanted += _system_ui_families()
    known = set(QFontDatabase.families())
    seen: set[str] = set()
    families: list[str] = []
    for fam in wanted:
        if fam and fam not in seen and fam in known:
            seen.add(fam)
            families.append(fam)
    if not families:
        families = _system_ui_families()
    # End with a guaranteed-present real font rather than the generic
    # "sans-serif" keyword, which Qt's QSS parser reports as a missing family.
    return ', '.join(f'"{fam}"' for fam in families)


def load_app_fonts(resources_dir: Path) -> list[str]:
    fonts_dir = resources_dir / 'fonts'
    families: list[str] = []
    if not fonts_dir.exists():
        return families
    for path in sorted(fonts_dir.glob('*')):
        if path.suffix.lower() not in {'.ttf', '.otf'}:
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            continue
        families.extend(QFontDatabase.applicationFontFamilies(font_id))
    return families


def create_app_font(available_families: list[str]) -> QFont:
    chosen = [family for family in FONT_PREFERENCE if family in available_families or family in QFontDatabase.families()]
    font = QFont()
    if chosen:
        font.setFamilies(chosen)
        font.setFamily(chosen[0])
    font.setPointSize(11)
    font.setWeight(QFont.Weight.Normal)
    return font


def build_body_font(
    profile: str,
    point_size: int,
    custom_family: str = '',
) -> QFont:
    if profile == 'custom' and custom_family:
        families = [custom_family]
    else:
        families = list(FONT_PROFILES.get(profile, FONT_PROFILES['default']))
    families += _system_ui_families()
    all_known = QFontDatabase.families()
    chosen = [family for family in families if family in all_known]
    font = QFont()
    if chosen:
        font.setFamilies(chosen)
        font.setFamily(chosen[0])
    font.setPointSize(point_size)
    font.setWeight(QFont.Weight.Normal)
    return font
