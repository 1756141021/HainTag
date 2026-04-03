from __future__ import annotations

import io
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from .error_reporting import format_exception_details, report_error, runtime_mode
from .font_loader import build_body_font, load_app_fonts
from .i18n import Translator
from .storage import AppStorage
from .theme import generate_qss, scale_qss
from .window import MainWindow


def _ensure_stdio() -> None:
    if sys.stderr is None:
        sys.stderr = io.StringIO()
    if sys.stdout is None:
        sys.stdout = io.StringIO()


def _report_fatal(
    storage: AppStorage,
    translator: Translator,
    action: str,
    summary_key: str,
) -> None:
    report_error(
        storage,
        kind='fatal_crash',
        summary=translator.t(summary_key),
        details=format_exception_details(*sys.exc_info()),
        context={'action': action, 'run_mode': runtime_mode()},
        translator=translator,
        popup=True,
    )


def _excepthook(storage: AppStorage, translator: Translator, exc_type, exc_value, exc_tb) -> None:
    report_error(
        storage,
        kind='fatal_crash',
        summary=translator.t('fatal_runtime_error'),
        details=format_exception_details(exc_type, exc_value, exc_tb),
        context={'action': 'runtime_unhandled', 'run_mode': runtime_mode()},
        translator=translator,
        popup=True,
    )
    app = QApplication.instance()
    if app is not None:
        app.exit(1)


def main() -> int:
    _ensure_stdio()
    resources_dir = Path(__file__).resolve().parent / 'resources'
    storage = AppStorage()
    initial_state = storage.load_state()
    translator = Translator(resources_dir)
    translator.set_language(initial_state.settings.language)
    sys.excepthook = lambda *args: _excepthook(storage, translator, *args)
    try:
        app = QApplication(sys.argv)
        load_app_fonts(resources_dir)
        storage.load_imported_fonts()
        settings = initial_state.settings
        custom_family = storage.font_family_by_id(settings.custom_font_id) if settings.custom_font_id else ''
        app.setFont(build_body_font(settings.font_profile, settings.body_font_point_size, custom_family))
        custom_palette = None
        if settings.theme == 'custom' and settings.custom_bg_image:
            from .theme import extract_palette_from_image
            custom_palette = extract_palette_from_image(settings.custom_bg_image)
        app.setStyleSheet(scale_qss(generate_qss(settings.theme, custom_palette=custom_palette, card_opacity=settings.card_opacity, brightness=settings.bg_brightness), settings.ui_scale_percent))

        window = MainWindow(storage, translator)
        window.show()
        return app.exec()
    except Exception:
        _report_fatal(storage, translator, 'startup', 'fatal_startup_error')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
