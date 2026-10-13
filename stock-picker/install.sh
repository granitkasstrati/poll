#!/usr/bin/env bash
# Install Munger Lens for the current user (no sudo needed, except optionally
# to install your distro's PyQt6 so the app uses your desktop's native style).
#
#   ./install.sh            install or upgrade
#   ./uninstall.sh          remove (keeps your watchlist; --purge removes it too)
#
# After installing:
#   munger-lens [TICKER]    native desktop app (also in your app menu)
#   munger-lens --web       browser version (Streamlit)
#
# Layout (XDG):
#   ~/.local/share/munger-lens/app     application code (replaced on upgrade)
#   ~/.local/share/munger-lens/venv    private Python environment
#   ~/.local/share/munger-lens/data    your watchlist and logs
#   ~/.local/share/munger-lens/env     settings sourced at launch, e.g. ANTHROPIC_API_KEY
#   ~/.config/munger-lens/             window layout and assumptions (Qt settings)
#   ~/.cache/munger-lens               market-data cache
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

# --- Qt: prefer the distro's PyQt6 so the app gets the native style ---------
# With the system Qt, Plasma's Breeze style, colour scheme, fonts and icons all
# apply automatically. pip's PyQt6 bundles its own Qt that can't load them.
# pyqtgraph also needs PyQt6.uic and sip; some distros split those into extra packages
# (Arch's python-pyqt6 has everything; Debian/Ubuntu need pyqt6-dev-tools for uic).
has_system_pyqt() { "$PY" -c 'import PyQt6.QtWidgets, PyQt6.uic; from PyQt6 import sip' 2>/dev/null; }
if ! has_system_pyqt && command -v pacman >/dev/null; then
  say "Your distro's PyQt6 (python-pyqt6) gives the app your desktop's native look."
  if [[ -t 0 ]]; then
    read -r -p "    Install it now with 'sudo pacman -S --needed python-pyqt6'? [Y/n] " ans
    if [[ ! "$ans" =~ ^[Nn] ]]; then
      sudo pacman -S --needed --noconfirm python-pyqt6 || warn "pacman install failed; falling back to pip's PyQt6."
    fi
  else
    warn "Non-interactive shell: skipping. Run 'sudo pacman -S python-pyqt6' and re-run ./install.sh for the native style."
  fi
fi
if has_system_pyqt; then
  QT_MODE=system
  say "Using system PyQt6 ($("$PY" -c 'from PyQt6.QtCore import QT_VERSION_STR as v; print("Qt", v)')) — native desktop style"
else
  QT_MODE=pip
  if "$PY" -c 'import PyQt6.QtWidgets' 2>/dev/null; then
    warn "Your system PyQt6 is incomplete (no PyQt6.uic). On Debian/Ubuntu: sudo apt install pyqt6-dev-tools, then re-run."
  fi
  say "Using PyQt6 from pip (colours, fonts and icons still follow your Plasma theme via kdeglobals)"
fi

# --- copy application code --------------------------------------------------
say "Installing app to $PREFIX"
mkdir -p "$PREFIX/data"
rm -rf "$PREFIX/app.new"
mkdir -p "$PREFIX/app.new"
cp -r "$SRC/app.py" "$SRC/stockpicker" "$SRC/desktop" "$SRC/.streamlit" "$SRC"/requirements*.txt "$PREFIX/app.new/"
find "$PREFIX/app.new" -name '__pycache__' -prune -exec rm -rf {} +
rm -rf "$PREFIX/app"
mv "$PREFIX/app.new" "$PREFIX/app"

# Carry over a watchlist created while running from the repo.
if [[ -f "$SRC/my_watchlist.json" && ! -f "$PREFIX/data/my_watchlist.json" ]]; then
  cp "$SRC/my_watchlist.json" "$PREFIX/data/"
  say "Imported your existing watchlist"
fi

# --- python environment -----------------------------------------------------
want_site=$([[ $QT_MODE == system ]] && echo true || echo false)
if [[ -f "$PREFIX/venv/pyvenv.cfg" ]]; then
  have_site=$(sed -n 's/^include-system-site-packages *= *//p' "$PREFIX/venv/pyvenv.cfg")
  have_py=$(sed -n 's/^executable *= *//p' "$PREFIX/venv/pyvenv.cfg")
  # (pyvenv.cfg has no 'executable' key before Python 3.11; only compare when present)
  if [[ "$have_site" != "$want_site" || ( -n "$have_py" && "$(readlink -f "$have_py")" != "$(command -v "$PY" | xargs readlink -f)" ) ]]; then
    say "Rebuilding Python environment (Qt source or Python changed)"
    rm -rf "$PREFIX/venv"
  fi
