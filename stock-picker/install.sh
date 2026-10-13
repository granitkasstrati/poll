#!/usr/bin/env bash
# Install Munger Lens as a desktop app for the current user (no sudo needed).
#
#   ./install.sh            install or upgrade
#   ./uninstall.sh          remove (keeps your watchlist; --purge removes it too)
#
# Layout (XDG):
#   ~/.local/share/munger-lens/app     application code (replaced on upgrade)
#   ~/.local/share/munger-lens/venv    private Python environment
#   ~/.local/share/munger-lens/data    your watchlist, logs, window state
#   ~/.local/share/munger-lens/env     optional settings, e.g. ANTHROPIC_API_KEY
#   ~/.cache/munger-lens               market-data cache
#   ~/.local/bin/munger-lens           command-line launcher
#   ~/.local/share/applications/munger-lens.desktop   app-menu entry
set -euo pipefail

APP=munger-lens
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
PREFIX="$DATA_HOME/$APP"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor"

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# --- prerequisites ----------------------------------------------------------
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null || die "python3 not found. Install Python 3.10+ first."
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || die "Python 3.10+ required (found $("$PY" --version 2>&1))."
"$PY" -c 'import venv, ensurepip' 2>/dev/null \
  || die "Python venv support missing. On Debian/Ubuntu: sudo apt install python3-venv"

# --- copy application code --------------------------------------------------
say "Installing app to $PREFIX"
mkdir -p "$PREFIX/data"
rm -rf "$PREFIX/app.new"
mkdir -p "$PREFIX/app.new"
cp -r "$SRC/app.py" "$SRC/stockpicker" "$SRC/desktop" "$SRC/.streamlit" \
      "$SRC/requirements.txt" "$SRC/requirements-desktop.txt" "$PREFIX/app.new/"
find "$PREFIX/app.new" -name '__pycache__' -prune -exec rm -rf {} +
rm -rf "$PREFIX/app"
mv "$PREFIX/app.new" "$PREFIX/app"

# Carry over a watchlist created while running from the repo.
if [[ -f "$SRC/my_watchlist.json" && ! -f "$PREFIX/data/my_watchlist.json" ]]; then
  cp "$SRC/my_watchlist.json" "$PREFIX/data/"
  say "Imported your existing watchlist"
fi

# --- python environment -----------------------------------------------------
if [[ ! -x "$PREFIX/venv/bin/python" ]]; then
  say "Creating Python environment"
  "$PY" -m venv "$PREFIX/venv"
fi
say "Installing dependencies (first run downloads ~200 MB, mostly Qt WebEngine)"
"$PREFIX/venv/bin/python" -m pip install --quiet --upgrade pip
"$PREFIX/venv/bin/python" -m pip install --quiet --upgrade \
  -r "$PREFIX/app/requirements.txt" -r "$PREFIX/app/requirements-desktop.txt"

# --- settings file (desktop-launched apps don't see your shell's exports) ---
if [[ ! -f "$PREFIX/env" ]]; then
  cat > "$PREFIX/env" <<'EOF'
# Munger Lens settings. Sourced by the launcher on every start.
# Uncomment and set to enable Claude-written research memos:
# export ANTHROPIC_API_KEY="sk-ant-..."
EOF
  chmod 600 "$PREFIX/env"
fi

# --- launcher command -------------------------------------------------------
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/$APP" <<EOF
#!/usr/bin/env bash
export STOCKPICKER_CACHE="\${XDG_CACHE_HOME:-\$HOME/.cache}/$APP"
export STOCKPICKER_DATA="$PREFIX/data"
[[ -f "$PREFIX/env" ]] && source "$PREFIX/env"
exec "$PREFIX/venv/bin/python" "$PREFIX/app/desktop/launcher.py" "\$@"
EOF
chmod +x "$BIN_DIR/$APP"

# --- app-menu entry and icon ------------------------------------------------
mkdir -p "$DESKTOP_DIR" "$ICON_DIR/scalable/apps" "$ICON_DIR/256x256/apps"
cp "$SRC/desktop/munger-lens.svg" "$ICON_DIR/scalable/apps/$APP.svg"
cp "$SRC/desktop/munger-lens.png" "$ICON_DIR/256x256/apps/$APP.png"
cat > "$DESKTOP_DIR/$APP.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Munger Lens
GenericName=Stock Research
Comment=Research companies through Munger, Graham and other investing lenses
Exec=$BIN_DIR/$APP
Icon=$APP
Terminal=false
Categories=Office;Finance;
Keywords=stocks;investing;research;munger;graham;
StartupWMClass=$APP
StartupNotify=true
EOF
command -v update-desktop-database >/dev/null && update-desktop-database -q "$DESKTOP_DIR" || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t "$ICON_DIR" 2>/dev/null || true

# --- system library check for the Qt window ---------------------------------
missing=()
for lib in libxcb-cursor.so.0 libnss3.so libxkbcommon-x11.so.0 libEGL.so.1; do
  ldconfig -p 2>/dev/null | grep -q "$lib" || missing+=("$lib")
done
if (( ${#missing[@]} )); then
  warn "Qt may need system libraries that look missing: ${missing[*]}"
  warn "  Debian/Ubuntu: sudo apt install libxcb-cursor0 libnss3 libxkbcommon-x11-0 libegl1"
  warn "  Fedora:        sudo dnf install xcb-util-cursor nss libxkbcommon-x11 mesa-libEGL"
  warn "  Arch:          sudo pacman -S xcb-util-cursor nss libxkbcommon-x11"
  warn "Without them the app still works but opens in your browser instead of its own window."
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) warn "$BIN_DIR is not on your PATH; the app-menu entry works, but to run 'munger-lens' from a terminal add it to PATH." ;;
esac

say "Done. Launch 'Munger Lens' from your app menu, or run: $APP"
say "Optional: add your ANTHROPIC_API_KEY to $PREFIX/env for Claude memos."
