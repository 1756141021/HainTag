from __future__ import annotations

from dataclasses import replace

from PyQt6.QtCore import QEvent, QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSpinBox,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from ..models import OCEntry
from ..theme import _fs, current_palette
from ..ui_tokens import _dp
from .text_context_menu import apply_app_menu_style


def _split_tags(text: str, limit: int = 8) -> list[str]:
    tags: list[str] = []
    for raw in text.replace("\n", ",").split(","):
        tag = raw.strip()
        if tag:
            tags.append(tag)
        if len(tags) >= limit:
            break
    return tags


def _has_visible_oc_content(entry: OCEntry) -> bool:
    if entry.character_name.strip() or entry.tags.strip() or entry.reference_images:
        return True
    return any(outfit.name.strip() or outfit.tags.strip() for outfit in entry.outfits)


class _OCBubble(QFrame):
    """HTML OCBubble equivalent, anchored near the titlebar chip."""

    edit_requested = pyqtSignal(int, QPoint)
    remove_requested = pyqtSignal(int)
    oc_changed = pyqtSignal(int, object)

    def __init__(self, translator, index: int, entry: OCEntry, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("WorkbenchOCBubble")
        self._t = translator
        self._index = index
        self._entry = entry
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        head = QWidget(self)
        head.setObjectName("WorkbenchOCBubbleHead")
        head_layout = QHBoxLayout(head)
        head_layout.setContentsMargins(_dp(14), _dp(12), _dp(14), _dp(12))
        head_layout.setSpacing(_dp(10))
        avatar = QLabel(head)
        avatar.setObjectName("WorkbenchOCBubbleAvatar")
        avatar.setFixedSize(_dp(32), _dp(32))
        head_layout.addWidget(avatar)
        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(_dp(2))
        name = QLabel(entry.character_name or self._t.t("character_name"), head)
        name.setObjectName("WorkbenchOCBubbleName")
        sub = QLabel(
            self._t.t("workbench_oc_order_depth").format(order=entry.order, depth=entry.depth),
            head,
        )
        sub.setObjectName("WorkbenchOCBubbleSub")
        title_box.addWidget(name)
        title_box.addWidget(sub)
        head_layout.addLayout(title_box, 1)
        root.addWidget(head)

        base = QWidget(self)
        base.setObjectName("WorkbenchOCBubbleSection")
        base_layout = QVBoxLayout(base)
        base_layout.setContentsMargins(_dp(14), _dp(10), _dp(14), _dp(10))
        base_layout.setSpacing(_dp(8))
        base_layout.addWidget(self._section_label("workbench_oc_base"))
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(_dp(8))
        order = self._stepper(self._t.t("workbench_oc_order_label"), entry.order)
        depth = self._stepper(self._t.t("workbench_oc_depth_label"), entry.depth)
        controls.addWidget(order[0])
        controls.addWidget(depth[0])
        base_layout.addLayout(controls)
        root.addWidget(base)

        order[1].valueChanged.connect(lambda _: self._emit_numeric(order[1].value(), depth[1].value()))
        depth[1].valueChanged.connect(lambda _: self._emit_numeric(order[1].value(), depth[1].value()))

        outfits = [outfit for outfit in entry.outfits if outfit.name.strip()]
        if outfits:
            outfit_section = QWidget(self)
            outfit_section.setObjectName("WorkbenchOCBubbleSection")
            outfit_layout = QVBoxLayout(outfit_section)
            outfit_layout.setContentsMargins(_dp(14), _dp(10), _dp(14), _dp(10))
            outfit_layout.setSpacing(_dp(8))
            outfit_layout.addWidget(self._section_label("workbench_oc_outfit"))
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(_dp(4))
            for outfit in outfits:
                btn = QPushButton(outfit.name, outfit_section)
                btn.setObjectName("WorkbenchOCOutfitPill")
                btn.setProperty("active", outfit.active)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda checked=False, name=outfit.name: self._switch_outfit(name))
                row.addWidget(btn)
            row.addStretch(1)
            outfit_layout.addLayout(row)
            root.addWidget(outfit_section)

        tags = _split_tags(entry.merged_tags())
        if tags:
            tag_section = QWidget(self)
            tag_section.setObjectName("WorkbenchOCBubbleSection")
            tag_layout = QVBoxLayout(tag_section)
            tag_layout.setContentsMargins(_dp(14), _dp(10), _dp(14), _dp(10))
            tag_layout.setSpacing(_dp(8))
            tag_layout.addWidget(QLabel(f"{self._t.t('tags')} · {len(tags)}", tag_section))
            tag_layout.itemAt(0).widget().setObjectName("WorkbenchOCBubbleSectionLabel")
            tag_row = QHBoxLayout()
            tag_row.setContentsMargins(0, 0, 0, 0)
            tag_row.setSpacing(_dp(4))
            for tag in tags:
                label = QLabel(tag, tag_section)
                label.setObjectName("WorkbenchOCBubbleTag")
                label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
                tag_row.addWidget(label)
            tag_row.addStretch(1)
            tag_layout.addLayout(tag_row)
            root.addWidget(tag_section)

        actions = QWidget(self)
        actions.setObjectName("WorkbenchOCBubbleSection")
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(_dp(14), _dp(10), _dp(14), _dp(10))
        actions_layout.setSpacing(_dp(6))
        edit_btn = QPushButton(self._t.t("workbench_edit_oc"), actions)
        edit_btn.setObjectName("WorkbenchOCBubblePrimary")
        remove_btn = QPushButton(self._t.t("workbench_remove_oc"), actions)
        remove_btn.setObjectName("WorkbenchOCBubbleButton")
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._index, self.mapToGlobal(self.rect().bottomLeft())))
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self._index))
        actions_layout.addWidget(edit_btn)
        actions_layout.addWidget(remove_btn)
        root.addWidget(actions)

        self.setFixedWidth(_dp(288))
        self.apply_style()

    def _section_label(self, key: str) -> QLabel:
        label = QLabel(self._t.t(key), self)
        label.setObjectName("WorkbenchOCBubbleSectionLabel")
        return label

    def _stepper(self, label_text: str, value: int) -> tuple[QWidget, QSpinBox]:
        box = QWidget(self)
        box.setObjectName("WorkbenchOCBubbleStepper")
        layout = QHBoxLayout(box)
        layout.setContentsMargins(_dp(8), _dp(4), _dp(8), _dp(4))
        layout.setSpacing(_dp(6))
        label = QLabel(label_text, box)
        label.setObjectName("WorkbenchOCBubbleStepperLabel")
        spin = QSpinBox(box)
        spin.setRange(0, 9999)
        spin.setValue(value)
        spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        layout.addWidget(label)
        layout.addWidget(spin, 1)
        return box, spin

    def _emit_numeric(self, order: int, depth: int) -> None:
        self._entry = replace(self._entry, order=order, depth=depth)
        self.oc_changed.emit(self._index, self._entry)

    def _switch_outfit(self, outfit_name: str) -> None:
        outfits = [replace(outfit, active=outfit.name == outfit_name) for outfit in self._entry.outfits]
        self._entry = replace(self._entry, outfits=outfits)
        self.oc_changed.emit(self._index, self._entry)

    def apply_style(self) -> None:
        pal = current_palette()
        self.setStyleSheet(
            f"QFrame#WorkbenchOCBubble {{ background: {pal['bg_card']}; border: 1px solid {pal['line_strong']}; border-radius: {_dp(6)}px; }}"
            f"QWidget#WorkbenchOCBubbleHead, QWidget#WorkbenchOCBubbleSection {{ background: transparent; border-bottom: 1px solid {pal['line']}; }}"
            f"QLabel#WorkbenchOCBubbleAvatar {{ background: {pal['accent_sub']}; border: 1px solid {pal['accent_hover']}; border-radius: {_dp(16)}px; }}"
            f"QLabel#WorkbenchOCBubbleName {{ color: {pal['text']}; font-size: {_fs('fs_14')}; font-weight: 500; }}"
            f"QLabel#WorkbenchOCBubbleSub, QLabel#WorkbenchOCBubbleSectionLabel, QLabel#WorkbenchOCBubbleStepperLabel {{ color: {pal['text_label']}; font-size: {_fs('fs_10')}; }}"
            f"QWidget#WorkbenchOCBubbleStepper {{ background: {pal['bg_input']}; border: 1px solid {pal['line']}; border-radius: {_dp(4)}px; }}"
            f"QSpinBox {{ background: transparent; color: {pal['text']}; border: none; font-size: {_fs('fs_12')}; }}"
            f"QPushButton#WorkbenchOCOutfitPill, QPushButton#WorkbenchOCBubbleButton {{ background: {pal['bg_input']}; color: {pal['text_body']}; border: 1px solid {pal['line']}; border-radius: {_dp(4)}px; padding: {_dp(4)}px {_dp(10)}px; font-size: {_fs('fs_11')}; }}"
            f"QPushButton#WorkbenchOCOutfitPill[active=\"true\"], QPushButton#WorkbenchOCBubblePrimary {{ background: {pal['accent_sub']}; color: {pal['accent_text']}; border: 1px solid {pal['accent_hover']}; border-radius: {_dp(4)}px; padding: {_dp(6)}px; font-size: {_fs('fs_11')}; }}"
            f"QLabel#WorkbenchOCBubbleTag {{ background: {pal['bg_input']}; color: {pal['text_body']}; border: 1px solid {pal['line']}; border-radius: {_dp(3)}px; padding: {_dp(2)}px {_dp(6)}px; font-size: {_fs('fs_10')}; }}"
        )


