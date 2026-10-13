"""Entry point for the native desktop app:  python -m stockpicker.gui"""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

ICON_FILE = Path(__file__).resolve().parents[2] / "desktop" / "munger-lens.svg"


def main() -> int:
    from PyQt6.QtCore import QThreadPool
    from PyQt6.QtGui import QGuiApplication, QIcon
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("munger-lens")          # QSettings: ~/.config/munger-lens/munger-lens.conf
    app.setOrganizationName("munger-lens")
    app.setApplicationDisplayName("Munger Lens")    # window titles read "… — Munger Lens"
    QGuiApplication.setDesktopFileName("munger-lens")  # Wayland app_id: matches the .desktop entry/taskbar icon

    from .theme import apply_desktop_theme

    theme_note = apply_desktop_theme(app)
    icon = QIcon.fromTheme("munger-lens")
    if icon.isNull() and ICON_FILE.exists():
        icon = QIcon(str(ICON_FILE))
    app.setWindowIcon(icon)

    from .main_window import MainWindow

    win = MainWindow(theme_note)
    win.show()
    tickers = [a for a in app.arguments()[1:] if not a.startswith("-")]
    if tickers:  # `munger-lens COST` opens straight to that company
        win.open_ticker(tickers[0])

    smoke = float(os.environ.get("MUNGER_LENS_SMOKE_TEST", "0"))  # self-test: quit after N seconds
    if smoke:
        from PyQt6.QtCore import QTimer

        QTimer.singleShot(int(smoke * 1000), app.quit)

    signal.signal(signal.SIGINT, signal.SIG_DFL)  # Ctrl+C in a terminal quits
    code = app.exec()
    QThreadPool.globalInstance().clear()  # drop queued jobs; running fetches finish in the background
    return code


if __name__ == "__main__":
    sys.exit(main())
