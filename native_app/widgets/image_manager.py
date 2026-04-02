"""Image Manager — standalone frameless browser window.

Design language: minimalist, breathable, line-driven, restrained.
All colors from palette (DARK_PALETTE / LIGHT_PALETTE), theme-following.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import sys
import shutil
import subprocess
from pathlib import Path

from PyQt6.QtCore import (
    QAbstractListModel,
    QEvent,
    QMimeData,
    QModelIndex,
    QPoint,
    QRect,
    QSize,
    QTimer,
    QUrl,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QCursor, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..i18n import Translator
from ..metadata import MetadataReader, MetadataWriter, ImageMetadata
from ..metadata.thumb_cache import ThumbCache
from ..theme import _fs, current_palette, is_theme_light
from ..ui_tokens import CLS_METADATA_TEXT
from .collapsible_section import CollapsibleSection

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

# Win32 constants for frameless window resize
if sys.platform == "win32":
    _GWL_STYLE = -16
    _WS_THICKFRAME = 0x00040000
    _WS_SYSMENU = 0x00080000
    _SWP_FRAMECHANGED = 0x0020
    _SWP_NOMOVE = 0x0002
    _SWP_NOSIZE = 0x0001
    _SWP_NOZORDER = 0x0004
    _SWP_NOACTIVATE = 0x0010
    _WM_NCCALCSIZE = 0x0083
    _WM_NCHITTEST = 0x0084
    _HTCAPTION = 2
    _HTLEFT = 10
    _HTRIGHT = 11
    _HTTOP = 12
    _HTTOPLEFT = 13
    _HTTOPRIGHT = 14
    _HTBOTTOM = 15
    _HTBOTTOMLEFT = 16
    _HTBOTTOMRIGHT = 17
_NEW_FOLDER_SENTINEL = "__new__"


def _send_to_recycle_bin(paths: list[str]) -> bool:
    """Move files to Windows Recycle Bin via SHFileOperationW."""
    if not paths:
        return True
    # Double-null terminated string of paths
    pFrom = "\0".join(os.path.abspath(p) for p in paths) + "\0\0"

    class SHFILEOPSTRUCT(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.wintypes.HWND),
            ("wFunc", ctypes.c_uint),
            ("pFrom", ctypes.c_wchar_p),
            ("pTo", ctypes.c_wchar_p),
            ("fFlags", ctypes.wintypes.WORD),
            ("fAnyOperationsAborted", ctypes.wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", ctypes.c_wchar_p),
        ]

    FO_DELETE = 3
    FOF_ALLOWUNDO = 0x0040
    FOF_NOCONFIRMATION = 0x0010
    FOF_SILENT = 0x0004

    op = SHFILEOPSTRUCT()
    op.wFunc = FO_DELETE
    op.pFrom = pFrom
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT
    return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0


def _p() -> dict[str, str]:
    return current_palette()


class _StyledDialog(QWidget):
    """Minimal themed dialog matching the image manager's design language."""

    accepted = pyqtSignal(str)
    rejected = pyqtSignal()

    def __init__(self, title: str, label: str, default: str = "",
                 confirm: str = "OK", cancel: str = "Cancel",
                 mode: str = "input", parent=None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._result: str | None = None
        p = _p()

        surface = QWidget(self)
        surface.setStyleSheet(f"""
            QWidget#DialogSurface {{
                background: {p['bg']};
                border: 1px solid {p['line_strong']};
                border-radius: 8px;
            }}
            QLabel {{ color: {p['text']}; background: transparent; }}
            QLineEdit {{
                background: {p['bg_content']};
                color: {p['text']};
                border: 1px solid {p['line']};
                border-radius: 4px;
                padding: 6px 8px;
                font-size: {_fs('fs_12')};
                selection-background-color: {p['accent']};
            }}
            QLineEdit:focus {{ border-color: {p['accent']}; }}
            QPushButton {{
                background: transparent;
                color: {p['text_muted']};
                border: 1px solid {p['line']};
                border-radius: 4px;
                padding: 6px 20px;
                font-size: {_fs('fs_11')};
            }}
            QPushButton:hover {{
                border-color: {p['line_strong']};
                color: {p['text']};
            }}
            QPushButton#DialogAccept {{
                background: {p['accent']};
                color: {p['accent_text']};
                border: 1px solid {p['accent']};
            }}
            QPushButton#DialogAccept:hover {{ opacity: 0.9; }}
        """)
        surface.setObjectName("DialogSurface")

        layout = QVBoxLayout(surface)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title_lbl = QLabel(title, surface)
        title_lbl.setStyleSheet(f"font-size: {_fs('fs_13')}; font-weight: bold; color: {p['text']};")
        layout.addWidget(title_lbl)

        if label and label != title:
            desc = QLabel(label, surface)
            desc.setStyleSheet(f"font-size: {_fs('fs_11')}; color: {p['text_dim']};")
            layout.addWidget(desc)

        self._edit = None
        if mode == "input":
            self._edit = QLineEdit(surface)
            self._edit.setText(default)
            self._edit.selectAll()
            self._edit.returnPressed.connect(self._accept)
            layout.addWidget(self._edit)
        elif mode == "confirm":
            if default:
                msg = QLabel(default, surface)
                msg.setWordWrap(True)
                msg.setStyleSheet(f"font-size: {_fs('fs_11')}; color: {p['text_muted']};")
                layout.addWidget(msg)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()
        cancel_btn = QPushButton(cancel, surface)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self._reject)
        btn_row.addWidget(cancel_btn)
        accept_btn = QPushButton(confirm, surface)
        accept_btn.setObjectName("DialogAccept")
        accept_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        accept_btn.clicked.connect(self._accept)
        btn_row.addWidget(accept_btn)
        layout.addLayout(btn_row)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(surface)
        self.setFixedWidth(320)
        self.adjustSize()

    def _accept(self):
        self._result = self._edit.text().strip() if self._edit else ""
        self.accepted.emit(self._result)
        self.close()

    def _reject(self):
        self._result = None
        self.rejected.emit()
        self.close()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self._reject()
        else:
            super().keyPressEvent(e)

    @staticmethod
    def get_text(parent, title: str, label: str, default: str = "",
                 confirm: str = "OK", cancel: str = "Cancel") -> tuple[str, bool]:
        dlg = _StyledDialog(title, label, default, confirm, cancel, "input", parent)
        dlg.move(QCursor.pos() - QPoint(160, 40))
        result = [None]
        loop = __import__('PyQt6.QtCore', fromlist=['QEventLoop']).QEventLoop()
        dlg.accepted.connect(lambda t: (result.__setitem__(0, t), loop.quit()))
        dlg.rejected.connect(loop.quit)
        dlg.show()
        if dlg._edit:
            dlg._edit.setFocus()
        loop.exec()
        return (result[0] or "", result[0] is not None)

    @staticmethod
    def confirm(parent, title: str, message: str,
                confirm: str = "OK", cancel: str = "Cancel") -> bool:
        dlg = _StyledDialog(title, "", message, confirm, cancel, "confirm", parent)
        dlg.move(QCursor.pos() - QPoint(160, 40))
        result = [False]
        loop = __import__('PyQt6.QtCore', fromlist=['QEventLoop']).QEventLoop()
        dlg.accepted.connect(lambda _: (result.__setitem__(0, True), loop.quit()))
        dlg.rejected.connect(loop.quit)
        dlg.show()
        loop.exec()
        return result[0]


