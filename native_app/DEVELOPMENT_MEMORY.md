# Native App Development Memory

## Status
- `native_app` is the only implementation source for the shipped Windows desktop app.
- Do not use `1_test/qt` as draft code, fallback code, or reference implementation.
- Do not pull behavior back from the old `app/` project.
- `text/` is the interaction and layout benchmark. The task book in `AI-Tag-Generator-Native-Task.md` overrides the HTML prototype when requirements conflict.

## Prototype Mapping
- `text/index.html`
  - Defines the structural skeleton: frameless shell, top-right controls, dock, workspace, input widget, prompt widget, right-side settings wing.
  - Native mapping: `native_app/window.py`, `native_app/widgets/dock.py`, `native_app/widgets/workspace.py`, `native_app/widgets/widget_card.py`, `native_app/widgets/input_widget.py`, `native_app/widgets/prompt_manager.py`, `native_app/widgets/settings_panel.py`.
- `text/style.css`
  - Defines the visual token direction: dark gradient shell, compact spacing, 12/10/6 radius rhythm, subtle borders, low-contrast chrome, dock thickness, prompt/example densities.
  - Native mapping: `native_app/theme.py`, `native_app/ui_tokens.py`, plus widget object names and style classes used by QSS.
- `text/script.js`
  - Defines interaction semantics: dock drag threshold, preview docking, floating dock resize, widget drag/resize, overlap resolution, prompt manager behavior, example widget persistence expectations, request flow, and layout persistence intent.
  - Native mapping: `native_app/window.py`, `native_app/widgets/dock.py`, `native_app/widgets/workspace.py`, `native_app/logic.py`, `native_app/storage.py`, `native_app/api_client.py`.
- `text/i18n.js` + `text/lang/*`
  - Defines language switching and the rule that dynamic UI created after startup must still refresh when language changes.
  - Native mapping: `native_app/i18n.py`, `native_app/resources/lang/*.json`, and each widget's `retranslate_ui()` implementation.

## Interaction Invariants
- Default startup layout:
  - Prompts widget starts docked/hidden from workspace and represented in the left dock.
  - Input widget starts visible inside the workspace.
  - Settings sidecar starts closed every launch and is not persisted as open.
- Window shell:
  - Frameless main window.
  - On Windows, the native HWND must keep `WS_THICKFRAME`, `WS_MAXIMIZEBOX`, `WS_MINIMIZEBOX`, and `WS_SYSMENU` while still omitting `WS_CAPTION`, so the app behaves like a normal resizable Windows window without restoring the stock title bar.
  - On Windows, outer edges and corners use native `WM_NCHITTEST` hit testing so the window resizes like a normal desktop app.
  - Window resize hit testing is based on the outer window rectangle first, with the open settings sidecar included in the right edge when visible.
  - Window resize hot zone is a 10 px band and it must not steal clicks from title-bar buttons, card resize bands, dock resize bands, or form controls.
  - Default first-launch target size is now 1440x860 before available-work-area clamping.
  - `TitleBar` blank area should keep normal window drag semantics; double-click toggles maximize/restore.
  - `WindowSurface`, `TitleBar`, `ContentHost`, and `Workspace` must keep stable dark backgrounds so the desktop never bleeds through empty areas.
  - Main window base size persists without counting the temporary settings sidecar width.
- Dock:
  - Supports left/right/top/bottom/floating.
  - Uses about 15 px drag threshold before changing state.
  - Shows docking preview on edge approach.
  - Supports expand/collapse, edge resize, floating resize, and double-click return to previous dock.
  - Dock edge resize hot zone is 10 px; dragging a collapsed dock edge only changes collapsed_thickness, follows the cursor, and never auto-expands the dock. The toggle button remains the only expand/collapse mode switch.
  - Floating dock resizes from all four edges and all four corners like a normal Windows floating panel; the small bottom-right hint is only a visual affordance, not the only resize entry.
  - Clicking a dock item restores the widget; dragging it out restores near the release position.
- Workspace widgets:
  - Move by the full-width top drag strip.
  - The small grip remains as a visual hint, not the only drag target.
  - Resize from all four edges and all four corners; the small bottom-right glyph is only a weak visual hint.
  - Auto-dock when released near the dock.
  - Restored widgets try to find free space and then resolve overlap.
- Settings sidecar:
  - Open path: commit the final outer window geometry once, then animate only the sidecar width.
  - Close path: animate sidecar to zero first, then commit the shrunken outer window geometry once.
  - `sidecarWidth` only reflects current sidecar display width; it must not call `setGeometry()` every animation frame.
- Short paths:
  - `Ctrl+Enter` / `Ctrl+Return`: send or stop.
  - `Ctrl+Shift+S`: summarize.
  - `Esc`: close the settings sidecar; Qt also closes menus/dialogs through normal behavior.
  - Workspace right-click menu: restore/dock prompts, add example, reset layout, toggle settings, toggle pin.
  - Input right-click menu: send/stop, summarize, clear history.
  - Dock right-click menu: expand/collapse, dock to four sides, toggle floating.
