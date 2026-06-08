#!/usr/bin/env bash
#
# Build the distributable macOS .app (dist/HainTag.app).
#
# The Danbooru tag dictionary (danbooru_all_2.csv, ~6 MB) is gitignored and
# lives outside the repo, so this script locates it and stages it at the repo
# root for the build (HainTag-mac.spec bundles it when present). The bundled
# copy is seeded into ~/Library/Application Support/HainTag/ on first run.
#
# Dictionary source, in priority order:
#   1. $HAINTAG_DICT_CSV         (explicit path)
#   2. ./danbooru_all_2.csv      (already at repo root)
#   3. ~/Library/Application Support/HainTag/danbooru_all_2.csv  (local copy)
#
# Usage:
#   ./build-macos.sh
#   HAINTAG_DICT_CSV=/path/to/danbooru_all_2.csv ./build-macos.sh
#
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"
CSV_NAME="danbooru_all_2.csv"
ROOT_CSV="$ROOT/$CSV_NAME"

# ── Resolve PyInstaller ──
if command -v pyinstaller >/dev/null 2>&1; then
  PYI=(pyinstaller)
elif python -c "import PyInstaller" >/dev/null 2>&1; then
  PYI=(python -m PyInstaller)
else
  echo "error: PyInstaller not found. Activate the venv first:" >&2
  echo "       source .venv/bin/activate && ./build-macos.sh" >&2
  exit 1
fi

# ── Resolve the tag-dictionary CSV ──
CSV="${HAINTAG_DICT_CSV:-}"
if [[ -z "$CSV" ]]; then
  for c in "$ROOT_CSV" "$HOME/Library/Application Support/HainTag/$CSV_NAME"; do
    if [[ -f "$c" ]]; then CSV="$c"; break; fi
  done
fi

staged_csv=0
if [[ -n "$CSV" && -f "$CSV" ]]; then
  if [[ "$CSV" -ef "$ROOT_CSV" ]]; then
    echo "[build-macos] bundling dictionary already at repo root: $ROOT_CSV"
  else
    cp "$CSV" "$ROOT_CSV"
    staged_csv=1
    echo "[build-macos] bundling dictionary: $CSV"
  fi
else
  echo "[build-macos] WARNING: $CSV_NAME not found — building WITHOUT the tag dictionary."
  echo "             autocomplete / translation will be empty until the user adds it."
  echo "             set HAINTAG_DICT_CSV=/path/to/$CSV_NAME to bundle it."
fi

cleanup() {
  # Remove the temporary repo-root copy we staged (it's gitignored either way).
  if [[ "$staged_csv" -eq 1 ]]; then rm -f "$ROOT_CSV"; fi
}
trap cleanup EXIT

# ── Build ──
echo "[build-macos] running: ${PYI[*]} HainTag-mac.spec"
"${PYI[@]}" HainTag-mac.spec --noconfirm

APP="$ROOT/dist/HainTag.app"
echo ""
echo "[build-macos] done → $APP"
echo "[build-macos] distribution note: the .app is ad-hoc signed but NOT"
echo "             notarized (no paid Apple Developer ID). After downloading it,"
echo "             recipients must clear the Gatekeeper quarantine flag:"
echo "                 xattr -dr com.apple.quarantine \"/Applications/HainTag.app\""
