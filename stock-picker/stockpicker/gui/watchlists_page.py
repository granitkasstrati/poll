"""Stocks to watch: screen a universe and rank it into three watchlists."""

from __future__ import annotations

import datetime as dt

import pandas as pd
from PyQt6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QTabWidget,
    QVBoxLayout, QWidget,
)

from .. import screener, universe, watchlist
from . import workers
from .state import AppState
from .theme import status_icon, theme_icon
from .widgets import FrameTable, dim_label, heading, text_label

LONG_COLS = [("Ticker", "Ticker", "text"), ("Name", "Name", "text"), ("Price", "Price", "money"),
             ("Munger score", "Munger", "score"), ("Quality", "Quality", "score"), ("Strength", "Strength", "score"),
             ("ROIC", "ROIC", "pct"), ("Base MoS", "Margin of safety", "pct"), ("Implied growth", "Implied growth", "pct"),
             ("Action", "Action", "text"), ("Munger verdict", "Verdict", "text")]
SWING_COLS = [("Ticker", "Ticker", "text"), ("Name", "Name", "text"), ("Price", "Price", "money"),
              ("Swing score", "Swing", "score"), ("Setup", "Setup", "text"), ("Trend", "Trend", "text"),
              ("RSI", "RSI", "num1"), ("Entry", "Entry", "money"), ("Stop", "Stop", "money"),
              ("Target", "Target", "money"), ("R/R", "R/R", "num1")]
RISKY_COLS = [("Ticker", "Ticker", "text"), ("Name", "Name", "text"), ("Price", "Price", "money"),
              ("Market cap", "Market cap", "money"), ("Asymmetry score", "Asymmetry", "score"),
              ("Upside", "Upside", "pct"), ("Downside", "Downside", "pct"), ("Payoff ratio", "Payoff", "ratio"),
              ("Volatility", "Volatility", "pct"), ("Short % float", "Short % float", "pct"), ("Strength", "Strength", "score")]

GROUPS = {"Quality compounders": universe.QUALITY, "Swing-trading liquids": universe.SWING, "Speculative": universe.SPECULATIVE}


def _screen_job(tickers, assumptions, progress, cancel):
    return screener.screen(tickers, assumptions, progress=lambda i, n, t: progress((i, n, t)), cancel=cancel)