def _clamp_to_screen(pos: QPoint, size: QSize, margin: int = 4) -> QPoint:
    """Adjust pos so popup stays fully visible on screen."""
    from PyQt6.QtGui import QGuiApplication
    screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
    if not screen:
        return pos
    avail = screen.availableGeometry()
    x, y = pos.x(), pos.y()
    if x + size.width() + margin > avail.right() + 1:
        x = avail.right() + 1 - size.width() - margin
    if x < avail.left() + margin:
        x = avail.left() + margin
    if y + size.height() + margin > avail.bottom() + 1:
        y = avail.bottom() + 1 - size.height() - margin
    if y < avail.top() + margin:
        y = avail.top() + margin
    return QPoint(x, y)


def _im_qss(p: dict[str, str]) -> str:
    """Generate a self-contained QSS for the image manager window."""
    return f"""
    /* ── Surface ── */
    #ImSurface {{
        background: {p['bg']};
        border: 1px solid {p['line_strong']};
        border-radius: 10px;
    }}

    /* ── Title bar ── */
    #ImTitleBar {{
        background: {p['bg_titlebar']};
        border-top-left-radius: 10px;
        border-top-right-radius: 10px;
    }}
    #ImTitleLabel {{
        color: {p['text_muted']};
        font-size: {_fs('fs_11')};
        letter-spacing: 3px;
        text-transform: uppercase;
    }}
    #ImTitleBtn {{
        background: transparent;
        color: {p['text_dim']};
        border: none;
        font-size: {_fs('fs_13')};
    }}
    #ImTitleBtn:hover {{
        color: {p['text']};
    }}

    /* ── Toolbar ── */
    #ImToolbar {{
        background: {p['bg_surface']};
        border-bottom: 1px solid {p['line']};
    }}
    #ImToolLabel {{
        color: {p['text_dim']};
        font-size: {_fs('fs_10')};
        letter-spacing: 1px;
    }}
    #ImToolBtn {{
        background: transparent;
        color: {p['text_muted']};
        border: 1px solid {p['line']};
        border-radius: 3px;
        padding: 2px 10px;
        font-size: {_fs('fs_10')};
    }}
    #ImToolBtn:hover {{
        border-color: {p['line_strong']};
        color: {p['text']};
    }}

    /* ── Grid ── */
    #ImGrid {{
        background: {p['bg_workspace']};
        border: none;
    }}

    /* ── Detail panel ── */
    #ImDetail {{
        background: {p['bg_surface']};
        border-left: 1px solid {p['line']};
    }}
    #ImDetailInfo {{
        color: {p['text_dim']};
        font-size: {_fs('fs_10')};
        letter-spacing: 0.5px;
    }}
    #ImDetailBtn {{
        background: transparent;
        color: {p['text_muted']};
        border: 1px solid {p['line']};
        border-radius: 3px;
        padding: 3px 8px;
        font-size: {_fs('fs_10')};
    }}
    #ImDetailBtn:hover {{
        border-color: {p['accent_text']};
        color: {p['accent_text']};
    }}

    /* ── Splitter ── */
    QSplitter#ImSplitter::handle {{
        background: {p['line']};
        width: 1px;
    }}

    /* ── SpinBox / Slider ── */
    QSpinBox {{
        background: {p['bg_input']};
        color: {p['text_body']};
        border: 1px solid {p['line']};
        border-radius: 3px;
        padding: 1px 4px;
        font-size: {_fs('fs_11')};
    }}
    QSlider::groove:horizontal {{
        height: 2px;
        background: {p['slider_groove']};
        border-radius: 1px;
    }}
    QSlider::handle:horizontal {{
        width: 10px;
        height: 10px;
        margin: -4px 0;
        background: {p['text_muted']};
        border-radius: 5px;
    }}
    QSlider::handle:horizontal:hover {{
        background: {p['accent_text']};
    }}

    /* ── Scrollbar ── */
    QScrollBar:vertical {{
        width: 6px;
        background: transparent;
    }}
    QScrollBar::handle:vertical {{
        background: {p['scrollbar']};
        border-radius: 3px;
        min-height: 30px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}

    /* ── Text edits (metadata) ── */
    QTextEdit[class="MetadataText"] {{
        background: {p['bg_input']};
        border: 1px solid {p['line']};
        border-radius: 4px;
        color: {p['text_body']};
        font-size: {_fs('fs_11')};
        padding: 4px 6px;
        selection-background-color: {p['selection_bg']};
    }}
    """


# ═══════════════════════════════════════════════════════════
#  Model
# ═══════════════════════════════════════════════════════════

_ROLE_IS_DIR = Qt.ItemDataRole.UserRole + 1


class ThumbnailModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._dirs: list[str] = []  # directory paths (always shown first)
        self._all: list[str] = []   # image paths
        self._loaded: list[str] = []
        self._buf = 50
        self._sort_key = "mtime_desc"

    def set_source(self, paths: list[str], buffer_size: int = 50):
        self._dirs = []
        self.beginResetModel()
        self._all, self._loaded, self._buf = list(paths), [], buffer_size
        self.endResetModel()
        self.fetchMore(QModelIndex())

    def set_folder_contents(self, dirs: list[str], images: list[str], buffer_size: int = 50):
        self._apply_sort(images)
        self.beginResetModel()
        self._dirs = list(dirs)
        self._all = list(images)
        self._loaded = []
        self._buf = buffer_size
        self.endResetModel()
        self.fetchMore(QModelIndex())

    def set_sort(self, key: str):
        self._sort_key = key
        self._apply_sort(self._all)
        self.beginResetModel()
        self._loaded = self._all[:len(self._loaded)]
        self.endResetModel()

    def _apply_sort(self, p: list[str]):
        try:
            sorts = {"name_asc": (lambda x: os.path.basename(x).lower(), False),
                     "name_desc": (lambda x: os.path.basename(x).lower(), True),
                     "mtime_desc": (lambda x: os.path.getmtime(x), True),
                     "mtime_asc": (lambda x: os.path.getmtime(x), False),
                     "size_desc": (lambda x: os.path.getsize(x), True),
                     "size_asc": (lambda x: os.path.getsize(x), False)}
            if self._sort_key in sorts:
                fn, rev = sorts[self._sort_key]
                p.sort(key=fn, reverse=rev)
        except OSError:
            pass

    def rowCount(self, parent=QModelIndex()):
        return len(self._dirs) + len(self._loaded)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        nd = len(self._dirs)
        if row < nd:
            # Directory entry
            path = self._dirs[row]
            if role == Qt.ItemDataRole.DisplayRole:
                return os.path.basename(path)
            if role == Qt.ItemDataRole.UserRole:
                return path
            if role == _ROLE_IS_DIR:
                return True
        else:
            # Image entry
            img_row = row - nd
            if img_row >= len(self._loaded):
                return None
            path = self._loaded[img_row]
            if role == Qt.ItemDataRole.DisplayRole:
                return os.path.basename(path)
            if role == Qt.ItemDataRole.UserRole:
                return path
            if role == _ROLE_IS_DIR:
                return False
        return None

    def canFetchMore(self, parent=QModelIndex()):
        return len(self._loaded) < len(self._all)

    def fetchMore(self, parent=QModelIndex()):
        s, e = len(self._loaded), min(len(self._loaded) + self._buf, len(self._all))
        if s >= e:
            return
        nd = len(self._dirs)
        self.beginInsertRows(QModelIndex(), nd + s, nd + e - 1)
        self._loaded.extend(self._all[s:e])
        self.endInsertRows()

    def path_at(self, idx: QModelIndex) -> str:
        if not idx.isValid():
            return ""
        row = idx.row()
        nd = len(self._dirs)
        if row < nd:
            return self._dirs[row]
        img_row = row - nd
        return self._loaded[img_row] if 0 <= img_row < len(self._loaded) else ""

    def is_dir(self, idx: QModelIndex) -> bool:
        return idx.isValid() and idx.row() < len(self._dirs)

    def total_count(self):
        return len(self._all)

    def loaded_count(self):
        return len(self._loaded)

    def mimeData(self, indexes):
        m = QMimeData()
        m.setUrls([QUrl.fromLocalFile(self.path_at(i)) for i in indexes if self.path_at(i)])
        return m

    def mimeTypes(self):
        return ["text/uri-list"]

    def flags(self, index):
        f = super().flags(index)
        return f | Qt.ItemFlag.ItemIsDragEnabled if index.isValid() else f


