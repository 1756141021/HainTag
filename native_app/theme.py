from __future__ import annotations

import re
from typing import Any

# ── Theme state (set by generate_qss, read by custom-painted widgets) ──
_is_light: bool = False
_current_palette: dict[str, str] = {}  # resolved palette after interpolation

# ── Palette definitions ──

DARK_PALETTE: dict[str, str] = {
    'bg': '#161615',
    'bg_top': '#1C1C1A',
    'bg_content': '#131312',
    'bg_workspace': '#0E0E0D',
    'bg_titlebar': '#1A1A18',
    'bg_surface': '#1E1E1C',
    'bg_input': '#0E0E0C',
    'bg_card': 'rgba(26, 26, 24, 0.82)',
    'bg_card_strip': 'rgba(22, 22, 20, 0.90)',
    'bg_card_strip_hover': 'rgba(32, 31, 29, 0.92)',
    'bg_dock': '#171716',
    'bg_settings_top': '#1E1E1C',
    'bg_settings': '#171716',
    'bg_prompt': '#141413',
    'bg_menu': 'rgba(22, 22, 20, 0.96)',
    'bg_backdrop': 'rgba(0, 0, 0, 0.24)',
    'text': '#F4F4F0',
    'text_body': '#C8C8C0',
    'text_muted': '#7A7A75',
    'text_dim': '#4A4A45',
    'text_label': '#8A8A82',
    'text_preview': '#D0D0C8',
    'line': 'rgba(244, 244, 240, 0.08)',
    'line_hover': 'rgba(244, 244, 240, 0.13)',
    'line_strong': 'rgba(244, 244, 240, 0.18)',
    'hover_bg': 'rgba(244, 244, 240, 0.06)',
    'hover_bg_strong': 'rgba(244, 244, 240, 0.10)',
    'accent': 'rgba(140, 150, 200, 0.25)',
    'accent_hover': 'rgba(140, 150, 200, 0.45)',
    'accent_text': '#B8BCD8',
    'accent_text_hover': '#D8DAF0',
    'accent_handle': '#7A7EA8',
    'accent_sub': 'rgba(140, 150, 200, 0.20)',
    'delete_hover': 'rgba(200, 60, 50, 0.35)',
    'close_hover': 'rgba(200, 60, 50, 0.65)',
    'selection_bg': 'rgba(140, 150, 200, 0.45)',
    'selection_text': '#F4F4F0',
    'disabled_text': '#5A5A55',
    'disabled_bg': 'rgba(244, 244, 240, 0.03)',
    'slider_groove': 'rgba(244, 244, 240, 0.07)',
    'slider_sub': 'rgba(140, 150, 200, 0.25)',
    'scrollbar': 'rgba(244, 244, 240, 0.10)',
    'dock_preview': 'rgba(140, 150, 200, 0.12)',
    'dock_preview_border': 'rgba(140, 150, 200, 0.50)',
    'corner_hint': 'rgba(244, 244, 240, 0.03)',
    'corner_hint_border': 'rgba(244, 244, 240, 0.05)',
    'edge_hover': 'rgba(140, 150, 200, 0.18)',
}

LIGHT_PALETTE: dict[str, str] = {
    'bg': '#F4F4F0',
    'bg_top': '#EEEEE8',
    'bg_content': '#E8E8E2',
    'bg_workspace': '#E2E2DC',
    'bg_titlebar': '#EEEEE8',
    'bg_surface': '#F4F4F0',
    'bg_input': '#FFFFFF',
    'bg_card': 'rgba(255, 255, 255, 0.82)',
    'bg_card_strip': 'rgba(248, 248, 244, 0.90)',
    'bg_card_strip_hover': 'rgba(240, 240, 234, 0.92)',
    'bg_dock': '#EAEAE4',
    'bg_settings_top': '#F0F0EA',
    'bg_settings': '#EAEAE4',
    'bg_prompt': '#F8F8F4',
    'bg_menu': 'rgba(244, 244, 240, 0.97)',
    'bg_backdrop': 'rgba(255, 255, 255, 0.22)',
    'text': '#111111',
    'text_body': '#333333',
    'text_muted': '#888888',
    'text_dim': '#AAAAAA',
    'text_label': '#666666',
    'text_preview': '#222222',
    'line': 'rgba(17, 17, 17, 0.08)',
    'line_hover': 'rgba(17, 17, 17, 0.14)',
    'line_strong': 'rgba(17, 17, 17, 0.20)',
    'hover_bg': 'rgba(17, 17, 17, 0.04)',
    'hover_bg_strong': 'rgba(17, 17, 17, 0.08)',
    'accent': 'rgba(80, 100, 180, 0.18)',
    'accent_hover': 'rgba(80, 100, 180, 0.35)',
    'accent_text': '#4A5A90',
    'accent_text_hover': '#3A4A80',
    'accent_handle': '#6A70A0',
    'accent_sub': 'rgba(80, 100, 180, 0.12)',
    'delete_hover': 'rgba(200, 60, 50, 0.24)',
    'close_hover': 'rgba(200, 60, 50, 0.55)',
    'selection_bg': 'rgba(80, 100, 180, 0.30)',
    'selection_text': '#111111',
    'disabled_text': '#BBBBBB',
    'disabled_bg': 'rgba(17, 17, 17, 0.03)',
    'slider_groove': 'rgba(17, 17, 17, 0.08)',
    'slider_sub': 'rgba(80, 100, 180, 0.25)',
    'scrollbar': 'rgba(17, 17, 17, 0.12)',
    'dock_preview': 'rgba(80, 100, 180, 0.10)',
    'dock_preview_border': 'rgba(80, 100, 180, 0.40)',
    'corner_hint': 'rgba(17, 17, 17, 0.03)',
    'corner_hint_border': 'rgba(17, 17, 17, 0.06)',
    'edge_hover': 'rgba(80, 100, 180, 0.15)',
}

