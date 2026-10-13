"""Reusable widgets. Everything takes its colours from the application palette,
so it follows the desktop theme (light, dark, accent colour) automatically."""

from __future__ import annotations

import math
from typing import Any, Callable

import pandas as pd
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PyQt6.QtGui import QFont, QPalette
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QFrame, QHBoxLayout, QHeaderView, QLabel, QSizePolicy,
    QStyle, QStyledItemDelegate, QStyleOptionProgressBar, QTableView, QTableWidget, QTableWidgetItem,
    QToolButton, QVBoxLayout, QWidget,
)

from ..formatting import metric_rows
from ..research.base import Finding, Report, fmt_money, fmt_pct
from .theme import STATUS_LABELS, status_icon


def heading(text: str, level: int = 2) -> QLabel:
    lbl = QLabel(text)
    f = lbl.font()
    f.setPointSizeF(f.pointSizeF() * {1: 1.6, 2: 1.3, 3: 1.1}.get(level, 1.0))
    f.setWeight(QFont.Weight.DemiBold if level > 1 else QFont.Weight.Bold)
    lbl.setFont(f)
    lbl.setWordWrap(True)
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lbl


def dim_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    pal = lbl.palette()
    pal.setColor(QPalette.ColorRole.WindowText, pal.color(QPalette.ColorRole.PlaceholderText))
    lbl.setPalette(pal)
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lbl


def text_label(text: str, rich: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setTextFormat(Qt.TextFormat.RichText if rich else Qt.TextFormat.PlainText)
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse)
    lbl.setOpenExternalLinks(True)
    # Preferred (not Minimum) lets the layout use heightForWidth instead of QLabel's
    # narrow-wrap sizeHint, which otherwise pads one-line text with blank space.
    lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
    lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    return lbl


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