class WatchlistsPage(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.worker = None
        self.df = pd.DataFrame()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 8)
        lay.addWidget(heading("Stocks to watch", 1))
        lay.addWidget(dim_label("Ranked by the same research lenses, run over a screening universe. "
                                "A starting point for research, not a buy list. Double-click a row to open its research."))

        opts = QHBoxLayout()
        self.groups = {}
        for name in GROUPS:
            cb = QCheckBox(name)
            cb.setChecked(state.settings.value(f"screen/{name}", True, type=bool))
            cb.toggled.connect(lambda on, n=name: (state.settings.setValue(f"screen/{n}", on), self._update_count()))
            opts.addWidget(cb)
            self.groups[name] = cb
        self.mine = QCheckBox("My watchlist")
        self.mine.setChecked(state.settings.value("screen/mine", True, type=bool))
        self.mine.toggled.connect(lambda on: (state.settings.setValue("screen/mine", on), self._update_count()))
        opts.addWidget(self.mine)
        self.extra = QLineEdit(state.settings.value("screen/extra", "", type=str))
        self.extra.setPlaceholderText("Extra tickers, comma-separated (e.g. RACE, NVO, SAP.DE)")
        self.extra.textChanged.connect(lambda t: (state.settings.setValue("screen/extra", t), self._update_count()))
        opts.addWidget(self.extra, 1)
        lay.addLayout(opts)

        run_row = QHBoxLayout()
        self.run_btn = QPushButton(theme_icon("media-playback-start", "system-run"), "Run screen")
        self.run_btn.clicked.connect(self.run)
        self.cancel_btn = QPushButton(theme_icon("process-stop", "media-playback-stop"), "Cancel")
        self.cancel_btn.clicked.connect(self.cancel)
        self.cancel_btn.hide()
        self.progress = QProgressBar()
        self.progress.hide()
        self.last = dim_label("")
        self.failed_btn = QPushButton()
        self.failed_btn.setFlat(True)
        self.failed_btn.hide()
        self.failed_btn.clicked.connect(self._show_failed)
        self.failures: list[str] = []
        for w in (self.run_btn, self.cancel_btn, self.progress):
            run_row.addWidget(w)
        run_row.addWidget(self.last, 1)
        run_row.addWidget(self.failed_btn)
        lay.addLayout(run_row)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.long = FrameTable(LONG_COLS, state.open_ticker.emit)
        self.swing = FrameTable(SWING_COLS, state.open_ticker.emit)
        self.risky = FrameTable(RISKY_COLS, state.open_ticker.emit)
        self.empty_labels = {}
        for title, icon, table, blurb, empty in (
            ("Long-term investments", ("view-bank", "office-chart-pie"), self.long,
             "<b>Wonderful businesses</b> (quality ≥ 55, sound balance sheets), ranked by Munger score. "
             "<i>Action</i> says whether the price is reasonable now or whether to wait for Mr. Market.",
             "No company in the universe passed the quality bar."),
            ("Swing trades", ("office-chart-line",), self.swing,
             "<b>Active technical setups</b> in non-downtrending stocks with reward/risk ≥ 1.8. "
             "Levels are mechanical suggestions; set your own stop and size the position for it.",
             "No clean setups today. No trade is a position too."),
            ("High risk / high reward", ("roll", "dialog-warning"), self.risky,
             "<b>Speculative.</b> Payoff ratio ≥ 2:1 on rough bull/bear anchors. Many of these will go to zero; "
             "size every position as if it will.",
             "Nothing with a lopsided payoff right now."),
        ):
            page = QWidget()
            pl = QVBoxLayout(page)
            pl.addWidget(text_label(blurb, rich=True))
            empty_lbl = dim_label(empty)
            empty_lbl.hide()
            self.empty_labels[id(table)] = empty_lbl
            pl.addWidget(empty_lbl)
            pl.addWidget(table, 1)
            self.tabs.addTab(page, theme_icon(*icon), title)
        lay.addWidget(self.tabs, 1)

        self.no_screen = dim_label("No screen yet. Click Run screen — the first run downloads data for every "
                                   "ticker and takes a few minutes; later runs use the 12-hour cache.")
        lay.addWidget(self.no_screen)
        state.watchlist_changed.connect(self._update_count)
        self._load_saved()
        self._update_count()

    def tickers(self) -> list[str]:
        out: list[str] = []
        for name, cb in self.groups.items():
            if cb.isChecked():
                out += GROUPS[name]
        out += [t.strip().upper() for t in self.extra.text().split(",") if t.strip()]
        if self.mine.isChecked():
            out += list(watchlist.load())
        return list(dict.fromkeys(out))

    def _update_count(self) -> None:
        if self.worker is None:
            self.run_btn.setText(f"Run screen ({len(self.tickers())} tickers)")

    def _load_saved(self) -> None:
        df, saved_at = screener.load_saved()
        if saved_at:
            self.last.setText(f"Last screen: {dt.datetime.fromtimestamp(saved_at):%Y-%m-%d %H:%M} · {len(df)} companies")
        self._show(df)

    def _show(self, df: pd.DataFrame) -> None:
        self.df = df
        has = not df.empty
        self.tabs.setVisible(has)
        self.no_screen.setVisible(not has)
        for table, fn in ((self.long, screener.long_term), (self.swing, screener.swing), (self.risky, screener.risky)):
            sub = fn(df) if has else pd.DataFrame()
            table.set_frame(sub)
            self.empty_labels[id(table)].setVisible(has and sub.empty)
            table.setVisible(not sub.empty)

    def run(self) -> None:
        tickers = self.tickers()
        if not tickers:
            return
        self.run_btn.setEnabled(False)
        self.cancel_btn.show()
        self.progress.setRange(0, len(tickers))
        self.progress.setValue(0)
        self.progress.setFormat("Starting…")
        self.progress.show()
        self.failed_btn.hide()
        w = workers.Worker(_screen_job, tickers, self.state.assumptions)
        w.signals.progress.connect(self._progress)
        w.signals.result.connect(self._done)
        w.signals.error.connect(lambda msg: QMessageBox.warning(self, "Screen failed", msg))
        w.signals.finished.connect(self._finished)
        self.worker = workers.start(w)

    def cancel(self) -> None:
        if self.worker:
            self.worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.progress.setFormat("Stopping…")

    def _progress(self, p) -> None:
        i, n, t = p
        self.progress.setValue(i)
        self.progress.setFormat(f"{i}/{n} · {t}")

    def _done(self, out) -> None:
        df, failed = out
        if not df.empty:
            screener.save(df)
            self.last.setText(f"Last screen: {dt.datetime.now():%Y-%m-%d %H:%M} · {len(df)} companies")
        self._show(df if not df.empty else self.df)
        self.failures = failed
        if failed:
            self.failed_btn.setIcon(status_icon("warn"))
            self.failed_btn.setText(f"{len(failed)} tickers failed…")
            self.failed_btn.show()
        self.state.status.emit(f"Screen finished: {len(df)} companies ranked")

    def _finished(self) -> None:
        self.worker = None
        self.run_btn.setEnabled(True)
        self.cancel_btn.hide()
        self.cancel_btn.setEnabled(True)
        self.progress.hide()
        self._update_count()

    def _show_failed(self) -> None:
        box = QMessageBox(QMessageBox.Icon.Information, "Tickers that failed",
                          f"{len(self.failures)} tickers returned no usable data (delisted, renamed, or rate-limited).",
                          parent=self)
        box.setDetailedText("\n".join(self.failures))
        box.exec()

    def rerank(self) -> None:
        """Re-show the saved screen (rankings don't depend on assumptions until the next run)."""
        self._load_saved()