class WorkbenchOCStrip(QFrame):
    """Titlebar OC chip strip matching the v3 workbench chrome."""

    add_requested = pyqtSignal(QPoint)
    edit_requested = pyqtSignal(int, QPoint)
    remove_requested = pyqtSignal(int)
    open_library_requested = pyqtSignal(QPoint)
    oc_changed = pyqtSignal(int, object)

    def __init__(self, translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WorkbenchOCStrip")
        self._t = translator
        self._entries: list[tuple[int, OCEntry]] = []
        self._bubble: _OCBubble | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(_dp(6), 0, 0, 0)
        layout.setSpacing(_dp(4))

        self._divider = QLabel(self)
        self._divider.setObjectName("WorkbenchOCDivider")
        self._divider.setFixedSize(_dp(1), _dp(12))
        layout.addWidget(self._divider)

        self._empty = QLabel(self)
        self._empty.setObjectName("WorkbenchOCEmpty")
        self._empty.hide()
        layout.addWidget(self._empty)

        self._chips_host = QWidget(self)
        self._chips_layout = QHBoxLayout(self._chips_host)
        self._chips_layout.setContentsMargins(0, 0, 0, 0)
        self._chips_layout.setSpacing(_dp(4))
        layout.addWidget(self._chips_host)

        self._add_btn = QPushButton("+", self)
        self._add_btn.setObjectName("WorkbenchOCAdd")
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.setFixedSize(_dp(18), _dp(18))
        self._add_btn.clicked.connect(self._emit_add_requested)
        layout.addWidget(self._add_btn)

        layout.addStretch(1)
        self.apply_style()
        self.set_entries([])

    def sizeHint(self) -> QSize:
        width = self._divider.width() + self._add_btn.width() + _dp(18)
        if self._entries:
            for i in range(self._chips_layout.count()):
                item = self._chips_layout.itemAt(i)
                widget = item.widget() if item is not None else None
                if widget is not None and not widget.isHidden():
                    width += max(widget.minimumWidth(), widget.sizeHint().width()) + _dp(4)
        return QSize(min(width, _dp(420)), _dp(28))

    def set_entries(self, entries: list[OCEntry]) -> None:
        self._entries = [
            (index, entry)
            for index, entry in enumerate(entries)
            if getattr(entry, "enabled", True) and _has_visible_oc_content(entry)
        ]
        while self._chips_layout.count():
            item = self._chips_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._empty.hide()
        self._chips_host.setVisible(bool(self._entries))
        self.retranslate_ui()
        for source_index, entry in self._entries[:4]:
            chip = QPushButton(self._chip_text(entry), self._chips_host)
            chip.setObjectName("WorkbenchOCChip")
            chip.setProperty("sourceIndex", source_index)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setMinimumWidth(_dp(46))
            chip.setMaximumWidth(_dp(150))
            chip.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            chip.clicked.connect(
                lambda checked=False, i=source_index, e=entry, b=chip: self._show_oc_quick_menu(i, e, b)
            )
            chip.customContextMenuRequested.connect(
                lambda pos, i=source_index, e=entry, b=chip: self._show_oc_context_menu(
                    i, e, b.mapToGlobal(pos)
                )
            )
            chip.installEventFilter(self)
            self._chips_layout.addWidget(chip)
        self.updateGeometry()
        parent = self.parentWidget()
        if parent is not None:
            parent.updateGeometry()
        self.apply_style()

    def eventFilter(self, watched, event) -> bool:
        return super().eventFilter(watched, event)

    def retranslate_ui(self) -> None:
        self._empty.setText(self._t.t("workbench_oc_empty"))
        self._add_btn.setToolTip(self._t.t("workbench_add_oc"))

    def _chip_text(self, entry: OCEntry) -> str:
        outfit = next((o.name for o in entry.outfits if o.active and o.name.strip()), "")
        fallback = self._t.t("character_name")
        if outfit:
            text = f"{entry.character_name or fallback}  {outfit}"
        else:
            text = entry.character_name or fallback
        return self.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, _dp(132))

    def _emit_add_requested(self) -> None:
        self.add_requested.emit(self._add_btn.mapToGlobal(self._add_btn.rect().bottomLeft()))

    def _show_oc_quick_menu(self, index: int, entry: OCEntry, button: QPushButton) -> None:
        if self._bubble is not None:
            self._bubble.close()
            self._bubble = None
        bubble = _OCBubble(self._t, index, entry, self.window())
        bubble.edit_requested.connect(self.edit_requested)
        bubble.remove_requested.connect(self.remove_requested)
        bubble.oc_changed.connect(self.oc_changed)
        bubble.destroyed.connect(lambda *_: setattr(self, "_bubble", None))
        pos = button.mapToGlobal(QPoint(0, button.height() + _dp(8)))
        bubble.move(pos)
        self._bubble = bubble
        bubble.show()

    def _show_oc_context_menu(self, index: int, entry: OCEntry, global_pos: QPoint) -> None:
        menu = self.build_context_menu(index, entry, global_pos)
        menu.exec(global_pos)

    def build_quick_menu(self, index: int, entry: OCEntry) -> QMenu:
        menu = QMenu(self)
        menu.setObjectName("WorkbenchOCMenu")
        name = entry.character_name or self._t.t("character_name")
        menu.addSection(name)
        menu.addAction(
            self._t.t("workbench_oc_order_depth").format(order=entry.order, depth=entry.depth)
        ).setEnabled(False)
        menu.addSeparator()
        self._add_order_depth_action(menu, index, entry)
        outfits = [o for o in entry.outfits if o.name.strip()]
        if outfits:
            menu.addSection(self._t.t("workbench_oc_outfit"))
            for outfit in outfits:
                action = menu.addAction(outfit.name)
                action.setCheckable(True)
                action.setChecked(outfit.active)
                action.triggered.connect(
                    lambda checked=False, outfit_name=outfit.name: self._switch_outfit(index, entry, outfit_name)
                )
        if entry.tags.strip():
            menu.addSeparator()
            preview = entry.tags.strip().replace("\n", " ")
            menu.addAction((preview[:64] + "...") if len(preview) > 64 else preview).setEnabled(False)
        self._style_menu(menu)
        return menu

    def build_context_menu(self, index: int, entry: OCEntry, anchor_pos: QPoint | None = None) -> QMenu:
        menu = QMenu(self)
        menu.setObjectName("WorkbenchOCMenu")
        name = entry.character_name or self._t.t("character_name")
        anchor = anchor_pos or self.mapToGlobal(self.rect().bottomLeft())
        menu.addSection(name)
        menu.addAction(self._t.t("workbench_remove_oc"), lambda: self.remove_requested.emit(index))
        menu.addSeparator()
        menu.addAction(self._t.t("workbench_edit_oc"), lambda: self.edit_requested.emit(index, anchor))
        menu.addAction(self._t.t("workbench_open_oc_library"), lambda: self.open_library_requested.emit(anchor))
        self._style_menu(menu)
        return menu

    def _add_order_depth_action(self, menu: QMenu, index: int, entry: OCEntry) -> None:
        row = QWidget(menu)
        layout = QVBoxLayout(row)
        layout.setContentsMargins(_dp(8), _dp(4), _dp(8), _dp(4))
        layout.setSpacing(_dp(4))

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(_dp(6))
        order_label = QLabel(self._t.t("workbench_oc_order_label"), row)
        depth_label = QLabel(self._t.t("workbench_oc_depth_label"), row)
        order = QSpinBox(row)
        order.setRange(0, 9999)
        order.setValue(entry.order)
        order.setFixedWidth(_dp(62))
        depth = QSpinBox(row)
        depth.setRange(0, 999)
        depth.setValue(entry.depth)
        depth.setFixedWidth(_dp(56))
        controls.addWidget(order_label)
        controls.addWidget(order)
        controls.addWidget(depth_label)
        controls.addWidget(depth)
        layout.addLayout(controls)

        def emit_change() -> None:
            self.oc_changed.emit(index, replace(entry, order=order.value(), depth=depth.value()))

        order.valueChanged.connect(lambda _: emit_change())
        depth.valueChanged.connect(lambda _: emit_change())
        pal = current_palette()
        row.setStyleSheet(
            f"QLabel {{ color: {pal['text_label']}; font-size: {_fs('fs_10')}; }}"
            f"QSpinBox {{ background: {pal['bg_input']}; color: {pal['text']}; border: 1px solid {pal['line_strong']}; "
            f"border-radius: {_dp(3)}px; padding: {_dp(2)}px {_dp(4)}px; font-size: {_fs('fs_10')}; }}"
        )
        action = QWidgetAction(menu)
        action.setDefaultWidget(row)
        menu.addAction(action)

    def _switch_outfit(self, index: int, entry: OCEntry, outfit_name: str) -> None:
        outfits = [
            replace(outfit, active=outfit.name == outfit_name)
            for outfit in entry.outfits
        ]
        self.oc_changed.emit(index, replace(entry, outfits=outfits))

    def apply_style(self) -> None:
        pal = current_palette()
        self.setStyleSheet(
            "QFrame#WorkbenchOCStrip { background: transparent; border: none; }"
            f"QLabel#WorkbenchOCDivider {{ background: {pal['line']}; }}"
            f"QLabel#WorkbenchOCEmpty {{ color: {pal['text_label']}; font-style: italic; font-size: {_fs('fs_11')}; padding-left: {_dp(4)}px; }}"
            f"QPushButton#WorkbenchOCChip {{ background: {pal['accent_sub']}; color: {pal['accent_text']}; "
            f"border: 1px solid {pal['accent']}; border-radius: {_dp(4)}px; padding: {_dp(2)}px {_dp(8)}px; "
            f"font-size: {_fs('fs_10')}; text-align: left; }}"
            f"QPushButton#WorkbenchOCChip:hover {{ background: {pal['accent']}; border-color: {pal['accent_hover']}; }}"
            f"QPushButton#WorkbenchOCAdd {{ background: transparent; color: {pal['text_label']}; border: 1px dashed {pal['line_strong']}; "
            f"border-radius: {_dp(9)}px; padding: 0px; font-size: {_fs('fs_11')}; }}"
            f"QPushButton#WorkbenchOCAdd:hover {{ color: {pal['accent_text']}; border-color: {pal['accent_hover']}; background: {pal['accent_sub']}; }}"
        )

    @staticmethod
    def _style_menu(menu: QMenu) -> None:
        apply_app_menu_style(menu)
