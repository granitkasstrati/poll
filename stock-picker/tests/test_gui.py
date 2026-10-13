"""Offscreen smoke tests for the native desktop app (skipped when PyQt6 isn't installed)."""

import os
import time

import pytest

pytest.importorskip("PyQt6.QtWidgets")
pytest.importorskip("pyqtgraph")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from stockpicker.research import run_all  # noqa: E402

from .fixtures import make_company  # noqa: E402


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    a = QApplication.instance() or QApplication([])
    a.setOrganizationName("munger-lens-tests")
    a.setApplicationName("munger-lens-tests")
    return a


def pump(app, seconds=0.2):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def test_kde_palette_parsing(tmp_path, monkeypatch, app):
    from stockpicker.gui import theme

    (tmp_path / "kdeglobals").write_text(
        "[General]\nColorScheme=BreezeDark\n[Icons]\nTheme=breeze-dark\n"
        "[Colors:Window]\nBackgroundNormal=32,35,38\nForegroundNormal=252,252,252\n"
        "[Colors:View]\nBackgroundNormal=20,22,24\nForegroundNormal=252,252,252\n"
        "[Colors:Selection]\nBackgroundNormal=61,174,233\nForegroundNormal=252,252,252\n")
    monkeypatch.setattr(theme, "KDEGLOBALS", tmp_path / "kdeglobals")
    cfg = theme._read_kdeglobals()
    pal = theme.kde_palette(cfg)
    from PyQt6.QtGui import QPalette

    assert pal.color(QPalette.ColorRole.Window).getRgb()[:3] == (32, 35, 38)
    assert pal.color(QPalette.ColorRole.Highlight).getRgb()[:3] == (61, 174, 233)
    assert theme.is_dark(pal)


def test_status_icons_never_null(app):
    from stockpicker.gui.theme import status_icon

    for s in ("good", "warn", "bad", "info"):
        assert not status_icon(s).isNull()


def test_research_views_render(app):
    from stockpicker.gui.research_page import MungerView
    from stockpicker.gui.charts import DcfChart, PriceChart
    from stockpicker.gui.widgets import LensView

    res = run_all(make_company())
    mv = MungerView()
    mv.set(res)
    for key in ("graham", "future", "moat", "forensic", "technical", "asymmetric"):
        v = LensView()
        v.set(res.reports[key])
        assert v.findings.lay.count() == len(res.reports[key].findings)
    assert PriceChart().set(res.reports["technical"])
    assert DcfChart().set(res.reports["future"], res.data.price)
    pump(app)


def test_main_window_loads_company(app, monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKPICKER_DATA", str(tmp_path))
    from stockpicker.gui.main_window import MainWindow
    from stockpicker.gui.state import AppState

    d = make_company(ticker="TEST")
    monkeypatch.setattr(AppState, "company", lambda self, t, refresh=False: d)
    win = MainWindow("test")
    win.show()
    win.research.analyze("TEST")
    for _ in range(300):
        pump(app, 0.02)
        if win.research.res is not None and win.research.worker is None:
            break
    assert win.research.res is not None
    assert win.research.name.text() == "TEST Corp (TEST)"
    assert win.research.tabs.count() == 9
    win.close()
