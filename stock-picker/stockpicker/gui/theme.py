"""Make the app look like the user's desktop.

Best case (CachyOS/Arch with the system `python-pyqt6`): Qt is the system Qt,
Plasma's platform theme loads, and we get the real Breeze style, colour
scheme, fonts and icons for free — this module then does nothing.

Fallback (PyQt6 from pip bundles its own Qt, which can't load Plasma's
plugins): read the active colour scheme, font and icon theme straight from
~/.config/kdeglobals and apply them on top of Qt's Fusion style, so colours,
fonts and icons still match. Off KDE, follow the system light/dark preference.
"""

from __future__ import annotations

import configparser
import os
from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPixmap
from PyQt6.QtWidgets import QApplication

from ..research.base import BAD, GOOD, INFO, WARN

KDEGLOBALS = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "kdeglobals"


# ---------------------------------------------------------------------------
# Desktop integration
# ---------------------------------------------------------------------------

def _rgb(value: str | None) -> QColor | None:
    if not value:
        return None
    try:
        parts = [int(x) for x in value.split(",")[:3]]
    except ValueError:
        return None
    return QColor(*parts) if len(parts) == 3 else None


def _read_kdeglobals() -> configparser.RawConfigParser | None:
    if not KDEGLOBALS.exists():
        return None
    cfg = configparser.RawConfigParser(strict=False, interpolation=None)
    cfg.optionxform = str  # keep key case
    try:
        cfg.read(KDEGLOBALS, encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError):
        return None
    return cfg


def kde_palette(cfg: configparser.RawConfigParser) -> QPalette | None:
    """Build a QPalette from a Plasma colour scheme (the [Colors:*] groups)."""
    def c(group: str, key: str) -> QColor | None:
        return _rgb(cfg.get(f"Colors:{group}", key, fallback=None))

    window_bg, window_fg = c("Window", "BackgroundNormal"), c("Window", "ForegroundNormal")
    if window_bg is None or window_fg is None:
        return None
    view_bg = c("View", "BackgroundNormal") or window_bg
    view_fg = c("View", "ForegroundNormal") or window_fg
    inactive = c("View", "ForegroundInactive") or c("Window", "ForegroundInactive") or window_fg.darker(150)

    pal = QPalette()
    roles = {
        QPalette.ColorRole.Window: window_bg,
        QPalette.ColorRole.WindowText: window_fg,
        QPalette.ColorRole.Base: view_bg,
        QPalette.ColorRole.AlternateBase: c("View", "BackgroundAlternate") or view_bg,
        QPalette.ColorRole.Text: view_fg,
        QPalette.ColorRole.Button: c("Button", "BackgroundNormal") or window_bg,
        QPalette.ColorRole.ButtonText: c("Button", "ForegroundNormal") or window_fg,
        QPalette.ColorRole.Highlight: c("Selection", "BackgroundNormal") or QColor("#3daee9"),
        QPalette.ColorRole.HighlightedText: c("Selection", "ForegroundNormal") or QColor("#ffffff"),
        QPalette.ColorRole.ToolTipBase: c("Tooltip", "BackgroundNormal") or window_bg,
        QPalette.ColorRole.ToolTipText: c("Tooltip", "ForegroundNormal") or window_fg,
        QPalette.ColorRole.Link: c("View", "ForegroundLink") or QColor("#1d99f3"),
        QPalette.ColorRole.LinkVisited: c("View", "ForegroundVisited") or QColor("#9b59b6"),
        QPalette.ColorRole.PlaceholderText: inactive,
        QPalette.ColorRole.BrightText: c("View", "ForegroundNegative") or QColor("#da4453"),
    }
    for role, color in roles.items():
        pal.setColor(role, color)
    if hasattr(QPalette.ColorRole, "Accent"):  # Qt 6.6+
        pal.setColor(QPalette.ColorRole.Accent, roles[QPalette.ColorRole.Highlight])
    # Shading roles Fusion uses for bevels/frames
    pal.setColor(QPalette.ColorRole.Light, window_bg.lighter(130))
    pal.setColor(QPalette.ColorRole.Midlight, window_bg.lighter(115))
    pal.setColor(QPalette.ColorRole.Mid, window_bg.darker(130))
    pal.setColor(QPalette.ColorRole.Dark, window_bg.darker(160))
    pal.setColor(QPalette.ColorRole.Shadow, QColor(0, 0, 0))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, inactive)
    return pal


def kde_font(cfg: configparser.RawConfigParser) -> QFont | None:
    spec = cfg.get("General", "font", fallback=None)  # e.g. "Noto Sans,10,-1,5,400,0,0,0,0,0,0,0,0,0,0,1"
    if not spec:
        return None
    f = QFont()
    return f if f.fromString(spec) else None