class Card(QFrame):
    """A framed panel, drawn by the current style (Breeze/Fusion)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setAutoFillBackground(True)
        self.setBackgroundRole(QPalette.ColorRole.Base)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(14, 12, 14, 12)
        self.body.setSpacing(6)


class KpiCard(Card):
    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.title = dim_label(title)
        self.value = QLabel("—")
        f = self.value.font()
        f.setPointSizeF(f.pointSizeF() * 1.9)
        f.setWeight(QFont.Weight.DemiBold)
        self.value.setFont(f)
        self.body.addWidget(self.title)
        self.body.addWidget(self.value)

    def set(self, text: str, tooltip: str = "") -> None:
        self.value.setText(text)
        self.setToolTip(tooltip)


class FindingRow(QWidget):
    def __init__(self, f: Finding, parent: QWidget | None = None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(8)
        icon = QLabel()
        icon.setPixmap(status_icon(f.status).pixmap(18, 18))
        icon.setToolTip(STATUS_LABELS.get(f.status, ""))
        icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        icon.setFixedWidth(20)
        lay.addWidget(icon)
        lay.addWidget(text_label(f.text), 1)


class FindingsList(QWidget):
    def __init__(self, findings: list[Finding] | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(2)
        if findings:
            self.set(findings)

    def set(self, findings: list[Finding]) -> None:
        clear_layout(self.lay)
        for f in findings:
            self.lay.addWidget(FindingRow(f))


class Collapsible(QWidget):
    """A disclosure triangle + title that shows/hides a body widget."""

    def __init__(self, title: str, body: QWidget, expanded: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.toggle = QToolButton()
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(expanded)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setAutoRaise(True)
        self.body = body
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.toggle)
        lay.addWidget(body)
        self.toggle.toggled.connect(self._sync)
        self._sync(expanded)

    def _sync(self, on: bool) -> None:
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
        self.body.setVisible(on)


class MetricsTable(QTableWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(0, 2, parent)
        self.setHorizontalHeaderLabels(["Metric", "Value"])
        self.verticalHeader().hide()
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

    def set(self, metrics: dict) -> None:
        rows = metric_rows(metrics)
        self.setRowCount(len(rows))
        for i, (k, v) in enumerate(rows):
            self.setItem(i, 0, QTableWidgetItem(k))
            item = QTableWidgetItem(v)
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.setItem(i, 1, item)
        h = self.horizontalHeader().height() + sum(self.rowHeight(i) for i in range(len(rows))) + 4
        self.setFixedHeight(min(h, 420))


class LensView(QWidget):
    """Score, verdict, philosophy, findings, metrics and caveats for one research lens."""

    def __init__(self, parent: QWidget | None = None, extra_top: QWidget | None = None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        top = QHBoxLayout()
        self.score = KpiCard("Score")
        self.score.setFixedWidth(150)
        top.addWidget(self.score)
        self.verdict = heading("", 2)
        top.addWidget(self.verdict, 1)
        lay.addLayout(top)
        if extra_top is not None:
            lay.addWidget(extra_top)
        self.philosophy = text_label("")
        self.philosophy.setContentsMargins(22, 0, 0, 6)
        lay.addWidget(Collapsible("How this lens thinks", self.philosophy))
        self.findings = FindingsList()
        lay.addWidget(self.findings)
        self.metrics = MetricsTable()
        lay.addWidget(Collapsible("All metrics", self.metrics))
        self.caveats = QVBoxLayout()
        lay.addLayout(self.caveats)
        lay.addStretch(1)

    def set(self, rep: Report) -> None:
        self.score.set("n/a" if rep.score is None else f"{rep.score:.0f}/100")
        self.verdict.setText(rep.verdict or "—")
        self.philosophy.setText(rep.philosophy)
        self.findings.set(rep.findings)
        self.metrics.set(rep.metrics)
        clear_layout(self.caveats)
        for c in rep.caveats:
            self.caveats.addWidget(dim_label(f"Caveat: {c}"))


# ---------------------------------------------------------------------------
# Tables: pandas model + native progress-bar delegate for 0-100 scores
# ---------------------------------------------------------------------------

def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v))


FORMATS: dict[str, Callable[[Any], str]] = {
    "money": lambda v: fmt_money(v) if _is_num(v) else "",
    "pct": lambda v: fmt_pct(v) if _is_num(v) else "",
    "ratio": lambda v: f"{v:.1f} : 1" if _is_num(v) else "",
    "num1": lambda v: f"{v:.1f}" if _is_num(v) else "",
    "score": lambda v: f"{v:.0f}" if _is_num(v) else "",
    "text": lambda v: "" if v is None or (isinstance(v, float) and math.isnan(v)) else str(v),
}


class DataFrameModel(QAbstractTableModel):
    """Read-only view of selected DataFrame columns. columns = [(col, header, format)]."""

    def __init__(self, columns: list[tuple[str, str, str]], parent=None):
        super().__init__(parent)
        self.columns = columns
        self.df = pd.DataFrame()

    def set_frame(self, df: pd.DataFrame) -> None:
        self.beginResetModel()
        self.df = df.reset_index(drop=True)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):  # noqa: N802 (Qt API)
        return 0 if parent.isValid() else len(self.df)

    def columnCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() else len(self.columns)

    def raw(self, row: int, col: int) -> Any:
        name = self.columns[col][0]
        return self.df.at[row, name] if name in self.df.columns else None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        v = self.raw(index.row(), index.column())
        fmt = self.columns[index.column()][2]
        if role == Qt.ItemDataRole.DisplayRole:
            return FORMATS[fmt](v)
        if role == Qt.ItemDataRole.UserRole:  # sort key
            if _is_num(v):
                return float(v)
            return "" if v is None or (isinstance(v, float) and math.isnan(v)) else str(v)
        if role == Qt.ItemDataRole.TextAlignmentRole and fmt != "text":
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole and fmt == "text":
            return FORMATS["text"](v)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.columns[section][1]
        return None

    def ticker_at(self, row: int) -> str | None:
        return str(self.df.at[row, "Ticker"]) if "Ticker" in self.df.columns and row < len(self.df) else None


class ScoreDelegate(QStyledItemDelegate):
    """Draws a 0-100 score as the style's own progress bar (Breeze bar on Plasma)."""

    def paint(self, painter, option, index):
        v = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(v, float):
            return super().paint(painter, option, index)
        bar = QStyleOptionProgressBar()
        bar.rect = option.rect.adjusted(4, 5, -4, -5)
        bar.minimum, bar.maximum = 0, 100
        bar.progress = int(round(v))
        bar.text = f"{v:.0f}"
        bar.textVisible = True
        bar.state = option.state | QStyle.StateFlag.State_Horizontal
        bar.palette = option.palette
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ProgressBar, bar, painter, option.widget)


class FrameTable(QTableView):
    """Sortable table over a DataFrameModel; double-click/Enter emits the row's ticker."""

    def __init__(self, columns: list[tuple[str, str, str]], on_open: Callable[[str], None] | None = None, parent=None):
        super().__init__(parent)
        self.model_ = DataFrameModel(columns, self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model_)
        self.proxy.setSortRole(Qt.ItemDataRole.UserRole)
        self.setModel(self.proxy)
        self.setSortingEnabled(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.verticalHeader().hide()
        self.horizontalHeader().setStretchLastSection(True)
        self.setWordWrap(False)
        delegate = ScoreDelegate(self)
        for i, (_, _, fmt) in enumerate(columns):
            if fmt == "score":
                self.setItemDelegateForColumn(i, delegate)
        self.on_open = on_open
        self.doubleClicked.connect(self._open)
        self.activated.connect(self._open)

    def set_frame(self, df: pd.DataFrame) -> None:
        self.model_.set_frame(df)
        self.resizeColumnsToContents()
        for i, (_, _, fmt) in enumerate(self.model_.columns):
            if fmt == "score":
                self.setColumnWidth(i, max(self.columnWidth(i), 110))

    def selected_ticker(self) -> str | None:
        rows = self.selectionModel().selectedRows()
        return self.model_.ticker_at(self.proxy.mapToSource(rows[0]).row()) if rows else None

    def _open(self, index) -> None:
        t = self.model_.ticker_at(self.proxy.mapToSource(index).row())
        if t and self.on_open:
            self.on_open(t)