# ── QSS template ──

_QSS_TEMPLATE = """
/* ── Global ── */
* {{
    font-family: {font_family};
    color: {text_body};
    outline: none;
}}

QWidget {{
    background: transparent;
}}

/* ── Window Shell ── */
#AppWindow {{
    background: transparent;
}}

#WindowSurface {{
    background: {bg};
    border: 1px solid {line};
    border-radius: 12px;
}}

#ContentHost {{
    background: {bg_content};
    border-bottom-left-radius: 12px;
    border-bottom-right-radius: 12px;
}}

#Workspace {{
    background: {bg_workspace};
}}

#VersionLabel {{
    color: {text_dim};
    background: transparent;
    border: none;
    font-size: {fs_9};
    letter-spacing: 1px;
    padding: 2px 4px;
    opacity: 0.5;
}}
#VersionLabel:hover {{
    color: {text_muted};
}}

#LibTabBtn {{
    background: {bg_menu};
    color: {text_dim};
    border: 1px solid {line};
    border-right: none;
    border-top-left-radius: 6px;
    border-bottom-left-radius: 6px;
    border-top-right-radius: 0px;
    border-bottom-right-radius: 0px;
    font-size: {fs_9};
    letter-spacing: 1px;
}}
#LibTabBtn:hover {{
    background: {hover_bg_strong};
    color: {accent_text};
    border-color: {accent};
}}
#HistTabBtn {{
    background: {bg_menu};
    color: {text_dim};
    border: 1px solid {line_strong};
    border-left: none;
    border-top-right-radius: 4px;
    border-bottom-right-radius: 4px;
    border-top-left-radius: 0px;
    border-bottom-left-radius: 0px;
    font-size: {fs_9};
    padding: 0px;
}}
#HistTabBtn:hover {{
    background: {hover_bg_strong};
    color: {accent_text};
    border-color: {accent};
}}

#TitleBar {{
    background: {bg_titlebar};
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
    border-bottom: 1px solid {line};
}}

/* ── Title Bar & Dock Buttons ── */
QPushButton#TitleBarButton,
QPushButton#CloseButton,
QPushButton#DockToggle,
QPushButton[class="DockItemButton"],
#PanelHeader {{
    font-weight: 500;
}}

QPushButton#TitleBarButton {{
    background: transparent;
    border: none;
    border-radius: 4px;
    color: {text_dim};
    font-size: {fs_12};
    min-width: 26px;
    max-width: 26px;
    min-height: 22px;
    max-height: 22px;
}}

QPushButton#TitleBarButton:hover {{
    background: {hover_bg_strong};
    color: {text_muted};
}}

QPushButton#TitleBarButton[active="true"] {{
    background: {accent};
    color: {accent_text};
}}

QPushButton#CloseButton:hover {{
    background: {close_hover};
    color: {selection_text};
}}

/* ── Dock Panel ── */
#DockPanel {{
    background: {bg_dock};
    border: 1px solid {line};
    border-radius: 10px;
}}

QPushButton#DockToggle {{
    background: transparent;
    border: none;
    border-radius: 4px;
    color: {text_dim};
    font-size: {fs_12};
    min-width: 20px;
    max-width: 20px;
    min-height: 20px;
    max-height: 20px;
}}

QPushButton#DockToggle:hover,
QPushButton[class="DockItemButton"]:hover {{
    background: {hover_bg_strong};
    color: {text_muted};
}}

QPushButton[class="DockItemButton"] {{
    background: transparent;
    border: none;
    border-radius: 0px;
    color: {text_dim};
    font-size: {fs_12};
    letter-spacing: 0.04em;
    padding: 7px 14px;
    min-height: 34px;
    text-align: left;
}}

#DockEdgeHandle,
#DockCornerHandle {{
    background: transparent;
    border-radius: 3px;
}}

#DockCornerHandle[visualHint="true"] {{
    background: {corner_hint};
    border: 1px solid {corner_hint_border};
}}

#DockEdgeHandle[hovered="true"],
#DockCornerHandle[hovered="true"] {{
    background: {edge_hover};
}}

#DockPreview {{
    background: {dock_preview};
    border: 1px solid {dock_preview_border};
    border-radius: 8px;
}}

/* ── Widget Cards ── */
#WidgetCard {{
    background: {bg_card};
    border: 1px solid {line};
    border-radius: 10px;
}}

#WidgetCard:hover {{
    border-color: {line_hover};
}}

#WidgetDragStrip {{
    background: {bg_card_strip};
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    border-bottom: 1px solid {line};
}}

#WidgetDragStrip:hover {{
    background: {bg_card_strip_hover};
}}

QPushButton#WidgetGrip {{
    color: {text_dim};
    border: none;
    background: transparent;
    border-radius: 8px;
    font-size: {fs_12};
    font-weight: 500;
}}

QPushButton#WidgetResizeHandle {{
    color: {text_dim};
    border: none;
    background: {hover_bg};
    border-radius: 6px;
    font-size: {fs_10};
    font-weight: 500;
}}

QPushButton#WidgetGrip:hover {{
    background: {hover_bg_strong};
    color: {text_muted};
}}

QFrame#WidgetResizeEdgeHandle,
QFrame#WidgetResizeCornerHandle {{
    background: transparent;
    border: none;
}}

/* ── Form Fields ── */
QLabel[class="FieldLabel"] {{
    color: {text_label};
    font-size: {fs_12};
}}

QLabel[class="SliderValue"],
#TokenLabel {{
    color: {text_muted};
    font-size: {fs_11};
}}

QLineEdit[class="FieldInput"],
QSpinBox[class="FieldSpin"],
QComboBox[class="FieldCombo"],
QTextEdit[class="FieldInput"],
QTextEdit[class="PromptTextEdit"],
QTextEdit[class="SummaryTextEdit"],
QTextEdit[class="InputEditor"],
QTextEdit[class="ExampleTextEdit"],
QTextEdit[class="OutputEditor"],
QTextEdit[class="MetadataText"] {{
    background: {bg_input};
    border: 1px solid {line};
    border-radius: 6px;
    color: {text_body};
    font-size: {fs_13};
    padding: 6px 8px;
    selection-background-color: {selection_bg};
    selection-color: {selection_text};
}}

QLineEdit[class="FieldInput"]:focus,
QSpinBox[class="FieldSpin"]:focus,
QComboBox[class="FieldCombo"]:focus,
QTextEdit[class="FieldInput"]:focus,
QTextEdit[class="PromptTextEdit"]:focus,
QTextEdit[class="SummaryTextEdit"]:focus,
QTextEdit[class="InputEditor"]:focus,
QTextEdit[class="ExampleTextEdit"]:focus,
QTextEdit[class="OutputEditor"]:focus,
QTextEdit[class="MetadataText"]:focus {{
    border-color: {accent_hover};
}}

QLineEdit[class="FieldInput"]::placeholder,
QTextEdit[class="FieldInput"]::placeholder,
QTextEdit[class="PromptTextEdit"]::placeholder,
QTextEdit[class="SummaryTextEdit"]::placeholder,
QTextEdit[class="InputEditor"]::placeholder,
QTextEdit[class="ExampleTextEdit"]::placeholder {{
    color: {text_dim};
}}

QSpinBox[class="FieldSpin"],
QComboBox[class="FieldCombo"] {{
    min-height: 30px;
}}

QSpinBox[class="FieldSpin"]::up-button,
QSpinBox[class="FieldSpin"]::down-button,
QComboBox[class="FieldCombo"]::drop-down {{
    width: 18px;
    border: none;
    background: transparent;
}}

QSpinBox[class="FieldSpin"]::up-arrow,
QSpinBox[class="FieldSpin"]::down-arrow,
QComboBox[class="FieldCombo"]::down-arrow {{
    width: 0px;
    height: 0px;
}}

QComboBox[class="FieldCombo"] QAbstractItemView,
QAbstractItemView {{
    background: {bg_surface};
    border: 1px solid {line_hover};
    color: {text_body};
    padding: 4px;
    selection-background-color: {selection_bg};
    selection-color: {selection_text};
}}

/* ── Buttons ── */
#InputActionBar {{
    background: transparent;
}}

QPushButton#SecondaryIconButton,
QPushButton#PrimaryIconButton,
QPushButton#GhostButton,
QPushButton#SecondaryButton,
QPushButton#PrimaryButton {{
    border-radius: 6px;
    min-height: 30px;
    padding: 4px 10px;
}}

QPushButton#SecondaryIconButton,
QPushButton#PrimaryIconButton {{
    min-width: 32px;
    max-width: 32px;
    min-height: 32px;
    max-height: 32px;
    padding: 0;
    font-size: {fs_13};
    font-weight: 500;
}}

QPushButton#SecondaryIconButton {{
    border: none;
    background: {hover_bg_strong};
    color: {text_muted};
}}

QPushButton#SecondaryIconButton:hover {{
    background: {line_hover};
    color: {text_body};
}}

QPushButton#PrimaryIconButton,
QPushButton#PrimaryButton {{
    border: none;
    background: {accent};
    color: {accent_text};
}}

QPushButton#PrimaryIconButton:hover,
QPushButton#PrimaryButton:hover {{
    background: {accent_hover};
    color: {accent_text_hover};
}}

QPushButton#GhostButton {{
    border: 1px dashed {line_hover};
    background: transparent;
    color: {text_muted};
}}

QPushButton#GhostButton:hover {{
    background: {hover_bg};
    border-color: {line_strong};
}}

QPushButton#SecondaryButton {{
    border: none;
    background: {hover_bg_strong};
    color: {text_body};
}}

QPushButton#SecondaryButton:hover {{
    background: {line_hover};
}}

QPushButton:disabled {{
    color: {disabled_text};
    background: {disabled_bg};
}}

/* ── Settings Panel ── */
#SettingsBackdrop {{
    background: {bg_backdrop};
}}

#SettingsPanel {{
    background: {bg_settings};
    border: 1px solid {line};
    border-radius: 12px;
}}

#PanelHeader {{
    color: {text_body};
    font-family: {font_family};
    font-size: {fs_14};
    border-bottom: 1px solid {line};
}}

/* ── Prompt Entries ── */
QFrame[class="PromptEntryFrame"] {{
    background: {bg_prompt};
    border: 1px solid {line};
    border-radius: 7px;
}}

QFrame[class="PromptEntryFrame"]:hover {{
    border-color: {line_hover};
}}

QWidget[class="PromptEntryHeader"] {{
    background: transparent;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
}}

QFrame[class="PromptEntryFrame"][expanded="true"] QWidget[class="PromptEntryHeader"] {{
    background: {hover_bg};
}}

QWidget[class="PromptEntryBody"] {{
    background: transparent;
    border-top: 1px solid {line};
    border-bottom-left-radius: 7px;
    border-bottom-right-radius: 7px;
}}

QFrame[class="PromptEntryFrame"] QLineEdit[class="FieldInput"],
QFrame[class="PromptEntryFrame"] QSpinBox[class="FieldSpin"],
QFrame[class="PromptEntryFrame"] QComboBox[class="FieldCombo"] {{
    min-height: 24px;
    padding: 4px 8px;
}}

QFrame[class="PromptEntryFrame"] QTextEdit[class="PromptTextEdit"] {{
    min-height: 104px;
}}

/* ── Example Entries ── */
QWidget[class="ExampleFrame"] {{
    background: {bg_prompt};
    border: 1px solid {line};
    border-radius: 6px;
}}

QWidget[class="ExampleFrame"]:hover {{
    border-color: {line_hover};
}}

QPushButton[class="PromptDeleteButton"],
QPushButton[class="ExampleDeleteButton"] {{
    background: transparent;
    border: none;
    border-radius: 4px;
    color: {text_dim};
}}

QPushButton[class="PromptDeleteButton"] {{
    min-width: 18px;
    max-width: 18px;
    min-height: 18px;
    max-height: 18px;
    font-size: {fs_14};
}}

QPushButton[class="ExampleDeleteButton"] {{
    min-width: 20px;
    max-width: 20px;
    min-height: 20px;
    max-height: 20px;
}}

QPushButton[class="PromptDeleteButton"]:hover,
QPushButton[class="ExampleDeleteButton"]:hover {{
    background: {delete_hover};
    color: white;
}}

QLabel[class="PromptDragHandle"] {{
    color: {text_dim};
    font-weight: 500;
}}

QLabel[class="PromptNamePreview"] {{
    color: {text_preview};
    font-size: {fs_12};
    padding: 0px 2px;
}}

QLabel[class="PromptExpandIndicator"] {{
    min-width: 16px;
    max-width: 16px;
    color: {text_dim};
    font-size: {fs_10};
    font-weight: 500;
}}

QFrame[class="PromptEntryFrame"][expanded="true"] QLabel[class="PromptExpandIndicator"] {{
    color: {text_muted};
}}

QPushButton[class="ImageSelectButton"] {{
    border: 1px dashed {line_hover};
    border-radius: 6px;
    background: {bg_input};
    color: {text_muted};
    font-size: {fs_12};
    padding: 8px;
}}

QPushButton[class="ImageSelectButton"]:hover {{
    border-color: {line_strong};
    color: {text_body};
}}

QListWidget {{
    background: transparent;
    border: none;
}}

QListWidget::item {{
    background: transparent;
    border: none;
    padding: 0px;
}}

/* ── Scrollbars & Sliders ── */
QScrollArea {{
    border: none;
    background: transparent;
}}

QScrollBar:vertical {{
    width: 4px;
    background: transparent;
}}

QScrollBar::handle:vertical {{
    background: {scrollbar};
    border-radius: 2px;
    min-height: 24px;
}}

QScrollBar:horizontal {{
    height: 4px;
    background: transparent;
}}

QScrollBar::handle:horizontal {{
    background: {scrollbar};
    border-radius: 2px;
    min-width: 24px;
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical,
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {{
    background: transparent;
    width: 0px;
    height: 0px;
}}

QSlider::groove:horizontal {{
    height: 4px;
    border-radius: 2px;
    background: {slider_groove};
}}

QSlider::sub-page:horizontal {{
    border-radius: 2px;
    background: {slider_sub};
}}

QSlider::handle:horizontal {{
    width: 14px;
    margin: -5px 0;
    border-radius: 7px;
    background: {accent_handle};
}}

/* ── Menus & Tooltips ── */
QMenu {{
    background: {bg_menu};
    border: 1px solid {line_hover};
    border-radius: 8px;
    padding: 6px;
}}

QMenu::item {{
    background: transparent;
    border-radius: 6px;
    padding: 7px 12px;
    color: {text_body};
}}

QMenu::item:selected {{
    background: {hover_bg_strong};
    color: {text};
}}

QMenu::separator {{
    height: 1px;
    background: {line};
    margin: 5px 8px;
}}

QToolTip {{
    background: {bg_menu};
    border: 1px solid {line_hover};
    color: {text_body};
    padding: 6px 8px;
}}

/* ── Output Tabs ── */
#OutputTabs::pane {{
    border: none;
}}

#OutputTabs QTabBar::tab {{
    background: transparent;
    color: {text_muted};
    padding: 6px 14px;
    border: none;
    border-bottom: 2px solid transparent;
}}

#OutputTabs QTabBar::tab:selected {{
    color: {text};
    border-bottom-color: {accent_handle};
}}

#OutputTabs QTabBar::tab:hover {{
    color: {text_body};
}}

/* ── Swap Button (floats on splitter handle) ── */
#SwapButton {{
    color: {text_dim};
    background: {bg_surface};
    border: 1px solid {line};
    border-radius: 8px;
    font-size: {fs_10};
    padding: 0;
}}
#SwapButton:hover {{
    color: {accent_text};
    border-color: {accent_handle};
    background: {hover_bg_strong};
}}

/* ── Main Splitter ── */
QSplitter::handle:vertical {{
    background: {line};
    height: 1px;
    margin: 2px 12px;
}}
QSplitter::handle:vertical:hover {{
    background: {accent_handle};
    height: 2px;
}}

/* ── Popup Panels (shared style for all floating panels) ── */
#PopupPanel {{
    background: {bg_surface};
    border: 1px solid {line_hover};
    border-radius: 10px;
}}

#PopupPanel QLabel {{
    color: {text_body};
    font-size: {fs_12};
}}

#PopupPanel QPushButton#PopupClose {{
    background: transparent;
    border: none;
    color: {text_dim};
    font-size: {fs_14};
    min-width: 20px;
    max-width: 20px;
    min-height: 20px;
    max-height: 20px;
    border-radius: 4px;
}}

#PopupPanel QPushButton#PopupClose:hover {{
    background: {delete_hover};
    color: white;
}}

#PopupPanel QPushButton#PopupBtn {{
    background: {hover_bg_strong};
    border: 1px solid {line};
    border-radius: 6px;
    color: {text_muted};
    padding: 6px 20px;
    font-size: {fs_12};
}}

#PopupPanel QPushButton#PopupBtn:hover {{
    background: {line_hover};
    color: {text_body};
}}

#PopupPanel QSlider::groove:horizontal {{
    height: 4px;
    border-radius: 2px;
    background: {slider_groove};
}}

#PopupPanel QSlider::sub-page:horizontal {{
    border-radius: 2px;
    background: {slider_sub};
}}

#PopupPanel QSlider::handle:horizontal {{
    width: 14px;
    margin: -5px 0;
    border-radius: 7px;
    background: {accent_handle};
}}

#PopupPanel QListWidget {{
    background: {bg_input};
    border: 1px solid {line};
    border-radius: 8px;
    color: {text_body};
    font-size: {fs_13};
    padding: 4px;
}}

#PopupPanel QListWidget::item {{
    padding: 8px 12px;
    border-radius: 6px;
    margin: 2px 0;
}}

#PopupPanel QListWidget::item:hover {{
    background: {hover_bg_strong};
}}

#PopupPanel QListWidget::item:selected {{
    background: {accent};
}}

#PopupPanel QSpinBox {{
    background: {bg_input};
    border: 1px solid {line};
    border-radius: 6px;
    color: {text_body};
    font-size: {fs_13};
    padding: 4px 8px;
    min-height: 30px;
}}

#PopupPanel QSpinBox::up-button,
#PopupPanel QSpinBox::down-button {{
    width: 18px;
    border: none;
    background: transparent;
}}
"""


