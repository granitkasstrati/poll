"""Main window: sidebar navigation, page stack, menus, status bar."""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QHBoxLayout, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QStackedWidget,
    QTextBrowser, QVBoxLayout, QWidget,
)

from .. import __version__
from ..methodology import METHODOLOGY_MD
from .my_watchlist_page import MyWatchlistPage
from .research_page import ResearchPage
from .settings_dialog import SettingsDialog
from .state import AppState
from .theme import theme_icon
from .watchlists_page import WatchlistsPage
from .widgets import heading


class MethodPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 8)
        lay.addWidget(heading("How it thinks", 1))
        view = QTextBrowser()
        view.setMarkdown(METHODOLOGY_MD)
        view.setOpenExternalLinks(True)
        lay.addWidget(view, 1)


class MainWindow(QMainWindow):
    PAGES = (
        ("Research", ("view-statistics", "office-chart-line", "system-search")),
        ("Watchlists", ("view-list-details", "view-list-text")),
        ("My watchlist", ("bookmarks", "starred-symbolic", "rating")),
        ("How it thinks", ("help-contents", "help-about")),
    )

    def __init__(self, theme_note: str = ""):
        super().__init__()
        self.theme_note = theme_note
        self.state = AppState(self)
        self.resize(1440, 920)
        self.setMinimumSize(980, 640)

        self.research = ResearchPage(self.state)
        self.watchlists = WatchlistsPage(self.state)
        self.mine = MyWatchlistPage(self.state)
        self.method = MethodPage()

        self.nav = QListWidget()
        self.nav.setIconSize(QSize(22, 22))
        self.nav.setFixedWidth(200)
        self.nav.setFrameShape(QListWidget.Shape.NoFrame)
        self.nav.setSpacing(2)
        self.stack = QStackedWidget()
        for (title, icons), page in zip(self.PAGES, (self.research, self.watchlists, self.mine, self.method)):
            item = QListWidgetItem(theme_icon(*icons), title)
            item.setSizeHint(QSize(180, 36))
            self.nav.addItem(item)
            self.stack.addWidget(page)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.currentRowChanged.connect(self._page_changed)

        central = QWidget()
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self.nav)
        row.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self._build_menus()
        self.statusBar().showMessage("Ready")
        self.state.status.connect(lambda msg: self.statusBar().showMessage(msg, 8000))
        self.state.open_ticker.connect(self.open_ticker)
        self.state.open_settings.connect(self.configure)
        self.research.title_changed.connect(self._title)

        s = self.state.settings
        if s.value("window/geometry") is not None:
            self.restoreGeometry(s.value("window/geometry"))
        self.nav.setCurrentRow(int(s.value("window/page", 0)))
        last = s.value("research/last_ticker", "", type=str)
        if last:
            self.research.ticker.setText(last)
        self._title("")

    # --- menus & actions ---
    def _build_menus(self) -> None:
        mb = self.menuBar()
        file_menu = mb.addMenu("&File")
        quit_act = QAction(theme_icon("application-exit"), "&Quit", self)
        quit_act.setShortcut(QKeySequence.StandardKey.Quit)
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        go = mb.addMenu("&Go")
        for i, (title, icons) in enumerate(self.PAGES):
            act = QAction(theme_icon(*icons), title, self)
            act.setShortcut(QKeySequence(f"Ctrl+{i + 1}"))
            act.triggered.connect(lambda _=False, i=i: self.nav.setCurrentRow(i))
            go.addAction(act)

        settings = mb.addMenu("&Settings")
        conf = QAction(theme_icon("configure", "preferences-system"), "&Configure Munger Lens…", self)
        conf.setShortcut(QKeySequence.StandardKey.Preferences)
        conf.triggered.connect(self.configure)
        settings.addAction(conf)

        help_menu = mb.addMenu("&Help")
        how = QAction(theme_icon("help-contents"), "How it &thinks", self)
        how.setShortcut(QKeySequence.StandardKey.HelpContents)
        how.triggered.connect(lambda: self.nav.setCurrentRow(3))
        about = QAction(theme_icon("help-about"), "&About Munger Lens", self)
        about.triggered.connect(self.about)
        help_menu.addAction(how)
        help_menu.addAction(about)

    def configure(self) -> None:
        dlg = SettingsDialog(self.state, self)
        if dlg.exec():
            self.research.refresh_key_state()
            self.statusBar().showMessage("Settings saved", 5000)

    def about(self) -> None:
        QMessageBox.about(self, "About Munger Lens",
                          f"<h3>Munger Lens {__version__}</h3>"
                          "<p>A stock research companion: Graham value, future expectations, moat &amp; management, "
                          "financial strength, swing setups and asymmetric bets, read together the way Charlie Munger would.</p>"
                          "<p><b>Not investment advice.</b> Data from Yahoo Finance; verify everything in the filings.</p>"
                          f"<p><small>Theme: {self.theme_note}</small></p>")

    # --- navigation ---
    def open_ticker(self, ticker: str) -> None:
        self.nav.setCurrentRow(0)
        self.research.analyze(ticker)

    def _page_changed(self, i: int) -> None:
        self.state.settings.setValue("window/page", i)
        if i != 0:
            self.setWindowTitle(self.PAGES[i][0])
        elif self.research.res:
            self._title(self.research.name.text())
        else:
            self.setWindowTitle("Research")

    def _title(self, text: str) -> None:
        # Qt appends the application display name ("— Munger Lens"), KDE-style.
        if self.nav.currentRow() == 0:
            self.setWindowTitle(text or "Research")

    def closeEvent(self, e):  # noqa: N802 (Qt API)
        s = self.state.settings
        s.setValue("window/geometry", self.saveGeometry())
        if self.research.res:
            s.setValue("research/last_ticker", self.research.res.data.ticker)
        super().closeEvent(e)