# ═══════════════════════════════════════════════════════════
#  Delegate — minimal, breathable
# ═══════════════════════════════════════════════════════════

class ThumbnailDelegate(QStyledItemDelegate):
    def __init__(self, cache: ThumbCache, ts: int = 160, parent=None):
        super().__init__(parent)
        self._cache, self._ts = cache, ts
        self._likes: set[str] = set()
        self._cut: set[str] = set()
        self._sizing = False  # True while slider is being dragged

    def set_thumb_size(self, s: int, sizing: bool = False):
        self._ts = s
        self._sizing = sizing

    def set_likes(self, likes: set[str]):
        self._likes = likes

    def set_cut(self, cut: set[str]):
        self._cut = cut

    def sizeHint(self, option, index):
        return QSize(self._ts + 12, self._ts + 28)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = option.rect
        path = index.data(Qt.ItemDataRole.UserRole)
        is_dir = index.data(_ROLE_IS_DIR)
        p = _p()

        # Hover / Selection — subtle rounded rect
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(QColor(p['accent_text']), 1))
            painter.setBrush(QColor(p['accent']))
            painter.drawRoundedRect(r.adjusted(2, 2, -2, -2), 6, 6)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(p['hover_bg']))
            painter.drawRoundedRect(r.adjusted(2, 2, -2, -2), 6, 6)

        tr = r.adjusted(6, 6, -6, -22)

        if is_dir:
            # Directory — folder icon (simple drawn shape)
            cx, cy = tr.center().x(), tr.center().y()
            fw, fh = min(tr.width(), 60), min(tr.height(), 48)
            fx, fy = cx - fw // 2, cy - fh // 2
            painter.setPen(QPen(QColor(p['text_dim']), 1.5))
            painter.setBrush(QColor(p['hover_bg']))
            # Tab
            painter.drawRoundedRect(fx, fy, fw // 3, fh // 6, 2, 2)
            # Body
            painter.drawRoundedRect(fx, fy + fh // 6 - 2, fw, fh - fh // 6 + 2, 4, 4)
        else:
            # Image thumbnail
            pm = self._cache.get(path, self._ts) if path else None
            if pm is None and path:
                pm = self._cache.get_any(path)
                if pm and not pm.isNull():
                    pm = pm.scaled(QSize(self._ts, self._ts),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.FastTransformation)
                if not self._sizing:
                    v = option.widget
                    self._cache.request(path, self._ts,
                        lambda _p, _px, vw=v, row=index.row(): self._on_ready(vw, row))
            if pm and not pm.isNull():
                x = tr.x() + (tr.width() - pm.width()) // 2
                y = tr.y() + (tr.height() - pm.height()) // 2
                if path in self._cut:
                    painter.setOpacity(0.35)
                painter.drawPixmap(x, y, pm)
                if path in self._cut:
                    painter.setOpacity(1.0)
            elif path:
                painter.setPen(QPen(QColor(p['line_strong']), 1, Qt.PenStyle.DotLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(tr.adjusted(8, 8, -8, -8), 4, 4)

        # Like badge — minimal circle
        if path and path in self._likes:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(200, 70, 70, 200))
            painter.drawEllipse(r.right() - 20, r.top() + 6, 14, 14)
            painter.setPen(QColor(255, 255, 255))
            f = painter.font()
            f.setPointSize(8)
            painter.setFont(f)
            painter.drawText(r.right() - 20, r.top() + 6, 14, 14, Qt.AlignmentFlag.AlignCenter, "♥")

        # Filename — restrained, small
        nr = r.adjusted(6, r.height() - 18, -6, -3)
        painter.setPen(QColor(p['text_dim']))
        f = painter.font()
        f.setPointSize(8)
        painter.setFont(f)
        fname = index.data(Qt.ItemDataRole.DisplayRole) or ""
        elided = painter.fontMetrics().elidedText(fname, Qt.TextElideMode.ElideMiddle, nr.width())
        painter.drawText(nr, Qt.AlignmentFlag.AlignCenter, elided)
        painter.restore()

    def _on_ready(self, view, row: int):
        try:
            if view and view.model():
                view.update(view.model().index(row, 0))
        except RuntimeError:
            pass


# ═══════════════════════════════════════════════════════════
#  Lightbox — cinematic overlay
# ═══════════════════════════════════════════════════════════

class LightboxOverlay(QWidget):
    closed = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.hide()
        self._paths: list[str] = []
        self._idx = 0
        self._pm: QPixmap | None = None

    def show_image(self, path: str, paths: list[str], index: int):
        self._paths, self._idx = paths, index
        self._load()
        self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()
        self.setFocus()

    def _load(self):
        self._pm = QPixmap(self._paths[self._idx]) if 0 <= self._idx < len(self._paths) else None
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Deep backdrop
        p.fillRect(self.rect(), QColor(0, 0, 0, 230))
        pal = _p()
        if self._pm and not self._pm.isNull():
            pad = 60
            avail = self.rect().adjusted(pad, pad, -pad, -pad - 30)
            sc = self._pm.scaled(avail.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            x = avail.x() + (avail.width() - sc.width()) // 2
            y = avail.y() + (avail.height() - sc.height()) // 2
            p.drawPixmap(x, y, sc)

        # Bottom info — sparse, elegant
        if self._paths:
            fname = os.path.basename(self._paths[self._idx])
            info = f"{fname}     {self._idx + 1} / {len(self._paths)}"
            p.setPen(QColor(pal['text_dim']))
            f = p.font()
            f.setPointSize(9)
            f.setLetterSpacing(f.SpacingType.AbsoluteSpacing, 1)
            p.setFont(f)
            p.drawText(self.rect().adjusted(60, 0, -60, -20),
                       Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter, info)

        # Nav — minimal chevrons
        p.setPen(QPen(QColor(255, 255, 255, 30), 1.5))
        h = self.height() // 2
        if self._idx > 0:
            p.drawLine(28, h - 10, 22, h)
            p.drawLine(22, h, 28, h + 10)
        if self._idx < len(self._paths) - 1:
            w = self.width()
            p.drawLine(w - 28, h - 10, w - 22, h)
            p.drawLine(w - 22, h, w - 28, h + 10)
        p.end()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
            self._close()
        elif e.key() in (Qt.Key.Key_Left, Qt.Key.Key_A):
            self._nav(-1)
        elif e.key() in (Qt.Key.Key_Right, Qt.Key.Key_D):
            self._nav(1)

    def mousePressEvent(self, e):
        x = e.pos().x()
        if x < self.width() * 0.15:
            self._nav(-1)
        elif x > self.width() * 0.85:
            self._nav(1)
        else:
            self._close()

    def _nav(self, d):
        n = self._idx + d
        if 0 <= n < len(self._paths):
            self._idx = n
            self._load()

    def _close(self):
        self.hide()
        self.closed.emit()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.update()


# ═══════════════════════════════════════════════════════════
#  Detail Panel — floating, airy, glass-like
# ═══════════════════════════════════════════════════════════

class DetailPanel(QWidget):
    send_to_input = pyqtSignal(str)
    use_as_example = pyqtSignal(str)

    def __init__(self, translator: Translator, parent=None):
        super().__init__(parent)
        self.setObjectName("ImDetail")
        self._t = translator
        self._reader = MetadataReader()
        self.setMinimumWidth(320)
        self.resize(360, 520)
        self._pinned = False

        # Window flags: Tool type for interactive content, no focus steal
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Hide timer — hover=50ms quick, pinned=1000ms slow fade
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(50)
        self._hide_timer.timeout.connect(self._do_hide)

        # Fade animations
        from PyQt6.QtCore import QPropertyAnimation, QEasingCurve
        self._fade_in = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_in.setDuration(150)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._fade_out = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_out.setDuration(120)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade_out.finished.connect(lambda: QWidget.hide(self))

        # ── Layout: breathing, hierarchical, restrained ──
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 12, 20, 14)
        root.setSpacing(0)

        # Top bar: drag hint + pin
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        drag_hint = QLabel("⠿", self)
        drag_hint.setStyleSheet(f"color: {_p()['text_dim']}; font-size: {_fs('fs_10')}; background: transparent; border: none;")
        drag_hint.setCursor(Qt.CursorShape.OpenHandCursor)
        top_row.addWidget(drag_hint)
        top_row.addStretch()
        self._float_pin_btn = QPushButton("📌", self)
        self._float_pin_btn.setFixedSize(20, 20)
        self._float_pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._float_pin_btn.setStyleSheet(f"background: transparent; border: none; color: {_p()['text_dim']}; font-size: {_fs('fs_11')};")
        self._float_pin_btn.clicked.connect(self._toggle_float_pin)
        top_row.addWidget(self._float_pin_btn)
        root.addLayout(top_row)
        root.addSpacing(4)

        # Preview — generous space
        self._preview = QLabel(self)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumHeight(160)
        self._preview.setStyleSheet("background: transparent; padding: 4px;")
        root.addWidget(self._preview)

        root.addSpacing(12)

        # File info — subtle, small, letter-spaced
        p = _p()
        self._info = QLabel(self)
        self._info.setWordWrap(True)
        self._info.setStyleSheet(
            f"color: {p['text_dim']}; font-size: {_fs('fs_10')}; "
            f"letter-spacing: 0.5px; line-height: 16px; "
            f"background: transparent; border: none; padding: 0;"
        )
        root.addWidget(self._info)

        # Thin separator
        root.addSpacing(10)
        sep1 = QWidget(self)
        sep1.setFixedHeight(1)
        sep1.setStyleSheet(f"background: {p['line']}; margin: 0 4px;")
        root.addWidget(sep1)
        root.addSpacing(8)

        # Prompt preview — just first line, muted
        self._prompt_preview = QLabel(self)
        self._prompt_preview.setWordWrap(True)
        self._prompt_preview.setMaximumHeight(48)
        self._prompt_preview.setStyleSheet(
            f"color: {p['text_muted']}; font-size: {_fs('fs_11')}; "
            f"background: transparent; border: none; padding: 0;"
        )
        root.addWidget(self._prompt_preview)

        root.addSpacing(6)

        # Scrollable sections — more detail
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")
        self._sw = QWidget()
        self._sl = QVBoxLayout(self._sw)
        self._sl.setContentsMargins(0, 0, 0, 0)
        self._sl.setSpacing(8)
        scroll.setWidget(self._sw)
        root.addWidget(scroll, 1)

        # Separator before actions
        root.addSpacing(8)
        sep2 = QWidget(self)
        sep2.setFixedHeight(1)
        sep2.setStyleSheet(f"background: {p['line']}; margin: 0 4px;")
        root.addWidget(sep2)
        root.addSpacing(10)

        # Actions — spaced, light, restrained
        row = QHBoxLayout()
        row.setSpacing(6)
        btn_style = (
            f"background: transparent; border: 1px solid {p['line']}; "
            f"border-radius: 4px; color: {p['text_muted']}; font-size: {_fs('fs_10')}; "
            f"padding: 4px 8px; letter-spacing: 0.5px;"
        )
        btn_hover = f"color: {p['text']}; border-color: {p['line_strong']};"
        for key, slot in [("copy", self._copy), ("im_copy_lora", self._copy_lora),
                          ("metadata_send_to_input", self._send), ("metadata_use_as_example", self._example)]:
            btn = QPushButton(translator.t(key), self)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(btn_style)
            btn.clicked.connect(slot)
            row.addWidget(btn)
        root.addLayout(row)

        self._path = ""
        self._meta: ImageMetadata | None = None
        self.clear()

    def paintEvent(self, _event):
        """Draw translucent rounded background — glass-like."""
        from PyQt6.QtGui import QPainterPath
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = _p()
        path = QPainterPath()
        path.addRoundedRect(self.rect().toRectF().adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
        # Semi-transparent background
        bg = QColor(pal['bg_surface'])
        bg.setAlpha(240)
        p.fillPath(path, bg)
        # Subtle border
        p.setPen(QPen(QColor(pal['line_strong']), 0.5))
        p.drawPath(path)
        p.end()

    def enterEvent(self, event):
        self._hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hide_timer.setInterval(1000 if self._pinned else 50)
        self._hide_timer.start()
        super().leaveEvent(event)

    def show_at(self, pos: QPoint):
        """Show with fade-in at position, clamped to screen."""
        self._fade_out.stop()
        clamped = _clamp_to_screen(pos, self.size())
        self.move(clamped)
        self.setWindowOpacity(0.0)
        QWidget.show(self)
        self.raise_()
        self._fade_in.start()

    # ── Drag support ──

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_start = e.globalPosition().toPoint()
            self._drag_origin = self.pos()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent):
        if hasattr(self, '_drag_start') and self._drag_start is not None and e.buttons() & Qt.MouseButton.LeftButton:
            delta = e.globalPosition().toPoint() - self._drag_start
            self.move(self._drag_origin + delta)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent):
        self._drag_start = None
        super().mouseReleaseEvent(e)

    def schedule_hide(self):
        if not self._pinned:
            self._hide_timer.start()

    def cancel_hide(self):
        self._hide_timer.stop()

    def hide(self):
        if not self.isVisible():
            return
        self._fade_in.stop()
        self._fade_out.setStartValue(self.windowOpacity())
        self._fade_out.start()

    def _do_hide(self):
        self.hide()
        self._pinned = False

    @property
    def is_pinned(self) -> bool:
        return self._pinned

    def set_pinned(self, v: bool):
        self._pinned = v

    def _toggle_float_pin(self):
        """Toggle window-stays-on-top for this floating panel."""
        on_top = bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        # Temporarily store pos before flag change
        pos = self.pos()
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, not on_top)
        if visible:
            self.move(pos)
            QWidget.show(self)
        p = _p()
        self._float_pin_btn.setStyleSheet(
            f"background: {p['accent']}; border: none; border-radius: 3px; color: {p['accent_text']}; font-size: {_fs('fs_11')};"
            if not on_top else
            f"background: transparent; border: none; color: {p['text_dim']}; font-size: {_fs('fs_11')};"
        )

    def show_image(self, path: str):
        self._path = path
        pm = QPixmap(path)
        if not pm.isNull():
            self._preview.setPixmap(pm.scaled(
                QSize(320, 200),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        try:
            st = os.stat(path)
            mb = st.st_size / (1024 * 1024)
            self._info.setText(f"{os.path.basename(path)}\n{pm.width()} × {pm.height()}   ·   {mb:.1f} MB")
        except OSError:
            self._info.setText(os.path.basename(path))
        self._meta = self._reader.read_metadata(path)
        # Prompt preview — first 80 chars
        if self._meta and self._meta.positive_prompt:
            preview = self._meta.positive_prompt[:80]
            if len(self._meta.positive_prompt) > 80:
                preview += "…"
            self._prompt_preview.setText(preview)
        else:
            self._prompt_preview.setText("")
        self._build()

    def show_metadata(self, meta: ImageMetadata, file_info: dict):
        self._meta = meta
        self._info.setText(file_info.get("text", ""))
        self._build()

    def clear(self):
        self._path, self._meta = "", None
        self._preview.clear()
        self._info.setText("")
        self._prompt_preview.setText("")
        self._clear()

    def _build(self):
        self._clear()
        m = self._meta
        if not m:
            return
        if m.positive_prompt:
            self._sl.addWidget(CollapsibleSection(self._t.t("metadata_positive"), self._te(m.positive_prompt), parent=self._sw))
        if m.negative_prompt:
            self._sl.addWidget(CollapsibleSection(self._t.t("metadata_negative"), self._te(m.negative_prompt), parent=self._sw))
        if m.parameters:
            self._sl.addWidget(CollapsibleSection(self._t.t("metadata_parameters"),
                self._te("\n".join(f"{k}: {v}" for k, v in m.parameters.items())), parent=self._sw))
        if m.loras:
            self._sl.addWidget(CollapsibleSection(f"LoRA ({len(m.loras)})",
                self._te("\n".join(f"{l.get('name','')} ({l.get('weight','')})" for l in m.loras)), parent=self._sw))
        self._sl.addStretch()

    def _clear(self):
        while self._sl.count():
            item = self._sl.takeAt(0)
            if (w := item.widget()):
                w.setParent(None)
                w.deleteLater()

    def _te(self, text: str) -> QTextEdit:
        te = QTextEdit(self._sw)
        te.setProperty("class", CLS_METADATA_TEXT)
        te.setPlainText(text)
        te.setReadOnly(True)
        te.setMaximumHeight(90)
        return te

    def _copy(self):
        if not self._meta:
            return
        parts = []
        if self._meta.positive_prompt:
            parts.append(self._meta.positive_prompt)
        if self._meta.loras:
            lora_str = " ".join(f"<lora:{l.get('name', '')}:{l.get('weight', '1')}>" for l in self._meta.loras)
            parts.append(lora_str)
        if parts:
            QApplication.clipboard().setText("\n".join(parts))

    def _copy_lora(self):
        if self._meta and self._meta.loras:
            text = " ".join(f"<lora:{l.get('name', '')}:{l.get('weight', '1')}>" for l in self._meta.loras)
            QApplication.clipboard().setText(text)

    def _send(self):
        if self._meta and self._meta.positive_prompt:
            self.send_to_input.emit(self._meta.positive_prompt)

    def _example(self):
        if self._path:
            self.use_as_example.emit(self._path)


# ═══════════════════════════════════════════════════════════
#  Main Window — frameless, custom titlebar, theme-following
# ═══════════════════════════════════════════════════════════

class ImageManagerWindow(QWidget):
    action_requested = pyqtSignal(str, list)
    send_to_input = pyqtSignal(str)
    use_as_example = pyqtSignal(str)
    folder_changed = pyqtSignal(str)  # emitted when user selects a new folder

    def __init__(self, translator: Translator, initial_folder: str = "", storage=None, parent=None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self._t = translator
        self._storage = storage
        self._cache = ThumbCache(500)
        self._ts = 160
        self._likes: set[str] = storage.load_likes() if storage else set()
        self._folder = initial_folder
        self._subfolder_mode = False
        self._cut_paths: list[str] = []  # internal clipboard for cut/paste
        self._nav_history: list[str] = []
        self._nav_future: list[str] = []
        # Resize/drag handled by nativeEvent + WM_NCHITTEST
        self.resize(1080, 740)
        self.setMinimumSize(640, 420)
        self._build()

    def _build(self):
        p = _p()
        self.setStyleSheet(_im_qss(p))

        # Surface
        self._surface = QWidget(self)
        self._surface.setObjectName("ImSurface")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.addWidget(self._surface)

        root = QVBoxLayout(self._surface)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Title bar ──
        tb = QWidget(self._surface)
        tb.setObjectName("ImTitleBar")
        tb.setFixedHeight(38)
        tbl = QHBoxLayout(tb)
        tbl.setContentsMargins(16, 0, 8, 0)
        tbl.setSpacing(8)

        title = QLabel(self._t.t("image_manager"), tb)
        title.setObjectName("ImTitleLabel")
        tbl.addWidget(title)
        tbl.addStretch()

        # Folder button
        self._folder_btn = QPushButton(self._t.t("im_select_folder"), tb)
        self._folder_btn.setObjectName("ImToolBtn")
        self._folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._folder_btn.setFixedHeight(24)
        self._folder_btn.clicked.connect(self._select_folder)
        tbl.addWidget(self._folder_btn)

        # Path breadcrumb — clickable to go up
        p = _p()
        self._path_label = QPushButton("", tb)
        self._path_label.setFlat(True)
        self._path_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._path_label.setStyleSheet(
            f"color: {p['text_dim']}; font-size: {_fs('fs_10')}; letter-spacing: 0.5px; "
            f"background: transparent; border: none; text-align: left; padding: 0 4px;"
        )
        self._path_label.clicked.connect(self._go_up)
        tbl.addWidget(self._path_label)
        tbl.addStretch()

        self._status = QLabel("", tb)
        self._status.setObjectName("ImDetailInfo")
        tbl.addWidget(self._status)

        self._pin_btn = QPushButton("📌", tb)
        self._pin_btn.setObjectName("ImTitleBtn")
        self._pin_btn.setFixedSize(30, 26)
        self._pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pin_btn.clicked.connect(lambda: self._toggle_pin())
        tbl.addWidget(self._pin_btn)

        for text, slot in [("—", self._minimize), ("✕", self.close)]:
            btn = QPushButton(text, tb)
            btn.setObjectName("ImTitleBtn")
            btn.setFixedSize(30, 26)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(slot)
            tbl.addWidget(btn)

        self._title_bar = tb
        root.addWidget(tb)

        # ── Toolbar ──
        bar = QWidget(self._surface)
        bar.setObjectName("ImToolbar")
        bar.setFixedHeight(34)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 0, 16, 0)
        bl.setSpacing(16)

        for label_key, widget in self._toolbar_widgets(bar):
            lbl = QLabel(label_key, bar)
            lbl.setObjectName("ImToolLabel")
            bl.addWidget(lbl)
            bl.addWidget(widget)

        bl.addStretch()

        # Sort
        sort_btn = QPushButton(self._t.t("im_sort"), bar)
        sort_btn.setObjectName("ImToolBtn")
        sort_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sm = QMenu(self)
        for key, label in [("mtime_desc", self._t.t("im_sort_newest")), ("mtime_asc", self._t.t("im_sort_oldest")),
                           ("name_asc", "A → Z"), ("name_desc", "Z → A"),
                           ("size_desc", self._t.t("im_sort_largest")), ("size_asc", self._t.t("im_sort_smallest"))]:
            a = sm.addAction(label)
            a.triggered.connect(lambda _, k=key: self._on_sort(k))
        sm.addSeparator()
        self._likes_filter_action = sm.addAction("♥ " + self._t.t("im_likes_only"))
        self._likes_filter_action.setCheckable(True)
        self._likes_filter_action.toggled.connect(self._toggle_likes_filter)
        sort_btn.setMenu(sm)
        bl.addWidget(sort_btn)

        # Subfolders toggle
        self._subfolder_btn = QPushButton(self._t.t("im_subfolders"), bar)
        self._subfolder_btn.setObjectName("ImToolBtn")
        self._subfolder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._subfolder_btn.setCheckable(True)
        self._subfolder_btn.toggled.connect(self._toggle_subfolders)
        bl.addWidget(self._subfolder_btn)

        # Navigation: back / forward / up
        self._back_btn = QPushButton("←", bar)
        self._back_btn.setObjectName("ImToolBtn")
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.clicked.connect(self._go_back)
        bl.addWidget(self._back_btn)

        self._fwd_btn = QPushButton("→", bar)
        self._fwd_btn.setObjectName("ImToolBtn")
        self._fwd_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fwd_btn.clicked.connect(self._go_forward)
        bl.addWidget(self._fwd_btn)

        self._up_btn = QPushButton("↑", bar)
        self._up_btn.setObjectName("ImToolBtn")
        self._up_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._up_btn.clicked.connect(self._go_up)
        bl.addWidget(self._up_btn)


        root.addWidget(bar)

        # ── Body ──
        self._model = ThumbnailModel(self)
        self._delegate = ThumbnailDelegate(self._cache, self._ts, self)
        self._delegate.set_likes(self._likes)
        self._view = QListView(self._surface)
        self._view.setObjectName("ImGrid")
        self._view.setViewMode(QListView.ViewMode.IconMode)
        self._view.setResizeMode(QListView.ResizeMode.Adjust)
        self._view.setUniformItemSizes(True)
        self._view.setLayoutMode(QListView.LayoutMode.Batched)
        self._view.setBatchSize(100)
        self._view.setGridSize(QSize(self._ts + 12, self._ts + 28))
        self._view.setModel(self._model)
        self._view.setItemDelegate(self._delegate)
        self._view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._view.setDragEnabled(True)
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._view.customContextMenuRequested.connect(self._ctx_menu)
        self._view.doubleClicked.connect(self._dbl_click)
        self._view.selectionModel().currentChanged.connect(self._sel_changed)
        self._view.clicked.connect(self._on_click)
        self._view.viewport().installEventFilter(self)
        self._view.setMouseTracking(True)
        root.addWidget(self._view, 1)

        # Floating detail popup (like a tooltip / context menu)
        self._detail = DetailPanel(self._t, None)
        self._detail.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self._detail.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._detail.send_to_input.connect(self.send_to_input.emit)
        self._detail.use_as_example.connect(self.use_as_example.emit)
        self._detail.hide()
        self._detail.set_pinned(False)
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(50)
        self._hover_timer.timeout.connect(self._show_hover_detail)
        self._hover_idx = QModelIndex()

        # Lightbox
        self._lb = LightboxOverlay(self)

        # Scroll debounce
        self._stimer = QTimer(self)
        self._stimer.setSingleShot(True)
        self._stimer.setInterval(100)
        self._stimer.timeout.connect(self._req_thumbs)
        sb = self._view.verticalScrollBar()
        if sb:
            sb.valueChanged.connect(self._on_scroll)

    def _on_scroll(self):
        # Auto-fetch more items when scrolling near bottom
        sb = self._view.verticalScrollBar()
        if sb and self._model.canFetchMore():
            if sb.value() > sb.maximum() * 0.7:
                self._model.fetchMore()
        self._stimer.start()

    def _toolbar_widgets(self, parent) -> list[tuple[str, QWidget]]:
        items = []
        spin = QSpinBox(parent)
        spin.setRange(10, 500)
        spin.setValue(50)
        spin.setFixedWidth(60)
        self._buf_spin = spin
        items.append((self._t.t("im_buffer_size"), spin))

        slider = QSlider(Qt.Orientation.Horizontal, parent)
        slider.setRange(96, 256)
        slider.setValue(self._ts)
        slider.setFixedWidth(100)
        slider.valueChanged.connect(self._on_size)
        self._slider = slider
        items.append((self._t.t("im_thumb_size"), slider))
        return items

    def apply_theme(self):
        """Re-apply theme colors. Call after main window theme switch."""
        self.setStyleSheet(_im_qss(_p()))

    def show(self):
        self.apply_theme()
        super().show()

    # ── Window drag & resize ──

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.BackButton:
            self._go_back()
            return
        if e.button() == Qt.MouseButton.ForwardButton:
            self._go_forward()
            return
        super().mousePressEvent(e)

    # ── Native frameless window handling (WM_NCHITTEST) ──

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_native_window_style()

    def _apply_native_window_style(self):
        if sys.platform != 'win32':
            return
        try:
            hwnd = int(self.winId())
        except (TypeError, ValueError):
            return
        if hwnd == 0:
            return
        user32 = ctypes.windll.user32
        style = int(user32.GetWindowLongW(hwnd, _GWL_STYLE))
        target = style | _WS_THICKFRAME | _WS_SYSMENU
        if target == style:
            return
        user32.SetWindowLongW(hwnd, _GWL_STYLE, target)
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                            _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOZORDER | _SWP_FRAMECHANGED | _SWP_NOACTIVATE)

    def nativeEvent(self, eventType, message):
        if sys.platform != 'win32':
            return False, 0
        try:
            msg = ctypes.wintypes.MSG.from_address(int(message))
        except (TypeError, ValueError, OSError):
            return False, 0
        if msg.message == _WM_NCCALCSIZE and msg.wParam:
            return True, 0
        if msg.message != _WM_NCHITTEST:
            return False, 0
        hit = self._hit_test()
        if hit is None:
            return False, 0
        return True, hit

    def _hit_test(self) -> int | None:
        local = self.mapFromGlobal(QCursor.pos())
        if not self.rect().contains(local):
            return None
        band = 8
        x, y, w, h = local.x(), local.y(), self.width(), self.height()
        left = x <= band
        right = x >= w - 1 - band
        top = y <= band
        bottom = y >= h - 1 - band
        if top and left:
            return _HTTOPLEFT
        if top and right:
            return _HTTOPRIGHT
        if bottom and left:
            return _HTBOTTOMLEFT
        if bottom and right:
            return _HTBOTTOMRIGHT
        if left:
            return _HTLEFT
        if right:
            return _HTRIGHT
        if top:
            return _HTTOP
        if bottom:
            return _HTBOTTOM
        # Title bar drag — 4px margin + 38px title bar = 42
        if y <= 42:
            # Don't drag when clicking on buttons
            child = self.childAt(local)
            if isinstance(child, QPushButton):
                return None
            return _HTCAPTION
        return None

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(QPen(QColor(80, 80, 80, 30), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()

    def _toggle_pin(self):
        pinned = bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        geo = self.geometry()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, not pinned)
        self.setGeometry(geo)
        self.show()
        p = _p()
        self._pin_btn.setStyleSheet(
            f"background: {p['accent']}; color: {p['accent_text']}; border: none; font-size: {_fs('fs_13')};"
            if not pinned else
            f"background: transparent; color: {p['text_dim']}; border: none; font-size: {_fs('fs_13')};"
        )

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.BackButton:
                self._go_back()
                return True
            if event.button() == Qt.MouseButton.ForwardButton:
                self._go_forward()
                return True
        # Hover tracking for floating detail
        if event.type() == QEvent.Type.MouseMove and obj is self._view.viewport():
            idx = self._view.indexAt(event.pos())
            if idx.isValid() and not self._model.is_dir(idx) and not self._detail.is_pinned:
                if idx != self._hover_idx:
                    self._hover_idx = idx
                    self._hover_pos = QCursor.pos()
                    self._hover_timer.start()
                self._detail.cancel_hide()
            else:
                self._hover_timer.stop()
                self._detail.schedule_hide()
                self._hover_idx = QModelIndex()
        if event.type() == QEvent.Type.Leave and obj is self._view.viewport():
            self._hover_timer.stop()
            self._detail.schedule_hide()
        return super().eventFilter(obj, event)

    def _minimize(self):
        self.showMinimized()

    # ── Actions ──

    def _select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, self._t.t("im_select_folder"), self._folder)
        if folder:
            self._open_folder(folder)

    def _open_folder(self, folder: str, *, from_history: bool = False):
        if self._folder and not from_history:
            self._nav_history.append(self._folder)
            self._nav_future.clear()
        self._folder = folder
        self._folder_btn.setText(os.path.basename(folder) or folder)
        self._folder_btn.setToolTip(folder)
        # Show relative path in status area
        self._path_label.setText(folder.replace("\\", " / "))
        self._cache.cancel_pending()
        self._scan_folder(folder)
        self._update_nav_buttons()
        self._update_status()
        self.folder_changed.emit(folder)
        QTimer.singleShot(200, self._req_thumbs)

    def _scan_folder(self, folder: str):
        """Scan folder for images and subdirectories.

        Normal mode: dirs first, then images (current level only).
        Subfolder mode: recursive scan, all images flat, no dir entries.
        """
        if self._subfolder_mode:
            images: list[str] = []
            try:
                for root, _dirs, files in os.walk(folder):
                    for f in files:
                        if Path(f).suffix.lower() in _IMAGE_EXTS:
                            images.append(os.path.join(root, f))
            except OSError:
                pass
            self._model.set_source(images, self._buf_spin.value())
        else:
            dirs: list[str] = []
            images_: list[str] = []
            try:
                for entry in sorted(os.scandir(folder), key=lambda e: e.name.lower()):
                    if entry.is_dir() and not entry.name.startswith('.'):
                        dirs.append(entry.path)
                    elif entry.is_file() and Path(entry.name).suffix.lower() in _IMAGE_EXTS:
                        images_.append(entry.path)
            except OSError:
                pass
            self._model.set_folder_contents(dirs, images_, self._buf_spin.value())

    def _go_back(self):
        if self._nav_history:
            self._nav_future.append(self._folder)
            prev = self._nav_history.pop()
            self._open_folder(prev, from_history=True)
        else:
            self._go_up()

    def _go_forward(self):
        if self._nav_future:
            self._nav_history.append(self._folder)
            nxt = self._nav_future.pop()
            self._open_folder(nxt, from_history=True)

    def _go_up(self):
        parent = os.path.dirname(self._folder)
        if parent and parent != self._folder:
            self._open_folder(parent)

    def _update_nav_buttons(self):
        pass  # back/fwd/up buttons are always visible

    def load_initial_folder(self):
        """Load the saved folder on startup if available."""
        if self._folder and os.path.isdir(self._folder):
            self._open_folder(self._folder)

    def _on_size(self, s: int):
        self._ts = s
        self._delegate.set_thumb_size(s, sizing=True)
        self._view.setGridSize(QSize(s + 12, s + 28))
        self._cache.cancel_pending()
        # Instant layout update — uses cached thumbnails with fast scale
        self._view.viewport().update()
        # Debounce: reload at new size after user stops dragging
        if not hasattr(self, '_size_timer'):
            self._size_timer = QTimer(self)
            self._size_timer.setSingleShot(True)
            self._size_timer.setInterval(300)
            self._size_timer.timeout.connect(self._apply_size_change)
        self._size_timer.start()

    def _apply_size_change(self):
        """Reload visible thumbnails at the final size."""
        self._delegate._sizing = False
        self._req_thumbs()

    def _on_sort(self, k: str):
        self._model.set_sort(k)
        self._cache.cancel_pending()
        QTimer.singleShot(200, self._req_thumbs)

    def _toggle_subfolders(self, checked: bool):
        self._subfolder_mode = checked
        if self._folder:
            self._cache.cancel_pending()
            self._scan_folder(self._folder)
            self._update_status()
            QTimer.singleShot(200, self._req_thumbs)

    def _toggle_likes_filter(self, checked: bool):
        if checked and self._folder:
            # Filter to only liked images
            liked = [p for p in self._model._all if p in self._likes]
            self._model.set_source(liked, self._buf_spin.value())
        elif self._folder:
            self._scan_folder(self._folder)
        self._update_status()
        QTimer.singleShot(200, self._req_thumbs)

    def _sel_changed(self, cur, _prev):
        pass  # Detail is handled by click and hover

    def _on_click(self, idx):
        """Click = pin the detail popup at cursor position."""
        if not idx.isValid() or self._model.is_dir(idx):
            return
        path = self._model.path_at(idx)
        if path:
            self._detail.show_image(path)
            self._detail.set_pinned(True)
            self._detail.set_pinned(True)
            self._detail.show_at(QCursor.pos() + QPoint(16, -40))

    def _show_hover_detail(self):
        """Hover = show floating detail at cursor (not pinned)."""
        if self._detail.is_pinned:
            return
        if not self._hover_idx.isValid():
            return
        path = self._model.path_at(self._hover_idx)
        if not path or self._model.is_dir(self._hover_idx):
            return
        self._detail.show_image(path)
        self._detail.set_pinned(False)
        self._detail.show_at(self._hover_pos + QPoint(16, -40))

    def _dbl_click(self, idx):
        if self._model.is_dir(idx):
            path = self._model.path_at(idx)
            if path:
                self._open_folder(path)
            return
        path = self._model.path_at(idx)
        if path:
            # Collect only image paths (skip dirs) for lightbox
            img_paths = []
            img_idx = 0
            for i in range(self._model.rowCount()):
                mi = self._model.index(i, 0)
                if not self._model.is_dir(mi):
                    p = self._model.path_at(mi)
                    if p:
                        if p == path:
                            img_idx = len(img_paths)
                        img_paths.append(p)
            self._lb.show_image(path, img_paths, img_idx)

    def _req_thumbs(self):
        vp = self._view.viewport()
        if not vp:
            return
        for y in range(0, vp.height(), self._ts // 2):
            for x in range(0, vp.width(), self._ts // 2):
                idx = self._view.indexAt(QPoint(x, y))
                if idx.isValid():
                    path = self._model.path_at(idx)
                    if path:
                        self._cache.request(path, self._ts)

    def _ctx_menu(self, pos):
        idxs = self._view.selectedIndexes()
        paths = [self._model.path_at(i) for i in idxs if self._model.path_at(i)]
        t = self._t
        menu = QMenu(self)

        # No selection — empty area menu
        if not paths:
            new_folder_act = menu.addAction(t.t("im_new_folder"))
            paste_act = menu.addAction(t.t("im_paste_here")) if self._cut_paths else None
            chosen = menu.exec(self._view.viewport().mapToGlobal(pos))
            if not chosen:
                return
            if chosen == new_folder_act:
                self._new_folder()
            elif paste_act and chosen == paste_act:
                self._paste_files()
            return

        # Has selection
        open_act = menu.addAction(t.t("im_open_lightbox")) if len(paths) == 1 else None
        menu.addSeparator()
        copy_act = menu.addAction(t.t("metadata_copy_file"))
        cut_act = menu.addAction(t.t("im_cut"))
        cprompt_act = menu.addAction(t.t("im_copy_prompt"))
        menu.addSeparator()

        # "Move to..." submenu — list current subdirectories
        move_menu = None
        file_paths = [p for p in paths if not os.path.isdir(p)]
        if file_paths and not self._subfolder_mode:
            move_menu = menu.addMenu(t.t("im_move_to"))
            dirs = self._model._dirs if hasattr(self._model, '_dirs') else []
            for d in dirs:
                a = move_menu.addAction(os.path.basename(d))
                a.setData(d)
            if dirs:
                move_menu.addSeparator()
            new_act_in_move = move_menu.addAction("+ " + t.t("im_new_folder"))
            new_act_in_move.setData(_NEW_FOLDER_SENTINEL)

        rename_act = menu.addAction(t.t("im_rename")) if len(paths) == 1 else None
        delete_act = menu.addAction(t.t("im_delete"))
        menu.addSeparator()
        send_act = menu.addAction(t.t("metadata_send_to_input"))
        ex_act = menu.addAction(t.t("metadata_use_as_example"))
        menu.addSeparator()
        like_act = menu.addAction("♥ " + t.t("im_like"))
        loc_act = menu.addAction(t.t("im_open_location"))
        menu.addSeparator()
        destroy_act = menu.addAction(t.t("im_destroy_metadata"))

        chosen = menu.exec(self._view.viewport().mapToGlobal(pos))
        if not chosen:
            return

        # Move to submenu actions
        if move_menu and chosen.parent() == move_menu:
            dest = chosen.data()
            if dest == _NEW_FOLDER_SENTINEL:
                dest = self._new_folder()
            if dest:
                self._move_files(file_paths, dest)
            return

        if chosen == open_act:
            all_p = [self._model.path_at(self._model.index(i, 0)) for i in range(self._model.rowCount())]
            self._lb.show_image(paths[0], all_p, idxs[0].row())
        elif chosen == copy_act:
            m = QMimeData()
            m.setUrls([QUrl.fromLocalFile(p_) for p_ in paths])
            QApplication.clipboard().setMimeData(m)
        elif chosen == cut_act:
            self._cut_paths = list(paths)
            self._delegate.set_cut(set(paths))
            self._view.viewport().update()
        elif chosen == cprompt_act:
            r = MetadataReader()
            texts = []
            for p_ in paths:
                meta = r.read_metadata(p_)
                if meta:
                    parts = []
                    if meta.positive_prompt:
                        parts.append(meta.positive_prompt)
                    if meta.loras:
                        parts.append(" ".join(f"<lora:{l.get('name', '')}:{l.get('weight', '1')}>" for l in meta.loras))
                    if parts:
                        texts.append("\n".join(parts))
            if texts:
                QApplication.clipboard().setText("\n\n".join(texts))
        elif chosen == send_act:
            meta = MetadataReader().read_metadata(paths[0])
            if meta and meta.positive_prompt:
                self.send_to_input.emit(meta.positive_prompt)
        elif chosen == ex_act:
            self.use_as_example.emit(paths[0])
        elif chosen == rename_act:
            self._rename_item(paths[0])
        elif chosen == delete_act:
            self._delete_items(paths)
        elif chosen == like_act:
            for p_ in paths:
                self._likes.symmetric_difference_update({p_})
            self._delegate.set_likes(self._likes)
            self._view.viewport().update()
            if self._storage:
                self._storage.save_likes(self._likes)
        elif chosen == loc_act and len(paths) == 1:
            subprocess.Popen(f'explorer /select,"{paths[0]}"')
        elif chosen == destroy_act:
            if _StyledDialog.confirm(self, t.t("im_destroy_metadata"),
                    t.t("im_destroy_confirm").replace("{count}", str(len(paths)))):
                w = MetadataWriter()
                for p_ in paths:
                    if Path(p_).suffix.lower() == ".png":
                        w.destroy(p_, p_)

    # ── File operations ──

    def _new_folder(self) -> str | None:
        """Create a new subfolder in the current directory. Returns path or None."""
        name, ok = _StyledDialog.get_text(self, self._t.t("im_new_folder"),
                                          self._t.t("im_new_folder_name"))
        if not ok or not name.strip():
            return None
        name = name.strip()
        dest = os.path.join(self._folder, name)
        try:
            os.makedirs(dest, exist_ok=True)
        except OSError:
            return None
        self._scan_folder(self._folder)
        self._update_status()
        QTimer.singleShot(200, self._req_thumbs)
        return dest

    def _rename_item(self, path: str) -> None:
        """Rename a file or folder via input dialog."""
        old_name = os.path.basename(path)
        name, ok = _StyledDialog.get_text(self, self._t.t("im_rename"),
                                          self._t.t("im_rename"), old_name)
        if not ok or not name.strip() or name.strip() == old_name:
            return
        new_path = os.path.join(os.path.dirname(path), name.strip())
        try:
            os.rename(path, new_path)
        except OSError:
            return
        # Update likes if renamed
        if path in self._likes:
            self._likes.discard(path)
            self._likes.add(new_path)
            if self._storage:
                self._storage.save_likes(self._likes)
        self._scan_folder(self._folder)
        self._update_status()
        QTimer.singleShot(200, self._req_thumbs)

    def _delete_items(self, paths: list[str]) -> None:
        """Delete items to Recycle Bin after confirmation."""
        if not _StyledDialog.confirm(self, self._t.t("im_delete"),
                self._t.t("im_delete_confirm").replace("{count}", str(len(paths)))):
            return
        _send_to_recycle_bin(paths)
        # Remove from likes
        for p in paths:
            self._likes.discard(p)
        if self._storage:
            self._storage.save_likes(self._likes)
        self._scan_folder(self._folder)
        self._update_status()
        QTimer.singleShot(200, self._req_thumbs)

    def _move_files(self, paths: list[str], dest_folder: str) -> None:
        """Move files into a destination folder."""
        for p in paths:
            try:
                shutil.move(p, os.path.join(dest_folder, os.path.basename(p)))
            except OSError:
                pass
            # Update likes
            if p in self._likes:
                self._likes.discard(p)
                self._likes.add(os.path.join(dest_folder, os.path.basename(p)))
        if self._storage:
            self._storage.save_likes(self._likes)
        self._scan_folder(self._folder)
        self._update_status()
        QTimer.singleShot(200, self._req_thumbs)

    def _paste_files(self) -> None:
        """Paste (move) cut files into the current folder."""
        if not self._cut_paths:
            return
        self._move_files(self._cut_paths, self._folder)
        self._cut_paths.clear()
        self._delegate.set_cut(set())
        self._view.viewport().update()

    def _update_status(self):
        self._status.setText(f"{self._model.loaded_count()} / {self._model.total_count()}")

    def keyPressEvent(self, e):
        mods = e.modifiers()
        key = e.key()
        if mods & Qt.KeyboardModifier.AltModifier:
            if key == Qt.Key.Key_Left:
                self._go_back()
                return
            if key == Qt.Key.Key_Right:
                self._go_forward()
                return
            if key == Qt.Key.Key_Up:
                self._go_up()
                return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            idxs = self._view.selectedIndexes()
            if idxs:
                self._dbl_click(idxs[0])
                return
        # F2 — rename
        if key == Qt.Key.Key_F2:
            idxs = self._view.selectedIndexes()
            if len(idxs) == 1:
                path = self._model.path_at(idxs[0])
                if path:
                    self._rename_item(path)
            return
        # Delete — recycle bin
        if key == Qt.Key.Key_Delete:
            idxs = self._view.selectedIndexes()
            paths = [self._model.path_at(i) for i in idxs if self._model.path_at(i)]
            if paths:
                self._delete_items(paths)
            return
        # Ctrl+X — cut
        if mods & Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_X:
            idxs = self._view.selectedIndexes()
            paths = [self._model.path_at(i) for i in idxs if self._model.path_at(i)]
            if paths:
                self._cut_paths = paths
                self._delegate.set_cut(set(paths))
                self._view.viewport().update()
            return
        # Ctrl+V — paste
        if mods & Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_V:
            if self._cut_paths:
                self._paste_files()
            return
        # Ctrl+C — copy to system clipboard
        if mods & Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_C:
            idxs = self._view.selectedIndexes()
            paths = [self._model.path_at(i) for i in idxs if self._model.path_at(i)]
            if paths:
                m = QMimeData()
                m.setUrls([QUrl.fromLocalFile(p) for p in paths])
                QApplication.clipboard().setMimeData(m)
            return
        super().keyPressEvent(e)

    def closeEvent(self, e):
        self._cache.stop()
        super().closeEvent(e)
