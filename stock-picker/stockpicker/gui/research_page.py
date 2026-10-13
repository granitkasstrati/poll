"""Research a company: header, KPI cards and one tab per research lens."""

from __future__ import annotations

import datetime as dt
import html

import pandas as pd
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QCompleter, QFileDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QProgressBar, QPushButton, QScrollArea, QStackedWidget, QTabWidget,
    QTextBrowser, QToolButton, QVBoxLayout, QWidget,
)

from .. import universe, watchlist
from ..research import Research
from ..research.base import fmt_money
from . import workers
from .charts import DcfChart, PriceChart, RsiChart
from .state import AppState
from .theme import STATUS_LABELS, status_icon, theme_icon
from .widgets import (
    Card, Collapsible, FindingsList, FrameTable, KpiCard, LensView, clear_layout, dim_label, heading, text_label,
)


def scrolled(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(widget)
    return area


def score_text(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.0f}/100"


# ---------------------------------------------------------------------------
# Munger synthesis tab
# ---------------------------------------------------------------------------

class MungerView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        self.philosophy = text_label("")
        self.philosophy.setContentsMargins(22, 0, 0, 6)
        lay.addWidget(Collapsible("How Munger thinks", self.philosophy))

        lay.addWidget(heading("The four filters", 3))
        self.filters = QGridLayout()
        self.filters.setSpacing(10)
        lay.addLayout(self.filters)

        cols = QHBoxLayout()
        cols.setSpacing(10)
        self.inversion_card, self.bias_card = Card(), Card()
        self.inversion_card.body.addWidget(heading("Invert, always invert", 3))
        self.inversion_card.body.addWidget(dim_label("How could this investment fail?"))
        self.inversion = QVBoxLayout()
        self.inversion_card.body.addLayout(self.inversion)
        self.inversion_card.body.addStretch(1)
        self.bias_card.body.addWidget(heading("Check your own psychology", 3))
        self.bias = QVBoxLayout()
        self.bias_card.body.addLayout(self.bias)
        self.bias_card.body.addStretch(1)
        cols.addWidget(self.inversion_card, 1)
        cols.addWidget(self.bias_card, 1)
        lay.addLayout(cols)

        self.lolla_title = heading("Forces in your favour", 3)
        self.lolla = text_label("", rich=True)
        lay.addWidget(self.lolla_title)
        lay.addWidget(self.lolla)

        lay.addWidget(heading("Lens scorecard", 3))
        self.scorecard = FrameTable([("Lens", "Lens", "text"), ("Score", "Score", "score"), ("Verdict", "Verdict", "text")])
        self.scorecard.setFixedHeight(230)
        lay.addWidget(self.scorecard)
        self.caveats = QVBoxLayout()
        lay.addLayout(self.caveats)
        lay.addStretch(1)

    def set(self, res: Research) -> None:
        mv = res.munger
        self.philosophy.setText(mv.report.philosophy)
        clear_layout(self.filters)
        for i, f in enumerate(mv.filters):
            card = Card()
            card.body.setAlignment(Qt.AlignmentFlag.AlignTop)
            row = QHBoxLayout()
            icon = QLabel()
            icon.setPixmap(status_icon(f.status, 20).pixmap(20, 20))
            icon.setToolTip(STATUS_LABELS[f.status])
            row.addWidget(icon)
            row.addWidget(heading(f.name, 3), 1)
            card.body.addLayout(row)
            q = dim_label(f.question)
            fnt = q.font()
            fnt.setItalic(True)
            q.setFont(fnt)
            card.body.addWidget(q)
            for e in f.evidence:
                card.body.addWidget(text_label(f"•  {e}"))
            card.body.addStretch(1)
            self.filters.addWidget(card, i // 2, i % 2)
        for layout, items in ((self.inversion, mv.inversion), (self.bias, mv.bias_checks)):
            clear_layout(layout)
            for x in items:
                layout.addWidget(text_label(f"•  {x}"))
        has_lolla = bool(mv.lollapalooza)
        self.lolla_title.setVisible(has_lolla)
        self.lolla.setVisible(has_lolla)
        if has_lolla:
            chips = " · ".join(f"<b>{html.escape(x)}</b>" for x in mv.lollapalooza)
            note = "<br><i>Lollapalooza — several factors pushing the same way.</i>" if len(mv.lollapalooza) >= 3 else ""
            self.lolla.setText(chips + note)
        self.scorecard.set_frame(pd.DataFrame(
            [{"Lens": r.title, "Score": r.score, "Verdict": r.verdict} for r in res.reports.values()]))
        clear_layout(self.caveats)
        for c in mv.report.caveats:
            self.caveats.addWidget(dim_label(c))


# ---------------------------------------------------------------------------
# Claude memo tab
# ---------------------------------------------------------------------------

def _memo_job(res: Research, effort: str, progress, cancel):
    import anthropic

    from ..ai_memo import stream_memo

    gen = stream_memo(res, effort=effort)
    try:
        for chunk in gen:
            if cancel.is_set():
                break
            progress(chunk)
    except anthropic.AuthenticationError:
        raise RuntimeError("No valid API credentials. Add your ANTHROPIC_API_KEY in Settings.") from None
    except anthropic.RateLimitError:
        raise RuntimeError("Rate limited by the API. Try again in a minute.") from None
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"API error {e.status_code}: {e.message}") from None
    except anthropic.APIConnectionError:
        raise RuntimeError("Couldn't reach the Anthropic API. Check your connection.") from None
    finally:
        gen.close()


class MemoView(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.res: Research | None = None
        self.memos: dict[str, str] = {}
        self.worker = None
        self.buffer = ""
        lay = QVBoxLayout(self)
        lay.addWidget(text_label(
            "Claude reads the research above, searches the web for recent news, competitive dynamics and "
            "management's record, and writes a Munger-style memo with sources. Check the sources."))
        row = QHBoxLayout()
        row.addWidget(QLabel("Depth:"))
        self.depth = QComboBox()
        self.depth.addItems(["low", "medium", "high", "xhigh"])
        self.depth.setCurrentText("high")
        self.depth.setToolTip("Higher = more searching and reasoning; slower and costlier.")
        row.addWidget(self.depth)
        self.write_btn = QPushButton(theme_icon("document-edit", "edit-entry"), "Write memo")
        self.stop_btn = QPushButton(theme_icon("media-playback-stop", "process-stop"), "Stop")
        self.save_btn = QPushButton(theme_icon("document-save-as", "document-save"), "Save as Markdown…")
        self.settings_btn = QPushButton(theme_icon("configure", "preferences-system"), "Add API key…")
        for b in (self.write_btn, self.stop_btn, self.save_btn, self.settings_btn):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.status = dim_label("")
        lay.addWidget(self.status)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        lay.addWidget(self.view, 1)
        self.render_timer = QTimer(self, interval=150, singleShot=True)
        self.render_timer.timeout.connect(self._render)
        self.write_btn.clicked.connect(self.start)
        self.stop_btn.clicked.connect(self.stop)
        self.save_btn.clicked.connect(self.save)
        self.settings_btn.clicked.connect(state.open_settings.emit)
        self._sync_buttons(False)

    def _sync_buttons(self, running: bool) -> None:
        key = self.state.has_api_key()
        self.write_btn.setEnabled(not running and key and self.res is not None)
        self.stop_btn.setVisible(running)
        self.save_btn.setEnabled(not running and bool(self.view.toPlainText().strip()))
        self.settings_btn.setVisible(not key)
        if not key and not running:
            self.status.setText("Claude memos need an Anthropic API key.")

    def refresh_key_state(self) -> None:
        self._sync_buttons(self.worker is not None)

    def set(self, res: Research) -> None:
        self.stop()
        self.res = res
        self.buffer = self.memos.get(res.data.ticker, "")
        self.view.setMarkdown(self.buffer)
        self.status.setText("")
        self._sync_buttons(False)

    def start(self) -> None:
        if self.res is None:
            return
        self.buffer = ""
        self.view.clear()
        self.status.setText("Researching and writing… (this can take a minute or two)")
        w = workers.Worker(_memo_job, self.res, self.depth.currentText())
        ticker = self.res.data.ticker
        w.signals.progress.connect(self._chunk)
        w.signals.error.connect(lambda msg: self.status.setText(msg))
        w.signals.finished.connect(lambda: self._done(ticker))
        self.worker = workers.start(w)
        self._sync_buttons(True)

    def stop(self) -> None:
        if self.worker is not None:
            self.worker.cancel()

    def _chunk(self, text: str) -> None:
        self.buffer += text
        if not self.render_timer.isActive():
            self.render_timer.start()

    def _render(self) -> None:
        bar = self.view.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 4
        self.view.setMarkdown(self.buffer)
        if at_bottom:
            bar.setValue(bar.maximum())

    def _done(self, ticker: str) -> None:
        self.worker = None
        self._render()
        if self.buffer:
            self.memos[ticker] = self.buffer
            if not self.status.text().startswith(("No valid", "Rate", "API", "Couldn't")):
                self.status.setText("Done. Verify anything that matters against the cited sources and filings.")
        self._sync_buttons(False)

    def save(self) -> None:
        if not self.res:
            return
        name = f"{self.res.data.ticker}-memo-{dt.date.today():%Y-%m-%d}.md"
        path, _ = QFileDialog.getSaveFileName(self, "Save memo", name, "Markdown (*.md)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.buffer)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def _research_job(state: AppState, ticker: str, refresh: bool, progress, cancel) -> Research:
    return state.research(ticker, refresh=refresh)


class ResearchPage(QWidget):
    title_changed = pyqtSignal(str)

    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.res: Research | None = None
        self.worker = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 8)

        # --- search bar ---
        bar = QHBoxLayout()
        self.ticker = QLineEdit()
        self.ticker.setPlaceholderText("Ticker (e.g. COST, MSFT, BRK-B, SAP.DE)")
        self.ticker.setClearButtonEnabled(True)
        self.ticker.addAction(theme_icon("edit-find", "search"), QLineEdit.ActionPosition.LeadingPosition)
        comp = QCompleter(sorted(set(universe.ALL)), self)
        comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.ticker.setCompleter(comp)
        self.ticker.returnPressed.connect(lambda: self.analyze(self.ticker.text()))
        bar.addWidget(self.ticker, 1)
        self.analyze_btn = QPushButton(theme_icon("view-statistics", "office-chart-line", "system-search"), "Analyze")
        self.analyze_btn.setDefault(True)
        self.analyze_btn.clicked.connect(lambda: self.analyze(self.ticker.text()))
        bar.addWidget(self.analyze_btn)
        self.refresh_btn = QPushButton(theme_icon("view-refresh"), "Refresh")
        self.refresh_btn.setToolTip("Re-download data, bypassing the 12-hour cache (F5)")
        self.refresh_btn.clicked.connect(lambda: self.analyze(self.ticker.text(), refresh=True))
        bar.addWidget(self.refresh_btn)
        self.star_btn = QPushButton()
        self.star_btn.setCheckable(True)
        self.star_btn.clicked.connect(self.toggle_watchlist)
        bar.addWidget(self.star_btn)
        outer.addLayout(bar)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=lambda: (self.ticker.setFocus(), self.ticker.selectAll()))
        QShortcut(QKeySequence(QKeySequence.StandardKey.Refresh), self,
                  activated=lambda: self.analyze(self.ticker.text(), refresh=True))

        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setMaximumHeight(4)
        self.busy.setTextVisible(False)
        self.busy.hide()
        outer.addWidget(self.busy)

        # --- empty state vs. content ---
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        self.empty = QLabel("Enter a ticker to generate the full set of research reports.")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        self.stack.addWidget(self.empty)

        content = QWidget()
        c = QVBoxLayout(content)
        c.setContentsMargins(0, 8, 0, 0)
        self.name = heading("", 1)
        self.subtitle = dim_label("")
        c.addWidget(self.name)
        c.addWidget(self.subtitle)
        kpis = QHBoxLayout()
        self.kpi = {k: KpiCard(k) for k in ("Price", "Market cap", "Munger score", "Quality", "Price score")}
        for card in self.kpi.values():
            kpis.addWidget(card)
        c.addLayout(kpis)
        self.verdict = heading("", 2)
        c.addWidget(self.verdict)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.munger = MungerView()
        self.lens = {k: LensView() for k in ("graham", "moat", "forensic", "asymmetric")}
        self.dcf = DcfChart()
        self.lens["future"] = LensView(extra_top=self.dcf)
        charts = QWidget()
        cl = QVBoxLayout(charts)
        cl.setContentsMargins(0, 0, 0, 0)
        self.price_chart, self.rsi_chart = PriceChart(), RsiChart()
        cl.addWidget(self.price_chart)
        cl.addWidget(self.rsi_chart)
        self.lens["technical"] = LensView(extra_top=charts)
        self.coc = self._circle_of_competence()
        moat_page = QWidget()
        ml = QVBoxLayout(moat_page)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.addWidget(self.lens["moat"])
        ml.addWidget(self.coc)
        self.memo = MemoView(state)
        self.business = QTextBrowser()
        self.business.setOpenExternalLinks(True)

        for title, icon, w in (
            ("Munger synthesis", ("compass", "games-config-options"), scrolled(self.munger)),
            ("Graham value", ("accessories-calculator", "office-chart-bar"), scrolled(self.lens["graham"])),
            ("Future && expectations", ("view-calendar-timeline", "chronometer"), scrolled(self.lens["future"])),
            ("Moat && management", ("security-high", "view-certificate"), scrolled(moat_page)),
            ("Financial strength", ("office-chart-area", "wallet-open"), scrolled(self.lens["forensic"])),
            ("Swing setup", ("office-chart-line",), scrolled(self.lens["technical"])),
            ("Asymmetric bet", ("roll", "games-difficult"), scrolled(self.lens["asymmetric"])),
            ("Claude memo", ("document-edit", "text-x-generic"), self.memo),
            ("Business", ("documentinfo", "help-about"), self.business),
        ):
            self.tabs.addTab(w, theme_icon(*icon), title)
        c.addWidget(self.tabs, 1)
        self.stack.addWidget(content)

        state.assumptions_changed.connect(self.recompute)
        state.watchlist_changed.connect(self._sync_star)
        self._sync_star()

    def _circle_of_competence(self) -> QGroupBox:
        box = QGroupBox("Circle-of-competence check (answer honestly)")
        lay = QVBoxLayout(box)
        self.coc_boxes = []
        for text in ("I can explain how this company makes money in two sentences.",
                     "I can name the moat and what would destroy it.",
                     "I know roughly what this business looks like in 10 years.",
                     "I've read the latest 10-K and the last shareholder letter."):
            cb = QCheckBox(text)
            cb.toggled.connect(self._save_coc)
            lay.addWidget(cb)
            self.coc_boxes.append(cb)
        return box

    def _save_coc(self) -> None:
        if self.res:
            self.state.settings.setValue(f"competence/{self.res.data.ticker}", [cb.isChecked() for cb in self.coc_boxes])

    def _load_coc(self, ticker: str) -> None:
        vals = self.state.settings.value(f"competence/{ticker}", [])
        vals = [v in (True, "true", 1, "1") for v in (vals if isinstance(vals, list) else [vals])]
        for i, cb in enumerate(self.coc_boxes):
            cb.blockSignals(True)
            cb.setChecked(i < len(vals) and vals[i])
            cb.blockSignals(False)

    # --- loading ---
    def analyze(self, ticker: str, refresh: bool = False) -> None:
        ticker = ticker.strip().upper()
        if not ticker:
            return
        self.ticker.setText(ticker)
        self._run(ticker, refresh)

    def recompute(self) -> None:
        if self.res is not None:
            self._run(self.res.data.ticker, False)

    def _run(self, ticker: str, refresh: bool) -> None:
        if self.worker is not None:
            self.worker.cancel()
        self.busy.show()
        self.analyze_btn.setEnabled(False)
        self.state.status.emit(f"Loading {ticker}…")
        w = workers.Worker(_research_job, self.state, ticker, refresh)
        w.signals.result.connect(lambda res, w=w: self._loaded(res) if w is self.worker else None)
        w.signals.error.connect(lambda msg, w=w: self._failed(ticker, msg) if w is self.worker else None)
        w.signals.finished.connect(lambda w=w: self._finished(w))
        self.worker = workers.start(w)

    def _finished(self, w) -> None:
        if w is self.worker:
            self.worker = None
            self.busy.hide()
            self.analyze_btn.setEnabled(True)

    def _failed(self, ticker: str, msg: str) -> None:
        self.state.status.emit(f"{ticker}: {msg}")
        QMessageBox.warning(self, "Couldn't load data", f"Loading {ticker} failed:\n\n{msg}")

    def _loaded(self, res: Research) -> None:
        d = res.data
        if not d.price:
            detail = ("\n\n" + "\n".join(d.errors[:3])) if d.errors else ""
            QMessageBox.warning(self, "No data", f"No data for {d.ticker}. Check the symbol "
                                f"(Yahoo format, e.g. BRK-B, RY.TO, SAP.DE).{detail}")
            self.state.status.emit(f"No data for {d.ticker}")
            return
        self.res = res
        mv = res.munger
        self.name.setText(f"{d.name} ({d.ticker})")
        self.subtitle.setText(f"{d.sector} · {d.industry} · data as of {dt.datetime.fromtimestamp(d.fetched_at):%Y-%m-%d %H:%M}")
        self.kpi["Price"].set(fmt_money(d.price))
        self.kpi["Market cap"].set(fmt_money(d.market_cap))
        self.kpi["Munger score"].set(score_text(mv.report.score), "Weighted: moat 35%, price 25%, strength 20%, management 20%")
        self.kpi["Quality"].set(score_text(res.reports["moat"].score), "Business quality & moat lens")
        self.kpi["Price score"].set(score_text(mv.report.metrics.get("Price score")), "Valuation: DCF margin of safety, reverse DCF, Graham")
        self.verdict.setText(mv.report.verdict)
        self.munger.set(res)
        for key, view in self.lens.items():
            view.set(res.reports[key])
        self.dcf.setVisible(self.dcf.set(res.reports["future"], d.price))
        has_chart = self.price_chart.set(res.reports["technical"])
        self.rsi_chart.set(res.reports["technical"])
        self.price_chart.setVisible(has_chart)
        self.rsi_chart.setVisible(has_chart)
        if has_chart:
            self.rsi_chart.setXLink(self.price_chart)
        self._load_coc(d.ticker)
        self.memo.set(res)
        self._set_business(res)
        self.stack.setCurrentIndex(1)
        self._sync_star()
        self.title_changed.emit(f"{d.name} ({d.ticker})")
        self.state.status.emit(f"{d.ticker} loaded")

    def _set_business(self, res: Research) -> None:
        d = res.data
        parts = [f"<h3>{html.escape(d.name)}</h3>",
                 f"<p>{html.escape(d.info.get('longBusinessSummary') or 'No description available.')}</p>"]
        if d.info.get("website"):
            parts.append(f'<p><a href="{html.escape(d.info["website"])}">Company website</a></p>')
        parts.append(f'<p><a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&amp;CIK={html.escape(d.ticker)}'
                     f'&amp;type=10-K">SEC filings (EDGAR)</a></p>')
        if d.errors:
            parts.append("<h4>Data warnings</h4><ul>" + "".join(f"<li>{html.escape(e)}</li>" for e in d.errors) + "</ul>")
        self.business.setHtml("".join(parts))

    # --- watchlist ---
    def _sync_star(self) -> None:
        t = self.res.data.ticker if self.res else None
        on = bool(t) and t in watchlist.load()
        self.star_btn.setEnabled(bool(t))
        self.star_btn.setChecked(on)
        self.star_btn.setIcon(theme_icon("starred-symbolic", "rating", "bookmarks") if on else
                              theme_icon("non-starred-symbolic", "rating-unrated", "bookmark-new"))
        self.star_btn.setText("On my watchlist" if on else "Add to watchlist")

    def toggle_watchlist(self) -> None:
        if not self.res:
            return
        t = self.res.data.ticker
        if t in watchlist.load():
            watchlist.remove(t)
        else:
            watchlist.add(t)
        self.state.watchlist_changed.emit()

    def refresh_key_state(self) -> None:
        self.memo.refresh_key_state()
