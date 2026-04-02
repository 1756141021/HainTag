from __future__ import annotations

import os
import re
import sys
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from .models import ErrorReport

if TYPE_CHECKING:
    from .i18n import Translator
    from .storage import AppStorage


_FALLBACK_STRINGS = {
    "zh-CN": {
        "report_dialog_title": "错误报告",
        "report_dialog_text": "程序发生错误",
        "report_dialog_instruction": "已生成错误报告文件，请把该文件发送给开发者。",
        "report_dialog_summary": "错误摘要：{summary}",
        "report_dialog_path": "报告文件：{path}",
        "report_open_dir": "打开报告目录",
        "report_copy_path": "复制文件路径",
        "close": "关闭",
        "fatal_startup_error": "程序在启动时发生错误",
        "fatal_runtime_error": "程序发生未处理异常"
    },
    "en": {
        "report_dialog_title": "Error Report",
        "report_dialog_text": "The application encountered an error",
        "report_dialog_instruction": "An error report has been generated. Please send this file to the developer.",
        "report_dialog_summary": "Summary: {summary}",
        "report_dialog_path": "Report file: {path}",
        "report_open_dir": "Open Report Folder",
        "report_copy_path": "Copy Report Path",
        "close": "Close",
        "fatal_startup_error": "The application failed during startup",
        "fatal_runtime_error": "The application hit an unhandled exception"
    }
}
_BLOCKED_KEY_PARTS = (
    'api_key',
    'authorization',
    'api_base_url',
    'input',
    'prompt',
    'message',
    'messages',
    'example',
    'examples',
    'content'
)


def runtime_mode() -> str:
    return 'dist' if getattr(sys, 'frozen', False) else 'source'


def format_exception_details(exc_type, exc_value, exc_tb) -> str:
    return ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))