- Typography:
  - Base body/form/input text uses `Noto Sans CJK SC` / `Noto Sans SC` first.
  - `Quicksand` is reserved for decorative chrome such as title-bar buttons, dock labels, section headers, and similar lightweight UI accents.
  - Numeric status/readout areas such as slider values and token counts keep a monospace family.
- Business behavior must not shrink relative to the task book:
  - Prompt manager fields: `enabled`, `name`, `role`, `depth`, `order`, `content`.
  - Prompt rows start in a compact collapsed state, new rows auto-expand, multiple rows may stay expanded at once, and every expand/collapse or content-height change must refresh the owning `QListWidgetItem.sizeHint()` so rows stack without overlap.
  - Example entries support image, tags, description, order, depth, persistence, and paired message insertion.
  - Memory Mode changes how active input is extracted.
  - Token estimate stays visible.
  - Summary prompt must include `{{content}}`.
  - Stream, non-stream, cancel, and error feedback must work.
- Configuration import/export:
  - Prompt-specific import/export stays as a separate feature.
  - Settings config import/export provides two scopes: `settings_page` and `full_profile`.
  - Exported config bundles never include `api_base_url` or `api_key`.
  - Imported config bundles never overwrite the current machine's `api_base_url` or `api_key`.
  - Importing `settings_page` only updates settings fields.
  - Importing `full_profile` restores settings, prompts, examples, dock state, widget state, and window state.
- Error reporting:
  - Validation errors stay inline in the input status area and do not generate report files.
  - Request, import, export, and storage failures generate sanitized reports under `%APPDATA%\AITagGenerator\reports`.
  - Fatal crashes write a report, show a popup that asks the user to send the file to the developer, and then exit the app.
  - Reports must redact `api_key`, `Authorization`, full `api_base_url`, and full input/prompt/example content.

## Current Native File Responsibilities
- `native_app/__main__.py`
  - PyInstaller entrypoint and `python -m native_app` entry.
- `native_app/main.py`
  - Creates `QApplication`, loads local fonts/resources, applies QSS, constructs storage, translator, and main window.
  - Installs the fatal exception hook and routes startup/runtime crashes into the unified error report flow.
- `native_app/error_reporting.py`
  - Builds sanitized error reports, controls popup wording, and handles open-folder / copy-path actions for generated reports.
- `native_app/theme.py`
  - Global QSS aligned to the HTML prototype's visual rhythm, background chain, dock hot-zone feedback, and font-role layering.
- `native_app/ui_tokens.py`
  - Shared design constants for window, resize hot zones, dock handles, settings wing, and control sizes.
- `native_app/font_loader.py`
  - Loads bundled fonts from `native_app/resources/fonts` and builds the app-wide default body font stack.
- `native_app/i18n.py`
  - Runtime language catalog loader and key lookup.
- `native_app/logic.py`
  - API base normalization, memory-mode input extraction, example validation, `build_messages()`, token estimation.
- `native_app/api_client.py`
  - Background LLM request worker with stream/non-stream support and cancel handling.
- `native_app/models.py`
  - Dataclasses for prompts, examples, dock, window, widgets, settings, config bundles, and full app state.
- `native_app/storage.py`
  - Persists app state JSON, imports/exports prompts, copies/removes example image assets, and reads/writes versioned config bundles.
- `native_app/window.py`
  - Main shell coordinator: window geometry restore, visible-shell native resize hit testing, settings sidecar animation, dock/workspace coordination, menus, shortcuts, config bundle flows, state save/load, request lifecycle.
- `native_app/widgets/common.py`
  - Shared custom controls like toggle switch and drag handle label.
- `native_app/widgets/dock.py`
  - Dock panel behavior, floating/edge resizing, split collapsed/expanded dock-size persistence, drag threshold, hover feedback, and restore from dock items.
- `native_app/widgets/workspace.py`
  - Free-layout workspace logic, widget state capture/restore, clamping, overlap resolution, dock detection, and card removal for layout replacement.
- `native_app/widgets/widget_card.py`
  - Generic movable/resizable workspace card shell used by prompts, input, and examples, with a full-width top drag strip.
- `native_app/widgets/input_widget.py`
  - Input editor, token indicator, send/summary action bar.
- `native_app/widgets/prompt_manager.py`
  - Prompt list UI, expand/collapse item content, ordering, role/depth fields, add/remove flow.
- `native_app/widgets/example_widget.py`
  - Example editor UI, image preview/import, tags/description/order/depth editing, dynamic language refresh.
- `native_app/widgets/settings_panel.py`
  - Settings sidecar content, sampling controls, language switcher, summary prompt, prompt import/export, and config import/export menus.
- `native_app/resources/lang/en.json`
  - English UI strings.
- `native_app/resources/lang/zh-CN.json`
  - Simplified Chinese UI strings.
- `native_app/resources/fonts/`
  - Bundled font files included in the one-folder release when available.

