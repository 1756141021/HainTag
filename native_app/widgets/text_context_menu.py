from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QLineEdit, QMenu, QTextEdit, QWidget

from ..theme import _fs, current_palette
from ..ui_tokens import _dp

def apply_app_menu_style(menu: QMenu) -> None:
    """Apply the app palette to menus without hardcoded per-surface colors."""
    p = current_palette()
    menu.setStyleSheet(
        f"QMenu {{ background: {p['bg_menu']}; color: {p['text']}; "
        f"border: 1px solid {p['line_strong']}; border-radius: {_dp(6)}px; "
        f"padding: {_dp(5)}px; font-size: {_fs('fs_11')}; }}"
        f"QMenu::item {{ background: transparent; color: {p['text']}; "
        f"padding: {_dp(6)}px {_dp(24)}px {_dp(6)}px {_dp(12)}px; border-radius: {_dp(4)}px; }}"
        f"QMenu::item:selected {{ background: {p['hover_bg_strong']}; color: {p['text']}; }}"
        f"QMenu::item:disabled {{ color: {p['disabled_text']}; }}"
        f"QMenu::separator {{ height: 1px; background: {p['line']}; margin: {_dp(5)}px {_dp(6)}px; }}"
    )


def add_text_edit_actions(menu: QMenu, editor: QTextEdit, translator) -> dict[str, QAction]:
    actions: dict[str, QAction] = {}
    actions["undo"] = menu.addAction(translator.t("edit_undo"))
    actions["undo"].setEnabled(editor.document().isUndoAvailable())
    actions["redo"] = menu.addAction(translator.t("edit_redo"))
    actions["redo"].setEnabled(editor.document().isRedoAvailable())
    menu.addSeparator()

    has_selection = editor.textCursor().hasSelection()
    actions["cut"] = menu.addAction(translator.t("edit_cut"))
    actions["cut"].setEnabled(has_selection and not editor.isReadOnly())
    actions["copy"] = menu.addAction(translator.t("edit_copy"))
    actions["copy"].setEnabled(has_selection)
    actions["paste"] = menu.addAction(translator.t("edit_paste"))
    actions["paste"].setEnabled(bool(QApplication.clipboard().text()) and not editor.isReadOnly())
    actions["delete"] = menu.addAction(translator.t("delete"))
    actions["delete"].setEnabled(has_selection and not editor.isReadOnly())
    menu.addSeparator()

    actions["select_all"] = menu.addAction(translator.t("select_all"))
    actions["select_all"].setEnabled(bool(editor.toPlainText()))
    return actions


def handle_text_edit_action(chosen: QAction | None, actions: dict[str, QAction], editor: QTextEdit) -> bool:
    if chosen is actions.get("undo"):
        editor.undo()
    elif chosen is actions.get("redo"):
        editor.redo()
    elif chosen is actions.get("cut"):
        editor.cut()
    elif chosen is actions.get("copy"):
        editor.copy()
    elif chosen is actions.get("paste"):
        editor.paste()
    elif chosen is actions.get("delete"):
        cursor = editor.textCursor()
        cursor.removeSelectedText()
        editor.setTextCursor(cursor)
    elif chosen is actions.get("select_all"):
        editor.selectAll()
    else:
        return False
    return True


def add_line_edit_actions(menu: QMenu, editor: QLineEdit, translator) -> dict[str, QAction]:
    actions: dict[str, QAction] = {}
    actions["undo"] = menu.addAction(translator.t("edit_undo"))
    actions["undo"].setEnabled(editor.isUndoAvailable())
    actions["redo"] = menu.addAction(translator.t("edit_redo"))
    actions["redo"].setEnabled(editor.isRedoAvailable())
    menu.addSeparator()

    has_selection = editor.hasSelectedText()
    actions["cut"] = menu.addAction(translator.t("edit_cut"))
    actions["cut"].setEnabled(has_selection and not editor.isReadOnly())
    actions["copy"] = menu.addAction(translator.t("edit_copy"))
    actions["copy"].setEnabled(has_selection)
    actions["paste"] = menu.addAction(translator.t("edit_paste"))
    actions["paste"].setEnabled(bool(QApplication.clipboard().text()) and not editor.isReadOnly())
    actions["delete"] = menu.addAction(translator.t("delete"))
    actions["delete"].setEnabled(has_selection and not editor.isReadOnly())
    menu.addSeparator()

    actions["select_all"] = menu.addAction(translator.t("select_all"))
    actions["select_all"].setEnabled(bool(editor.text()))
    return actions


def handle_line_edit_action(chosen: QAction | None, actions: dict[str, QAction], editor: QLineEdit) -> bool:
    if chosen is actions.get("undo"):
        editor.undo()
    elif chosen is actions.get("redo"):
        editor.redo()
    elif chosen is actions.get("cut"):
        editor.cut()
    elif chosen is actions.get("copy"):
        editor.copy()
    elif chosen is actions.get("paste"):
        editor.paste()
    elif chosen is actions.get("delete"):
        editor.del_()
    elif chosen is actions.get("select_all"):
        editor.selectAll()
    else:
        return False
    return True


def show_text_edit_context_menu(
    editor: QTextEdit,
    translator,
    parent: QWidget,
    global_pos: QPoint,
) -> None:
    """Show a localized edit menu for QTextEdit-like widgets."""
    menu = QMenu(parent)
    apply_app_menu_style(menu)
    actions = add_text_edit_actions(menu, editor, translator)
    chosen = menu.exec(global_pos)
    handle_text_edit_action(chosen, actions, editor)


def show_line_edit_context_menu(
    editor: QLineEdit,
    translator,
    parent: QWidget,
    global_pos: QPoint,
) -> None:
    """Show a localized edit menu for QLineEdit widgets."""
    menu = QMenu(parent)
    apply_app_menu_style(menu)
    actions = add_line_edit_actions(menu, editor, translator)
    chosen = menu.exec(global_pos)
    handle_line_edit_action(chosen, actions, editor)


def install_localized_context_menus(root: QWidget, translator) -> None:
    """Replace Qt default edit menus without touching widgets that already own custom menus."""
    editors = []
    if isinstance(root, (QTextEdit, QLineEdit)):
        editors.append(root)
    editors.extend(root.findChildren(QTextEdit))
    editors.extend(root.findChildren(QLineEdit))
    for editor in editors:
        if editor.property("_localized_context_menu_installed"):
            continue
        if editor.contextMenuPolicy() != Qt.ContextMenuPolicy.DefaultContextMenu:
            continue
        editor.setProperty("_localized_context_menu_installed", True)
        editor.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        if isinstance(editor, QTextEdit):
            editor.customContextMenuRequested.connect(
                lambda pos, edit=editor: show_text_edit_context_menu(edit, translator, edit, edit.mapToGlobal(pos))
            )
        else:
            editor.customContextMenuRequested.connect(
                lambda pos, edit=editor: show_line_edit_context_menu(edit, translator, edit, edit.mapToGlobal(pos))
            )