# ── Public API ──

def _interpolate_hex(a: str, b: str, t: float) -> str:
    """Linearly interpolate between two hex colors. t=0→a, t=1→b."""
    if not a.startswith('#') or not b.startswith('#'):
        return b if t > 0.5 else a
    ra, ga, ba = int(a[1:3], 16), int(a[3:5], 16), int(a[5:7], 16)
    rb, gb, bb = int(b[1:3], 16), int(b[3:5], 16), int(b[5:7], 16)
    r = int(ra + (rb - ra) * t)
    g = int(ga + (gb - ga) * t)
    b_ = int(ba + (bb - ba) * t)
    return f'#{r:02x}{g:02x}{b_:02x}'


_RGBA_RE = re.compile(r'rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)')


def _interpolate_rgba(a: str, b: str, t: float) -> str:
    """Linearly interpolate between two rgba() strings."""
    ma = _RGBA_RE.match(a)
    mb = _RGBA_RE.match(b)
    if not ma or not mb:
        return b if t > 0.5 else a
    ra, ga, ba, aa = int(ma.group(1)), int(ma.group(2)), int(ma.group(3)), float(ma.group(4))
    rb, gb, bb, ab = int(mb.group(1)), int(mb.group(2)), int(mb.group(3)), float(mb.group(4))
    r = int(ra + (rb - ra) * t)
    g = int(ga + (gb - ga) * t)
    b_ = int(ba + (bb - ba) * t)
    alpha = round(aa + (ab - aa) * t, 2)
    return f'rgba({r}, {g}, {b_}, {alpha})'