def safe_context_from_settings(settings: Any | None, *, action: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    context: dict[str, Any] = {'action': action, 'run_mode': runtime_mode()}
    api_base_url = ''
    api_key = ''
    if settings is not None:
        api_base_url = str(getattr(settings, 'api_base_url', '') or '')
        api_key = str(getattr(settings, 'api_key', '') or '')
        for name in ('model', 'stream', 'memory_mode', 'language', 'max_tokens'):
            value = getattr(settings, name, None)
            if value not in (None, ''):
                context[name] = value
    if extra:
        context.update(extra)
    return _sanitize_context(context, api_base_url=api_base_url, api_key=api_key)


def create_error_report(
    kind: str,
    summary: str,
    *,
    details: str = '',
    context: dict[str, Any] | None = None,
    api_base_url: str = '',
    api_key: str = ''
) -> ErrorReport:
    return ErrorReport(
        kind=str(kind or 'runtime_error'),
        summary=_sanitize_text(summary, api_base_url=api_base_url, api_key=api_key, max_length=400),
        details=_sanitize_text(details, api_base_url=api_base_url, api_key=api_key, max_length=12000),
        context=_sanitize_context(context or {}, api_base_url=api_base_url, api_key=api_key)
    )


def report_error(
    storage: AppStorage,
    *,
    kind: str,
    summary: str,
    details: str = '',
    context: dict[str, Any] | None = None,
    translator: Translator | None = None,
    parent: QWidget | None = None,
    popup: bool = False,
    api_base_url: str = '',
    api_key: str = ''
) -> ErrorReport:
    report = create_error_report(
        kind,
        summary,
        details=details,
        context=context,
        api_base_url=api_base_url,
        api_key=api_key,
    )
    try:
        report = storage.write_error_report(report)
    except Exception as exc:
        _write_stderr_notice(
            'Failed to write error report\n'
            f'Summary: {report.summary}\n'
            f'Write failure: {type(exc).__name__}: {exc}\n'
            f'Details:\n{report.details}\n'
        )
        return report
    if popup:
        show_error_report_dialog(report, translator=translator, parent=parent)
    return report


def show_error_report_dialog(report: ErrorReport, *, translator=None, parent: QWidget | None = None) -> bool:
    strings = _strings(translator)
    path_text = report.report_path or '(unavailable)'
    notice = '\n'.join(
        [
            strings['report_dialog_text'],
            strings['report_dialog_instruction'],
            strings['report_dialog_summary'].format(summary=report.summary or '-'),
            strings['report_dialog_path'].format(path=path_text),
        ]
    )
    _write_stderr_notice(notice + '\n')

    app = QApplication.instance()
    temporary_app = None
    if app is None:
        try:
            temporary_app = QApplication([])
            app = temporary_app
        except Exception:
            return False

    box_parent = parent if isinstance(parent, QWidget) and parent is not None else None
    box = QMessageBox(box_parent)
    try:
        from .theme import current_palette
        p = current_palette()
        box.setStyleSheet(f"""
            QMessageBox {{ background: {p['bg']}; color: {p['text']}; }}
            QLabel {{ color: {p['text']}; background: transparent; }}
            QPushButton {{ background: {p['bg_surface']}; color: {p['text']}; border: 1px solid {p['line']}; border-radius: 4px; padding: 4px 12px; }}
            QPushButton:hover {{ border-color: {p['accent_text']}; }}
            QTextEdit {{ background: {p['bg_content']}; color: {p['text_muted']}; border: 1px solid {p['line']}; }}
        """)
    except Exception:
        pass
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle(strings['report_dialog_title'])
    box.setText(strings['report_dialog_text'])
    box.setInformativeText(
        '\n'.join(
            [
                strings['report_dialog_instruction'],
                strings['report_dialog_summary'].format(summary=report.summary or '-'),
                strings['report_dialog_path'].format(path=path_text),
            ]
        )
    )
    if report.details:
        box.setDetailedText(report.details)
    open_button = box.addButton(strings['report_open_dir'], QMessageBox.ButtonRole.ActionRole)
    copy_button = box.addButton(strings['report_copy_path'], QMessageBox.ButtonRole.ActionRole)
    close_button = box.addButton(strings['close'], QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(close_button)
    box.exec()
    clicked = box.clickedButton()
    if clicked is open_button and report.report_path:
        _open_report_directory(Path(report.report_path).parent)
    elif clicked is copy_button and report.report_path:
        QApplication.clipboard().setText(report.report_path)
    if temporary_app is not None:
        temporary_app.quit()
    return True


def _strings(translator) -> dict[str, str]:
    language = 'zh-CN'
    if translator is not None:
        language = getattr(translator, 'get_language', lambda: 'zh-CN')() or 'zh-CN'
    fallback = _FALLBACK_STRINGS.get(language, _FALLBACK_STRINGS['zh-CN'])
    values: dict[str, str] = {}
    for key, default in fallback.items():
        if translator is None:
            values[key] = default
            continue
        translated = translator.t(key)
        values[key] = translated if translated != key else default
    return values


def _sanitize_context(context: dict[str, Any], *, api_base_url: str, api_key: str) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in context.items():
        key_text = str(key)
        key_lower = key_text.lower()
        if any(part in key_lower for part in _BLOCKED_KEY_PARTS):
            continue
        if value in (None, ''):
            continue
        if isinstance(value, (bool, int, float)):
            cleaned[key_text] = value
            continue
        if isinstance(value, Path):
            cleaned[key_text] = str(value)
            continue
        if isinstance(value, (list, tuple, set, dict)):
            cleaned[key_text] = f'<{type(value).__name__} omitted>'
            continue
        cleaned[key_text] = _sanitize_text(str(value), api_base_url=api_base_url, api_key=api_key, max_length=300)
    return cleaned


def _sanitize_text(text: Any, *, api_base_url: str, api_key: str, max_length: int) -> str:
    value = str(text or '').replace('\r\n', '\n').replace('\r', '\n')
    if not value:
        return ''
    if api_key:
        value = value.replace(api_key, '[REDACTED_API_KEY]')
    if api_base_url:
        value = value.replace(api_base_url, '[REDACTED_API_BASE_URL]')
    value = re.sub(r"Authorization\s*:\s*Bearer\s+[^\s\"']+", 'Authorization: Bearer [REDACTED]', value, flags=re.IGNORECASE)
    value = re.sub(r'Bearer\s+[A-Za-z0-9._~+/=-]+', 'Bearer [REDACTED]', value, flags=re.IGNORECASE)
    if len(value) > max_length:
        value = value[:max_length].rstrip() + '\n...[truncated]'
    return value.strip()


def _open_report_directory(path: Path) -> None:
    try:
        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            return
    except Exception:
        pass
    if hasattr(os, 'startfile'):
        try:
            os.startfile(str(path))
        except OSError:
            return


def _write_stderr_notice(message: str) -> None:
    try:
        sys.stderr.write(message)
        if not message.endswith('\n'):
            sys.stderr.write('\n')
        sys.stderr.flush()
    except Exception:
        pass