fi
if [[ ! -x "$PREFIX/venv/bin/python" ]]; then
  say "Creating Python environment"
  if [[ $QT_MODE == system ]]; then
    "$PY" -m venv --system-site-packages "$PREFIX/venv"
  else
    "$PY" -m venv "$PREFIX/venv"
  fi
fi
REQS=(-r "$PREFIX/app/requirements.txt" -r "$PREFIX/app/requirements-desktop.txt")
[[ $QT_MODE == pip ]] && REQS+=(-r "$PREFIX/app/requirements-pyqt.txt")
say "Installing dependencies"
"$PREFIX/venv/bin/python" -m pip install --quiet --upgrade pip
"$PREFIX/venv/bin/python" -m pip install --quiet --upgrade "${REQS[@]}"
# Drop the old embedded-browser wrapper if a previous version installed it.
"$PREFIX/venv/bin/python" -m pip uninstall --quiet --yes pywebview PyQt6-WebEngine PyQt6-WebEngine-Qt6 proxy_tools 2>/dev/null || true
"$PREFIX/venv/bin/python" -c 'import PyQt6.QtWidgets, pyqtgraph' \
  || die "PyQt6/pyqtgraph failed to import in the new environment. See the messages above."

# --- settings file (desktop-launched apps don't see your shell's exports) ---
if [[ ! -f "$PREFIX/env" ]]; then
  cat > "$PREFIX/env" <<'EOF'
# Munger Lens settings. Sourced by the launcher on every start.
# You can also set the key from the app: Settings > Configure Munger Lens.
# export ANTHROPIC_API_KEY="sk-ant-..."
EOF
  chmod 600 "$PREFIX/env"
fi

# --- launcher command -------------------------------------------------------
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/$APP" <<EOF
#!/usr/bin/env bash
# Munger Lens launcher. 'munger-lens' = native app, 'munger-lens --web' = browser version.
export STOCKPICKER_CACHE="\${XDG_CACHE_HOME:-\$HOME/.cache}/$APP"
export STOCKPICKER_DATA="$PREFIX/data"
[[ -f "$PREFIX/env" ]] && source "$PREFIX/env"
cd "$PREFIX/app"
if [[ "\${1:-}" == "--web" ]]; then
  exec "$PREFIX/venv/bin/python" desktop/web_launcher.py
fi
exec "$PREFIX/venv/bin/python" -m stockpicker.gui "\$@"
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
Categories=Office;Finance;Qt;
Keywords=stocks;investing;research;munger;graham;
StartupWMClass=$APP
StartupNotify=true
Actions=web;

[Desktop Action web]
Name=Open Web Version
Exec=$BIN_DIR/$APP --web
EOF
command -v update-desktop-database >/dev/null && update-desktop-database -q "$DESKTOP_DIR" || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t "$ICON_DIR" 2>/dev/null || true
command -v kbuildsycoca6 >/dev/null && kbuildsycoca6 --noincremental >/dev/null 2>&1 || true  # refresh KDE's menu cache

# --- system library check (only matters for pip's bundled Qt) ---------------
if [[ $QT_MODE == pip ]]; then
  missing=()
  for lib in libxcb-cursor.so.0 libxkbcommon-x11.so.0 libEGL.so.1; do
    ldconfig -p 2>/dev/null | grep -q "$lib" || missing+=("$lib")
  done
  if (( ${#missing[@]} )); then
    warn "Qt may need system libraries that look missing: ${missing[*]}"
    warn "  Arch/CachyOS:  sudo pacman -S xcb-util-cursor libxkbcommon-x11 libglvnd"
    warn "  Debian/Ubuntu: sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1"
    warn "  Fedora:        sudo dnf install xcb-util-cursor libxkbcommon-x11 mesa-libEGL"
  fi
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) warn "$BIN_DIR is not on your PATH; the app-menu entry works, but to run '$APP' from a terminal add it to PATH." ;;
esac

say "Done. Open 'Munger Lens' from your app menu, or run: $APP   (browser version: $APP --web)"