def _relative_luminance(hex_color: str) -> float:
    """WCAG 2.0 relative luminance. Input: '#rrggbb'. Output: 0.0 (black) to 1.0 (white)."""
    if not hex_color.startswith('#') or len(hex_color) != 7:
        return 0.5
    r, g, b = int(hex_color[1:3], 16) / 255.0, int(hex_color[3:5], 16) / 255.0, int(hex_color[5:7], 16) / 255.0
    r = r / 12.92 if r <= 0.03928 else ((r + 0.055) / 1.055) ** 2.4
    g = g / 12.92 if g <= 0.03928 else ((g + 0.055) / 1.055) ** 2.4
    b = b / 12.92 if b <= 0.03928 else ((b + 0.055) / 1.055) ** 2.4
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _auto_text_colors(bg_hex: str) -> dict[str, str]:
    """Generate a full set of text colors that contrast well against bg_hex."""
    lum = _relative_luminance(bg_hex)
    is_light_bg = lum > 0.18  # threshold tuned for readability
    if is_light_bg:
        return {
            'text': '#111111', 'text_body': '#222222', 'text_muted': '#555555',
            'text_dim': '#444444', 'text_label': '#444444', 'text_preview': '#1a1a1a',
            'accent_text': '#3A4A80', 'accent_text_hover': '#2A3A70',
            'selection_text': '#111111', 'disabled_text': '#888888',
        }
    return {
        'text': '#F4F4F0', 'text_body': '#D0D0C8', 'text_muted': '#A0A098',
        'text_dim': '#8A8A82', 'text_label': '#9A9A92', 'text_preview': '#E0E0D8',
        'accent_text': '#B8BCD8', 'accent_text_hover': '#D8DAF0',
        'selection_text': '#F4F4F0', 'disabled_text': '#5A5A55',
    }