def _dark_palette() -> QPalette:
    """Breeze Dark-like palette for non-KDE dark desktops."""
    pal = QPalette()
    for role, hexv in {
        QPalette.ColorRole.Window: "#202326", QPalette.ColorRole.WindowText: "#fcfcfc",
        QPalette.ColorRole.Base: "#141618", QPalette.ColorRole.AlternateBase: "#1d1f22",
        QPalette.ColorRole.Text: "#fcfcfc", QPalette.ColorRole.Button: "#292c30",
        QPalette.ColorRole.ButtonText: "#fcfcfc", QPalette.ColorRole.Highlight: "#3daee9",
        QPalette.ColorRole.HighlightedText: "#fcfcfc", QPalette.ColorRole.ToolTipBase: "#292c30",
        QPalette.ColorRole.ToolTipText: "#fcfcfc", QPalette.ColorRole.Link: "#1d99f3",
        QPalette.ColorRole.PlaceholderText: "#a1a9b1",
    }.items():
        pal.setColor(role, QColor(hexv))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor("#6e7175"))
    return pal


def apply_desktop_theme(app: QApplication) -> str:
    """Match the desktop; returns a short description of what was applied (for logs/About)."""
    style = app.style().name().lower()
    if style == "breeze":
        return "native Breeze (system Qt)"

    cfg = _read_kdeglobals()
    if cfg is not None:
        app.setStyle("Fusion")
        pal = kde_palette(cfg)
        if pal is not None:
            app.setPalette(pal)
        font = kde_font(cfg)
        if font is not None:
            app.setFont(font)
        icons = cfg.get("Icons", "Theme", fallback=None)
        if icons:
            QIcon.setThemeName(icons)
        scheme = cfg.get("General", "ColorScheme", fallback="Plasma colours")
        return f"Fusion + {scheme} (from kdeglobals)"

    hints = app.styleHints()
    dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark
    app.setStyle("Fusion")
    if dark and app.palette().color(QPalette.ColorRole.Window).lightness() > 128:
        app.setPalette(_dark_palette())
    return f"Fusion ({'dark' if dark else 'light'})"


def is_dark(palette: QPalette | None = None) -> bool:
    pal = palette or QApplication.palette()
    return pal.color(QPalette.ColorRole.Window).lightness() < 128


# ---------------------------------------------------------------------------
# Status icons: theme icon when available (Breeze has data-*), else a drawn badge.
# Status is never colour alone — every badge also carries a glyph and a tooltip.
# ---------------------------------------------------------------------------

STATUS_COLORS = {GOOD: "#0ca30c", WARN: "#fab219", BAD: "#d03b3b", INFO: "#3987e5"}
STATUS_LABELS = {GOOD: "Good", WARN: "Caution", BAD: "Red flag", INFO: "Info"}
_THEME_NAMES = {
    GOOD: ("data-success", "emblem-success", "dialog-ok-apply"),
    WARN: ("data-warning", "dialog-warning"),
    BAD: ("data-error", "dialog-error"),
    INFO: ("data-information", "dialog-information"),
}
_GLYPHS = {GOOD: "✓", WARN: "!", BAD: "×", INFO: "i"}
_icon_cache: dict[tuple[str, int], QIcon] = {}


def status_icon(status: str, size: int = 18) -> QIcon:
    key = (status, size)
    if key in _icon_cache:
        return _icon_cache[key]
    for name in _THEME_NAMES.get(status, ()):
        icon = QIcon.fromTheme(name)
        if not icon.isNull():
            _icon_cache[key] = icon
            return icon
    pm = QPixmap(QSize(size, size) * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(STATUS_COLORS.get(status, "#888888")))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.setPen(QColor("#1a1a19" if status == WARN else "#ffffff"))
    f = QFont()
    f.setBold(True)
    f.setPixelSize(int(size * 0.68))
    p.setFont(f)
    p.drawText(0, 0, size, size, Qt.AlignmentFlag.AlignCenter, _GLYPHS.get(status, "•"))
    p.end()
    icon = QIcon(pm)
    _icon_cache[key] = icon
    return icon


def theme_icon(*names: str) -> QIcon:
    for n in names:
        icon = QIcon.fromTheme(n)
        if not icon.isNull():
            return icon
    return QIcon()


# ---------------------------------------------------------------------------
# Chart colours (validated categorical slots 1-3, stepped per light/dark)
# ---------------------------------------------------------------------------

def chart_colors(palette: QPalette | None = None) -> dict:
    pal = palette or QApplication.palette()
    dark = is_dark(pal)
    base = pal.color(QPalette.ColorRole.Base)
    text = pal.color(QPalette.ColorRole.Text)
    grid = QColor(text)
    grid.setAlphaF(0.12)
    axis = QColor(text)
    axis.setAlphaF(0.55)
    return {
        "series": ["#3987e5", "#d95926", "#199e70"] if dark else ["#2a78d6", "#eb6834", "#1baf7a"],
        "good": "#0ca30c",
        "critical": "#d03b3b",
        "background": base.name(),
        "text": text.name(),
        # QColor objects, not hex: pyqtgraph reads 8-digit hex as RRGGBBAA, Qt writes AARRGGBB.
        "axis": axis,
        "grid": grid,
    }