## Persisted State Fields
- `AppSettings`
  - `api_base_url`
  - `api_key`
  - `model`
  - `temperature`
  - `top_p`
  - `top_k`
  - `freq_penalty`
  - `pres_penalty`
  - `max_tokens`
  - `stream`
  - `memory_mode`
  - `summary_prompt`
  - `language`
- `WindowState`
  - `x`, `y`, `width`, `height`
  - `maximized`
  - `pinned`
  - `available_screen_x`, `available_screen_y`, `available_screen_width`, `available_screen_height`
  - `screen_device_name`
  - Important rule: `width` and `height` mean the base main window size with the settings sidecar closed.
- `DockState`
  - `position`, `expanded`
  - `collapsed_thickness`, `expanded_vertical_size`, `expanded_horizontal_size`
  - `floating_x`, `floating_y`, `floating_width`, `floating_height`
  - `last_docked_position`
- `WidgetState`
  - `widget_id`, `visible`, `docked`
  - `x`, `y`, `width`, `height`
  - `dock_slot`
- Other persisted app data
  - `prompts[]`
  - `examples[]`
  - `input_history`
  - Example image files copied into the storage `examples/` directory.

## Config Bundle Format
- `ConfigBundle`
  - `version`
  - `scope`: `settings_page` or `full_profile`
  - `payload`
- `payload.settings`
  - Exportable settings only.
  - `api_base_url` and `api_key` are always excluded.
- `payload.prompts`
  - Present for `full_profile` exports.
- `payload.examples`
  - Present for `full_profile` exports.
  - Example images are embedded into the bundle as base64 and restored back into app storage on import.
- `payload.dock`
  - Present for `full_profile` exports.
- `payload.widgets`
  - Present for `full_profile` exports.
- `payload.window`
  - Present for `full_profile` exports.

## Window Restore Rules
- First launch targets `1440x860`, but clamps to `92%` of the current screen's available work area.
- Closing records the available work area, not raw monitor resolution.
- Reopen on the same geometry restores exact placement.
- Reopen on changed work area scales window and widget geometry proportionally, then clamps everything back into the current available area.
- If a stored monitor no longer exists or saved geometry ends up out of bounds, recenter into the current primary available area.

## Packaging And Launch
- Dev launch:
  - `python -m native_app`
- Build script:
  - `build_native.ps1`
  - The build disables PyInstaller windowed traceback so the shipped app uses the native report popup instead of the default traceback window.
- PyInstaller mode:
  - one-folder (`--onedir`) Windows GUI build.
- Output entry executable:
  - `dist\AITagGenerator\AITagGenerator.exe`
- Resource inclusion:
  - `build_native.ps1` includes `native_app/resources`, so language files and bundled fonts under that tree ship with the executable.
- Runtime storage location:
  - Prefer `%APPDATA%\AITagGenerator`.
  - Fallback to `.native_appdata\AITagGenerator` under the current working directory if `%APPDATA%` is unavailable or blocked.

## Code Standards
- These standards are the default baseline for all code projects handled in this workspace, not just `native_app`.
- Core principles:
  - Prefer simple solutions first (KISS).
  - Keep responsibilities narrow (SRP); one function or class should do one job well.
  - Favor small, focused functions over large multi-purpose blocks.
- Naming and style:
  - Names must be descriptive, searchable, and reflect real intent.
  - Avoid single-letter names except for very short-lived loop counters.
  - Keep repo style consistent: snake_case for Python variables/functions/modules, PascalCase for classes, UPPER_SNAKE_CASE for constants.
  - Use spaces for indentation, not tabs; keep formatting consistent and easy to scan.
  - Reduce nesting where possible by using early returns and clear guard clauses.
- Comments and documentation:
  - Comments should explain why a decision exists, not restate what obvious code already says.
  - Remove stale comments, dead code, and misleading notes as part of normal maintenance.
  - Keep supporting docs in sync when responsibilities or behavior change.
- Defensive programming:
  - Validate parameters and external inputs before using them.
  - Handle failures explicitly; do not silently swallow exceptions.
  - Prefer clear error paths and user-facing feedback for recoverable failures.
- Safety and performance:
  - Manage resources carefully and always close or release them correctly.
  - Avoid broad or ambiguous data access patterns when a narrower one is clearer and safer.
  - Make performance-conscious choices, but not at the cost of readability without evidence.
- Testing and collaboration:
  - Add or update focused tests for meaningful behavior changes and bug fixes when practical.
  - Consistency across the codebase is more important than personal preference in any one file.
  - Treat code review as part of quality control: optimize for readability, maintainability, and low communication cost.
## Maintenance Rules
- Any time module responsibilities move, update this file in the same change.
- Any time a new dynamic UI element is added, verify it participates in `retranslate_ui()`.
- Any time persistence schema changes, update the relevant sections here and keep backward-compatible loading in `models.py` or `storage.py`.
- Any time interaction diverges from `text/`, document why the native behavior is objectively shorter-path or lower-cognitive-load.