def _interpolate_palettes(dark: dict[str, str], light: dict[str, str], factor: float) -> dict[str, str]:
    """Interpolate between dark and light palettes. factor: 0=dark, 1=light.

    Background colors interpolate smoothly. Text colors are auto-calculated
    from the resulting background using WCAG luminance for guaranteed contrast.
    """
    result = {}
    for key in dark:
        dv = dark[key]
        lv = light.get(key, dv)
        if dv.startswith('#') and lv.startswith('#') and len(dv) == 7 and len(lv) == 7:
            result[key] = _interpolate_hex(dv, lv, factor)
        elif dv.startswith('rgba') and lv.startswith('rgba'):
            result[key] = _interpolate_rgba(dv, lv, factor)
        else:
            result[key] = lv if factor > 0.5 else dv
    # Auto-calculate all text colors based on the interpolated background
    if 'bg' in result:
        result.update(_auto_text_colors(result['bg']))
    return result


def generate_qss(theme: str = 'dark', custom_palette: dict[str, str] | None = None, card_opacity: int = 82, brightness: int = 50, body_font_pt: int = 11, font_family: str = '') -> str:
    if theme == 'custom' and custom_palette:
        palette = dict(custom_palette)
    elif theme == 'light':
        palette = dict(LIGHT_PALETTE)
    else:
        palette = dict(DARK_PALETTE)

    # Brightness: each theme has its own half of the interpolation range
    # Dark mode:  brightness 0-100% → factor 0.0-0.5 (always dark-ish)
    # Light mode: brightness 0-100% → factor 0.5-1.0 (always light-ish)
    b = max(0, min(100, brightness)) / 100.0
    if theme == 'light':
        factor = 0.5 + b * 0.5   # 0%→0.5, 50%→0.75, 100%→1.0
    elif theme == 'custom' and custom_palette:
        factor = b  # custom: full range 0-1
    else:
        factor = b * 0.5          # 0%→0.0, 50%→0.25, 100%→0.5

    if theme == 'custom' and custom_palette:
        palette = _interpolate_palettes(custom_palette, LIGHT_PALETTE, factor)
    else:
        palette = _interpolate_palettes(DARK_PALETTE, LIGHT_PALETTE, factor)

    # 更新主题亮暗状态（供 ToggleSwitch / token label 等自定义绘制组件读取）
    global _is_light, _current_palette
    _is_light = _relative_luminance(palette['bg']) > 0.18

    # Font family token — set by app.setFont() profile, QSS must match
    if font_family:
        palette['font_family'] = font_family
    else:
        palette['font_family'] = '"Microsoft YaHei UI", "Segoe UI", sans-serif'

    # Font size tokens — all relative to body_font_pt (default 11)
    # QSS template uses these instead of hardcoded px values
    bp = max(8, min(24, body_font_pt))
    palette['fs_9']  = f'{max(7, bp - 2)}px'   # 9px@11  — tiny labels
    palette['fs_10'] = f'{max(8, bp - 1)}px'   # 10px@11 — secondary
    palette['fs_11'] = f'{bp}px'               # 11px@11 — body
    palette['fs_12'] = f'{bp + 1}px'           # 12px@11 — buttons, fields
    palette['fs_13'] = f'{bp + 2}px'           # 13px@11 — emphasis
    palette['fs_14'] = f'{bp + 3}px'           # 14px@11 — titles

    # 仅覆盖 alpha 以应用用户设置的卡片透明度，RGB 保留插值结果实现平滑过渡
    opacity = max(30, min(100, card_opacity)) / 100.0
    strip_opacity = round(min(1.0, opacity + 0.08), 4)
    strip_hover_opacity = round(min(1.0, opacity + 0.10), 4)
    for key, alpha in (
        ('bg_card', opacity),
        ('bg_card_strip', strip_opacity),
        ('bg_card_strip_hover', strip_hover_opacity),
    ):
        m = _RGBA_RE.match(palette[key])
        if m:
            palette[key] = f'rgba({m.group(1)}, {m.group(2)}, {m.group(3)}, {alpha})'
    _current_palette = dict(palette)
    return _QSS_TEMPLATE.format(**palette)


