from __future__ import annotations

from pathlib import Path

from PyQt6.QtGui import QFont, QFontDatabase


FONT_PREFERENCE = [
    'Noto Sans CJK SC',
    'Noto Sans SC',
    'Microsoft YaHei UI',
    'Segoe UI',
    'Quicksand',
]

FONT_PROFILES: dict[str, list[str]] = {
    'default': ['Noto Sans CJK SC', 'Noto Sans SC', 'Microsoft YaHei UI', 'Segoe UI'],
    'yahei': ['Microsoft YaHei UI', 'Segoe UI'],
    'segoe': ['Segoe UI', 'Microsoft YaHei UI'],
}


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
    all_known = QFontDatabase.families()
    chosen = [family for family in families if family in all_known]
    font = QFont()
    if chosen:
        font.setFamilies(chosen)
        font.setFamily(chosen[0])
    font.setPointSize(point_size)
    font.setWeight(QFont.Weight.Normal)
    return font
