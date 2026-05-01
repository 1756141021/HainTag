from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ..models import HistoryEntry
from ..theme import _fs, current_palette
from ..ui_tokens import _dp


class WorkbenchTimeline(QWidget):
    """Compact v3-style recent-generation strip for the main TAG workbench."""

    view_all_requested = pyqtSignal()
    entry_selected = pyqtSignal(object)

    def __init__(self, translator, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("WorkbenchTimeline")
        self._t = translator
        self._expanded = False
        self._items: list[dict] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._row = QWidget(self)
        self._row.setObjectName("WorkbenchTimelineRow")
        row = QHBoxLayout(self._row)
        row.setContentsMargins(_dp(14), _dp(8), _dp(14), _dp(8))
        row.setSpacing(_dp(10))

        self._caret = QLabel("▶", self._row)
        self._caret.setObjectName("WorkbenchTimelineCaret")
        row.addWidget(self._caret)

        self._icon = QLabel("◷", self._row)
        self._icon.setObjectName("WorkbenchTimelineIcon")
        row.addWidget(self._icon)

        self._label = QLabel(self._t.t("workbench_recent"), self._row)
        self._label.setObjectName("WorkbenchTimelineLabel")
        row.addWidget(self._label)

        self._count = QLabel("0", self._row)
        self._count.setObjectName("WorkbenchTimelineCount")
        row.addWidget(self._count)

        self._divider_a = QLabel("", self._row)
        self._divider_a.setObjectName("WorkbenchTimelineDivider")
        self._divider_a.setFixedSize(_dp(1), _dp(12))
        row.addWidget(self._divider_a)

        self._rail = QWidget(self._row)
        self._rail.setObjectName("WorkbenchTimelineRail")
        self._rail_layout = QHBoxLayout(self._rail)
        self._rail_layout.setContentsMargins(0, 0, 0, 0)
        self._rail_layout.setSpacing(_dp(3))
        row.addWidget(self._rail)

        self._divider_b = QLabel("", self._row)
        self._divider_b.setObjectName("WorkbenchTimelineDivider")
        self._divider_b.setFixedSize(_dp(1), _dp(12))
        row.addWidget(self._divider_b)

        self._current = QLabel("● \"\"", self._row)
        self._current.setObjectName("WorkbenchTimelineCurrent")
        self._current.setTextFormat(Qt.TextFormat.PlainText)
        row.addWidget(self._current, 1)

        self._all_btn = QPushButton(self._t.t("workbench_view_all_history"), self._row)
        self._all_btn.setObjectName("WorkbenchTimelineAction")
        self._all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._all_btn.clicked.connect(lambda checked=False: self.view_all_requested.emit())
        row.addWidget(self._all_btn)

        root.addWidget(self._row, 0)

        self._expanded_row = QScrollArea(self)
        self._expanded_row.setObjectName("WorkbenchTimelineExpanded")
        self._expanded_row.setWidgetResizable(True)
        self._expanded_row.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._expanded_row.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._expanded_row.setFrameShape(QFrame.Shape.NoFrame)
        self._expanded_row.setFixedHeight(_dp(112))
        self._cards_host = QWidget(self._expanded_row)
        self._cards_host.setObjectName("WorkbenchTimelineCards")
        self._expanded_layout = QHBoxLayout(self._cards_host)
        self._expanded_layout.setContentsMargins(_dp(14), _dp(12), _dp(14), _dp(12))
        self._expanded_layout.setSpacing(_dp(8))
        self._expanded_row.setWidget(self._cards_host)
        self._expanded_row.hide()
        root.addWidget(self._expanded_row, 0)

        self._row.mousePressEvent = lambda event: self.toggle_expanded()
        self.set_items([])
        self.apply_workbench_style()

    def set_items(self, items: list[dict]) -> None:
        self._items = list(items or [])
        self._count.setText(str(len(self._items)))
        if self._items:
            current = next((item for item in self._items if item.get("current")), self._items[0])
            prompt = str(current.get("prompt", "") or "")
            self._current.setText(f"● \"{prompt}\"")
        else:
            self._current.setText("● \"\"")
        self._rebuild_rail()
        self._rebuild_cards()

    def set_history_entries(self, entries: list[HistoryEntry]) -> None:
        items: list[dict] = []
        for entry in entries[:18]:
            prompt = (entry.input_text or entry.output_text or "").replace("\n", " ").strip()
            if len(prompt) > 80:
                prompt = prompt[:77] + "..."
            items.append({
                "time": entry.timestamp[:16].replace("T", "  ") if entry.timestamp else "--",
                "prompt": prompt,
                "tokens": len((entry.output_text or "").split()),
                "status": "ok",
                "current": False,
                "entry": entry,
            })
        self.set_items(items)

    def add_history_item(self, prompt: str, *, tokens: int = 0, status: str = "ok") -> None:
        for item in self._items:
            item["current"] = False
        self._items.insert(0, {
            "time": "",
            "prompt": prompt,
            "tokens": tokens,
            "status": status,
            "current": True,
        })
        self.set_items(self._items[:18])

    def mark_current(self, *, tokens: int | None = None, status: str | None = None) -> None:
        current = next((item for item in self._items if item.get("current")), None)
        if current is None:
            return
        if tokens is not None:
            current["tokens"] = tokens
        if status is not None:
            current["status"] = status
        self.set_items(self._items)

    def attach_current_entry(self, entry: object) -> None:
        current = next((item for item in self._items if item.get("current")), None)
        if current is None:
            return
        current["entry"] = entry
        self.set_items(self._items)

    def retranslate_ui(self) -> None:
        self._label.setText(self._t.t("workbench_recent"))
        self._all_btn.setText(self._t.t("workbench_view_all_history"))
        self._rebuild_cards()

    def toggle_expanded(self) -> None:
        self._expanded = not self._expanded
        self._caret.setText("▼" if self._expanded else "▶")
        self._expanded_row.setVisible(self._expanded)

    def _rebuild_cards(self) -> None:
        while self._expanded_layout.count():
            item = self._expanded_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for item in self._items[:18]:
            card = QWidget(self._cards_host)
            card.setObjectName("WorkbenchTimelineCard")
            card.setFixedSize(_dp(180), _dp(82))
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(_dp(8), _dp(7), _dp(8), _dp(7))
            card_layout.setSpacing(_dp(4))
            time = QLabel(str(item.get("time") or (self._t.t("workbench_current") if item.get("current") else "--")), card)
            time.setObjectName("WorkbenchTimelineCardTime")
            card_layout.addWidget(time)
            prompt = QLabel(str(item.get("prompt", "")), card)
            prompt.setObjectName("WorkbenchTimelineCardPrompt")
            prompt.setWordWrap(True)
            prompt.setMaximumHeight(_dp(34))
            card_layout.addWidget(prompt, 1)
            token_label = self._t.t("token_count")
            meta = QLabel(f"{int(item.get('tokens') or 0):,} {token_label}", card)
            meta.setObjectName("WorkbenchTimelineCardMeta")
            card_layout.addWidget(meta)
            card.mousePressEvent = lambda event, it=item: self._emit_entry_selected(it)
            self._expanded_layout.addWidget(card)
        self._expanded_layout.addStretch(1)

    def _rebuild_rail(self) -> None:
        while self._rail_layout.count():
            item = self._rail_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for item in self._items[:18]:
            dot = QFrame(self._rail)
            dot.setObjectName("WorkbenchTimelineDot")
            dot.setProperty("current", bool(item.get("current")))
            dot.setProperty("failed", item.get("status") == "failed")
            dot.setFixedSize(_dp(14) if item.get("current") else _dp(5), _dp(5))
            tooltip = f"{item.get('time') or '--'} · {int(item.get('tokens') or 0):,} tok\n{item.get('prompt') or ''}"
            dot.setToolTip(tooltip)
            dot.mousePressEvent = lambda event, it=item: self._emit_entry_selected(it)
            self._rail_layout.addWidget(dot)

    def _emit_entry_selected(self, item: dict) -> None:
        self.entry_selected.emit(item.get("entry") or item)

    def apply_workbench_style(self) -> None:
        pal = current_palette()
        self.setStyleSheet(
            f"QWidget#WorkbenchTimeline {{ background: {pal['bg_card_strip']}; border-top: 1px solid {pal['line']}; border-bottom: 1px solid {pal['line']}; }}"
            f"QWidget#WorkbenchTimelineRow {{ background: {pal['bg_surface']}; }}"
            f"QWidget#WorkbenchTimelineRow:hover {{ background: {pal['hover_bg']}; }}"
            f"QLabel#WorkbenchTimelineCaret, QLabel#WorkbenchTimelineIcon {{ color: {pal['text_label']}; font-size: {_fs('fs_10')}; }}"
            f"QLabel#WorkbenchTimelineLabel {{ color: {pal['text_label']}; font-size: {_fs('fs_10')}; letter-spacing: 1px; }}"
            f"QLabel#WorkbenchTimelineCount {{ color: {pal['text_muted']}; font-size: {_fs('fs_10')}; }}"
            f"QFrame#WorkbenchTimelineDot {{ background: {pal['line_strong']}; border-radius: {_dp(2)}px; }}"
            f"QFrame#WorkbenchTimelineDot[current=\"true\"] {{ background: {pal['accent_text']}; }}"
            f"QFrame#WorkbenchTimelineDot[failed=\"true\"] {{ background: {pal['delete_hover']}; }}"
            f"QLabel#WorkbenchTimelineDivider {{ background: {pal['line']}; }}"
            f"QLabel#WorkbenchTimelineCurrent {{ color: {pal['text_muted']}; font-size: {_fs('fs_12')}; }}"
            f"QPushButton#WorkbenchTimelineAction {{ background: transparent; color: {pal['text_label']}; border: none; border-radius: {_dp(3)}px; padding: {_dp(2)}px {_dp(6)}px; font-size: {_fs('fs_11')}; }}"
            f"QPushButton#WorkbenchTimelineAction:hover {{ color: {pal['accent_text']}; background: {pal['accent_sub']}; }}"
            f"QScrollArea#WorkbenchTimelineExpanded {{ background: {pal['bg_card_strip']}; border-top: 1px solid {pal['line']}; }}"
            f"QWidget#WorkbenchTimelineCards {{ background: {pal['bg_card_strip']}; }}"
            f"QWidget#WorkbenchTimelineCard {{ background: {pal['bg_surface']}; border: 1px solid {pal['line']}; border-radius: {_dp(5)}px; min-width: {_dp(160)}px; max-width: {_dp(180)}px; }}"
            f"QLabel#WorkbenchTimelineCardTime {{ color: {pal['accent_text']}; font-size: {_fs('fs_10')}; }}"
            f"QLabel#WorkbenchTimelineCardPrompt {{ color: {pal['text']}; font-size: {_fs('fs_11')}; }}"
            f"QLabel#WorkbenchTimelineCardMeta {{ color: {pal['text_label']}; font-size: {_fs('fs_9')}; }}"
            f"QScrollBar:horizontal {{ background: transparent; height: {_dp(8)}px; }}"
            f"QScrollBar::handle:horizontal {{ background: {pal['scrollbar']}; border-radius: {_dp(4)}px; min-width: {_dp(24)}px; }}"
        )
        self._rebuild_rail()