def is_theme_light() -> bool:
    """Whether the currently applied theme has a light background."""
    return _is_light


def current_palette() -> dict[str, str]:
    """Return the resolved palette from the last generate_qss() call."""
    return dict(_current_palette) if _current_palette else dict(DARK_PALETTE)


def _fs(key: str) -> str:
    """Shorthand for inline stylesheets: f"font-size: {_fs('fs_12')};" """
    p = _current_palette
    if p and key in p:
        return p[key]
    fallback = {'fs_9': '9px', 'fs_10': '10px', 'fs_11': '11px',
                'fs_12': '12px', 'fs_13': '13px', 'fs_14': '14px'}
    return fallback.get(key, '11px')


def font_sizes() -> dict[str, str]:
    """Return current font size tokens from the last generate_qss() call.

    Keys: fs_9, fs_10, fs_11, fs_12, fs_13, fs_14
    Values: e.g. '9px', '10px', etc. (scaled to user's body_font_pt)
    Use in inline stylesheets: f"font-size: {fs['fs_12']};"
    """
    p = _current_palette
    if p and 'fs_11' in p:
        return {k: p[k] for k in ('fs_9', 'fs_10', 'fs_11', 'fs_12', 'fs_13', 'fs_14')}
    # Fallback to default 11pt
    return {'fs_9': '9px', 'fs_10': '10px', 'fs_11': '11px',
            'fs_12': '12px', 'fs_13': '13px', 'fs_14': '14px'}


