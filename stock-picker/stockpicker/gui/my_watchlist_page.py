"""Your own saved tickers, with your thesis note and current scores."""

from __future__ import annotations

import pandas as pd
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget

from .. import watchlist
from . import workers
from .state import AppState
from .theme import theme_icon
from .widgets import FrameTable, dim_label, heading

COLS = [("Ticker", "Ticker", "text"), ("Name", "Name", "text"), ("Price", "Price", "money"),
        ("Munger score", "Munger", "score"), ("Munger verdict", "Verdict", "text"), ("Base MoS", "Margin of safety", "pct"),
        ("Swing score", "Swing", "score"), ("Setup", "Setup", "text"), ("Asymmetry score", "Asymmetry", "score"),
        ("Note", "Your note", "text"), ("Added", "Added", "text")]


def _summaries_job(state: AppState, items: dict, progress, cancel) -> pd.DataFrame:
    rows = []
    for tk, meta in items.items():
        if cancel.is_set():
            break
        try:
            s = state.research(tk).summary()
        except Exception:
            s = {"Ticker": tk}
        s["Note"], s["Added"] = meta.get("note", ""), meta.get("added", "")
        rows.append(s)
        progress(tk)
    return pd.DataFrame(rows)


class MyWatchlistPage(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.worker = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 8)
        lay.addWidget(heading("My watchlist", 1))
        lay.addWidget(dim_label("Your saved companies and why they're here. Double-click to open the research."))

        form = QHBoxLayout()
        self.ticker = QLineEdit()
        self.ticker.setPlaceholderText("Ticker")
        self.ticker.setMaximumWidth(140)
        self.note = QLineEdit()
        self.note.setPlaceholderText("Why is it here? (your thesis, the price you'd pay…)")
        add = QPushButton(theme_icon("list-add"), "Add")
        add.clicked.connect(self.add)
        self.note.returnPressed.connect(self.add)
        self.ticker.returnPressed.connect(self.note.setFocus)
        form.addWidget(self.ticker)
        form.addWidget(self.note, 1)
        form.addWidget(add)
        lay.addLayout(form)

        self.table = FrameTable(COLS, state.open_ticker.emit)
        lay.addWidget(self.table, 1)
        self.empty = dim_label("Empty. Add tickers here, or with the star button on any research page.")
        lay.addWidget(self.empty)

        btns = QHBoxLayout()
        self.open_btn = QPushButton(theme_icon("document-open", "go-next"), "Open research")
        self.remove_btn = QPushButton(theme_icon("list-remove", "edit-delete"), "Remove")
        self.refresh_btn = QPushButton(theme_icon("view-refresh"), "Refresh scores")
        self.open_btn.clicked.connect(lambda: self.table.selected_ticker() and state.open_ticker.emit(self.table.selected_ticker()))
        self.remove_btn.clicked.connect(self.remove)
        self.refresh_btn.clicked.connect(self.refresh)
        for b in (self.open_btn, self.remove_btn):
            btns.addWidget(b)
        btns.addStretch(1)
        btns.addWidget(self.refresh_btn)
        lay.addLayout(btns)
        self.status = dim_label("")
        lay.addWidget(self.status)
        state.watchlist_changed.connect(self.refresh)
        self._dirty = True

    def showEvent(self, e):  # noqa: N802 (Qt API) — refresh lazily when the page is first shown
        super().showEvent(e)
        if self._dirty:
            self.refresh()

    def refresh(self) -> None:
        items = watchlist.load()
        self.empty.setVisible(not items)
        self.table.setVisible(bool(items))
        # Show names/notes immediately, fill scores when the background job finishes.
        self.table.set_frame(pd.DataFrame([{"Ticker": t, "Note": m.get("note", ""), "Added": m.get("added", "")}
                                           for t, m in items.items()]))
        if not items or not self.isVisible():
            self._dirty = not self.isVisible()
            return
        self._dirty = False
        if self.worker:
            self.worker.cancel()
        self.status.setText("Updating scores…")
        w = workers.Worker(_summaries_job, self.state, items)
        w.signals.result.connect(lambda df, w=w: self.table.set_frame(df) if w is self.worker else None)
        w.signals.finished.connect(lambda w=w: self._finished(w))
        self.worker = workers.start(w)

    def _finished(self, w) -> None:
        if w is self.worker:
            self.worker = None
            self.status.setText("")

    def add(self) -> None:
        t = self.ticker.text().strip().upper()
        if not t:
            return
        watchlist.add(t, self.note.text().strip())
        self.ticker.clear()
        self.note.clear()
        self.ticker.setFocus()
        self.state.watchlist_changed.emit()

    def remove(self) -> None:
        t = self.table.selected_ticker()
        if t:
            watchlist.remove(t)
            self.state.watchlist_changed.emit()
