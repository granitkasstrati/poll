#!/usr/bin/env bash
# Remove the Munger Lens desktop app.
#   ./uninstall.sh           keep your watchlist and settings
#   ./uninstall.sh --purge   remove everything, including watchlist, settings, window layout and data cache
set -euo pipefail

APP=munger-lens
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
PREFIX="$DATA_HOME/$APP"

rm -rf "$PREFIX/app" "$PREFIX/app.new" "$PREFIX/venv"
rm -f "$HOME/.local/bin/$APP" "$DATA_HOME/applications/$APP.desktop" \
      "$DATA_HOME/icons/hicolor/scalable/apps/$APP.svg" "$DATA_HOME/icons/hicolor/256x256/apps/$APP.png"
command -v update-desktop-database >/dev/null && update-desktop-database -q "$DATA_HOME/applications" || true

if [[ "${1:-}" == "--purge" ]]; then
  rm -rf "$PREFIX" "${XDG_CACHE_HOME:-$HOME/.cache}/$APP" "${XDG_CONFIG_HOME:-$HOME/.config}/$APP"
  echo "Munger Lens removed, including your data."
else
  echo "Munger Lens removed. Your watchlist and settings remain in $PREFIX (use --purge to delete)."
fi