def scale_qss(qss: str, scale_percent: int) -> str:
    global _current_palette
    if scale_percent == 100:
        return qss
    factor = scale_percent / 100.0
    if _current_palette:
        scaled = dict(_current_palette)
        for key in ('fs_9', 'fs_10', 'fs_11', 'fs_12', 'fs_13', 'fs_14'):
            value = scaled.get(key, '')
            match = re.fullmatch(r'(\d+)px', value)
            if match:
                scaled[key] = f"{max(1, round(int(match.group(1)) * factor))}px"
        _current_palette = scaled

    def _replace(m: re.Match) -> str:
        return f"{max(1, round(int(m.group(1)) * factor))}px"

    return re.sub(r'(\d+)px', _replace, qss)


# Keep backward compat — APP_QSS is now generated on import (dark default)
APP_QSS = generate_qss('dark', card_opacity=82, body_font_pt=11,
                        font_family='"Microsoft YaHei UI", "Segoe UI", sans-serif')


def extract_palette_from_image(path: str) -> dict[str, str]:
    """Extract dominant color from image and generate a full UI palette.

    Algorithm: resize → pixel frequency → dominant HSL → desaturate → derive palette.
    Ensures WCAG 4.5:1 contrast ratio for text readability.
    """
    try:
        from PIL import Image
    except ImportError:
        return dict(DARK_PALETTE)

    try:
        img = Image.open(path).convert('RGB')
        img = img.resize((80, 80), Image.Resampling.LANCZOS)
    except Exception:
        return dict(DARK_PALETTE)

    # Find dominant color by pixel frequency
    pixels = list(img.getdata())
    # Quantize to reduce unique colors
    quantized = [(r // 16 * 16, g // 16 * 16, b // 16 * 16) for r, g, b in pixels]
    from collections import Counter
    freq = Counter(quantized).most_common(1)
    if not freq:
        return dict(DARK_PALETTE)
    dominant_rgb = freq[0][0]

    # Convert to HSL
    r, g, b = dominant_rgb[0] / 255.0, dominant_rgb[1] / 255.0, dominant_rgb[2] / 255.0
    import colorsys
    h, l, s = colorsys.rgb_to_hls(r, g, b)

    # Decide dark or light base
    is_dark = l < 0.5

    def hsl_to_hex(h: float, s: float, l: float) -> str:
        r, g, b = colorsys.hls_to_rgb(h, l, s)
        return f'#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}'

    def hsl_to_rgba(h: float, s: float, l: float, a: float) -> str:
        r, g, b = colorsys.hls_to_rgb(h, l, s)
        return f'rgba({int(r*255)}, {int(g*255)}, {int(b*255)}, {a})'

    bg_s = 0.10  # Heavy desaturation for backgrounds

    if is_dark:
        # Dark theme derived from dominant hue
        bg = hsl_to_hex(h, bg_s, 0.08)
        bg_top = hsl_to_hex(h, bg_s, 0.10)
        bg_content = hsl_to_hex(h, bg_s, 0.07)
        bg_workspace = hsl_to_hex(h, bg_s, 0.05)
        bg_titlebar = hsl_to_hex(h, bg_s, 0.09)
        bg_surface = hsl_to_hex(h, bg_s, 0.11)
        bg_input = hsl_to_hex(h, bg_s, 0.05)
        bg_card_strip = hsl_to_rgba(h, bg_s, 0.08, 0.90)
        bg_card_strip_hover = hsl_to_rgba(h, bg_s, 0.12, 0.92)
        bg_dock = hsl_to_hex(h, bg_s, 0.09)
        bg_settings = hsl_to_hex(h, bg_s, 0.09)
        bg_settings_top = hsl_to_hex(h, bg_s, 0.11)
        bg_prompt = hsl_to_hex(h, bg_s, 0.06)
        bg_menu = hsl_to_rgba(h, bg_s, 0.08, 0.96)
        text = '#F4F4F0'
        text_body = '#C8C8C0'
        text_muted = '#7A7A75'
        text_dim = '#4A4A45'
        text_label = '#8A8A82'
        text_preview = '#D0D0C8'
        tint_rgba = '244, 244, 240'
    else:
        # Light theme derived from dominant hue
        bg = hsl_to_hex(h, bg_s, 0.95)
        bg_top = hsl_to_hex(h, bg_s, 0.93)
        bg_content = hsl_to_hex(h, bg_s, 0.91)
        bg_workspace = hsl_to_hex(h, bg_s, 0.89)
        bg_titlebar = hsl_to_hex(h, bg_s, 0.93)
        bg_surface = hsl_to_hex(h, bg_s, 0.95)
        bg_input = '#FFFFFF'
        bg_card_strip = hsl_to_rgba(h, bg_s, 0.96, 0.90)
        bg_card_strip_hover = hsl_to_rgba(h, bg_s, 0.93, 0.92)
        bg_dock = hsl_to_hex(h, bg_s, 0.91)
        bg_settings = hsl_to_hex(h, bg_s, 0.91)
        bg_settings_top = hsl_to_hex(h, bg_s, 0.93)
        bg_prompt = hsl_to_hex(h, bg_s, 0.96)
        bg_menu = hsl_to_rgba(h, bg_s, 0.95, 0.97)
        text = '#111111'
        text_body = '#333333'
        text_muted = '#888888'
        text_dim = '#AAAAAA'
        text_label = '#666666'
        text_preview = '#222222'
        tint_rgba = '17, 17, 17'

    accent_h = (h + 0.6) % 1.0  # Complementary hue for accent
    accent_s = 0.35

    return {
        'bg': bg, 'bg_top': bg_top, 'bg_content': bg_content,
        'bg_workspace': bg_workspace, 'bg_titlebar': bg_titlebar,
        'bg_surface': bg_surface, 'bg_input': bg_input,
        'bg_card': hsl_to_rgba(h, bg_s, 0.10 if is_dark else 0.98, 0.82),
        'bg_card_strip': bg_card_strip, 'bg_card_strip_hover': bg_card_strip_hover,
        'bg_dock': bg_dock, 'bg_settings_top': bg_settings_top,
        'bg_settings': bg_settings, 'bg_prompt': bg_prompt, 'bg_menu': bg_menu,
        'text': text, 'text_body': text_body, 'text_muted': text_muted,
        'text_dim': text_dim, 'text_label': text_label, 'text_preview': text_preview,
        'line': f'rgba({tint_rgba}, 0.08)',
        'line_hover': f'rgba({tint_rgba}, 0.13)',
        'line_strong': f'rgba({tint_rgba}, 0.18)',
        'hover_bg': f'rgba({tint_rgba}, 0.06)',
        'hover_bg_strong': f'rgba({tint_rgba}, 0.10)',
        'accent': hsl_to_rgba(accent_h, accent_s, 0.55, 0.25),
        'accent_hover': hsl_to_rgba(accent_h, accent_s, 0.55, 0.45),
        'accent_text': hsl_to_hex(accent_h, accent_s, 0.72 if is_dark else 0.35),
        'accent_text_hover': hsl_to_hex(accent_h, accent_s, 0.82 if is_dark else 0.25),
        'accent_handle': hsl_to_hex(accent_h, accent_s, 0.55),
        'accent_sub': hsl_to_rgba(accent_h, accent_s, 0.55, 0.20),
        'delete_hover': 'rgba(200, 60, 50, 0.35)',
        'close_hover': 'rgba(200, 60, 50, 0.65)',
        'selection_bg': hsl_to_rgba(accent_h, accent_s, 0.55, 0.45),
        'selection_text': text,
        'disabled_text': text_dim,
        'disabled_bg': f'rgba({tint_rgba}, 0.03)',
        'slider_groove': f'rgba({tint_rgba}, 0.07)',
        'slider_sub': hsl_to_rgba(accent_h, accent_s, 0.55, 0.25),
        'scrollbar': f'rgba({tint_rgba}, 0.10)',
        'dock_preview': hsl_to_rgba(accent_h, accent_s, 0.55, 0.12),
        'dock_preview_border': hsl_to_rgba(accent_h, accent_s, 0.55, 0.50),
        'corner_hint': f'rgba({tint_rgba}, 0.03)',
        'corner_hint_border': f'rgba({tint_rgba}, 0.05)',
        'edge_hover': hsl_to_rgba(accent_h, accent_s, 0.55, 0.18),
    }
