"""Native charts (pyqtgraph). Colours come from theme.chart_colors(), so they
follow the desktop's light/dark scheme; series use the validated categorical
slots, stop/target use the reserved status colours and always carry a label."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PyQt6.QtCore import Qt

from ..research.base import Report, fmt_money, fmt_pct
from .theme import chart_colors

pg.setConfigOptions(antialias=True)


def _epoch(idx: pd.Index) -> np.ndarray:
    return np.array([pd.Timestamp(t).timestamp() for t in idx], dtype=float)


class _ThemedPlot(pg.PlotWidget):
    def __init__(self, title: str, date_axis: bool = False, parent=None):
        axis = {"bottom": pg.DateAxisItem(orientation="bottom")} if date_axis else {}
        super().__init__(parent=parent, axisItems=axis)
        self.colors = chart_colors()
        c = self.colors
        self.setBackground(c["background"])
        self.setTitle(title, color=c["text"], size="11pt")
        pi = self.getPlotItem()
        pi.showGrid(x=True, y=True, alpha=0.12)
        for name in ("left", "bottom"):
            ax = pi.getAxis(name)
            ax.setPen(pg.mkPen(c["axis"]))
            ax.setTextPen(pg.mkPen(c["axis"]))
        pi.setMenuEnabled(False)
        pi.hideButtons()
        # No wheel-zoom: these charts live in scrolling tabs, and the wheel should scroll the page.
        self.setMouseEnabled(x=False, y=False)

    def wheelEvent(self, ev):  # noqa: N802 (Qt API)
        ev.ignore()  # let the surrounding scroll area scroll instead of pyqtgraph swallowing it

    def add_legend(self):
        leg = self.getPlotItem().addLegend(offset=(-10, 10), labelTextColor=self.colors["text"])
        leg.setBrush(pg.mkBrush(self.colors["background"]))
        return leg


class _Crosshair:
    """Vertical hover line + readout of every series at the nearest bar.

    Created once per chart; attach() re-adds its items after each plot.clear().
    """

    def __init__(self, plot: _ThemedPlot, fmt):
        self.plot, self.fmt = plot, fmt
        self.xs, self.series = np.array([]), {}
        c = plot.colors
        self.vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(c["axis"], width=1))
        self.label = pg.TextItem(color=c["text"], anchor=(0, 0), fill=pg.mkBrush(c["background"]),
                                 border=pg.mkPen(c["grid"]))
        plot.scene().sigMouseMoved.connect(self._moved)

    def attach(self, xs: np.ndarray, series: dict[str, np.ndarray]) -> None:
        self.xs, self.series = xs, series
        for item in (self.vline, self.label):
            item.setZValue(100)
            item.hide()
            self.plot.addItem(item, ignoreBounds=True)

    def _moved(self, pos):
        vb = self.plot.getPlotItem().vb
        if not len(self.xs) or not vb.sceneBoundingRect().contains(pos):
            self.vline.hide()
            self.label.hide()
            return
        x = vb.mapSceneToView(pos).x()
        i = int(np.clip(np.searchsorted(self.xs, x), 0, len(self.xs) - 1))
        self.vline.setPos(self.xs[i])
        date = pd.Timestamp(self.xs[i], unit="s").strftime("%Y-%m-%d")
        lines = [date] + [f"{k}: {self.fmt(v[i])}" for k, v in self.series.items() if np.isfinite(v[i])]
        self.label.setText("\n".join(lines))
        (x0, x1), (y0, y1) = vb.viewRange()
        # Keep the readout inside the plot: flip to the left side when hovering on the right half.
        self.label.setAnchor((1, 0) if self.xs[i] > (x0 + x1) / 2 else (0, 0))
        self.label.setPos(self.xs[i], y1)
        self.vline.show()
        self.label.show()


class PriceChart(_ThemedPlot):
    def __init__(self, parent=None):
        super().__init__("Price with trend averages", date_axis=True, parent=parent)
        self.setMinimumHeight(320)
        self.legend = self.add_legend()
        self.crosshair = _Crosshair(self, lambda v: fmt_money(float(v)))

    def set(self, rep: Report, days: int = 380) -> bool:
        self.clear()
        ind = rep.metrics.get("_indicators")
        if ind is None:
            return False
        ind = ind.iloc[-days:]
        xs = _epoch(ind.index)
        c = self.colors
        self.legend.clear()
        series = {}
        for (name, col), color in zip((("Close", "Close"), ("50-day avg", "SMA50"), ("200-day avg", "SMA200")), c["series"]):
            ys = ind[col].to_numpy(dtype=float)
            self.plot(xs, ys, pen=pg.mkPen(color, width=2), name=name, connect="finite")
            series[name] = ys
        m = rep.metrics
        if "Stop" in m:
            for label, val, color in (("Stop", m["Stop"], c["critical"]), ("Target", m["Target"], c["good"])):
                line = pg.InfiniteLine(pos=val, angle=0, movable=False, pen=pg.mkPen(color, width=1, style=Qt.PenStyle.DashLine),
                                       label=f"{label} {fmt_money(val)}",
                                       labelOpts={"position": 0.02, "color": c["text"], "anchors": [(0, 1), (0, 1)]})
                self.addItem(line)
        self.crosshair.attach(xs, series)
        self.getPlotItem().enableAutoRange()
        return True


class RsiChart(_ThemedPlot):
    def __init__(self, parent=None):
        super().__init__("RSI(14) momentum", date_axis=True, parent=parent)
        self.setFixedHeight(170)
        self.crosshair = _Crosshair(self, lambda v: f"{float(v):.0f}")

    def set(self, rep: Report, days: int = 380) -> bool:
        self.clear()
        ind = rep.metrics.get("_indicators")
        if ind is None:
            return False
        ind = ind.iloc[-days:]
        xs = _epoch(ind.index)
        ys = ind["RSI"].to_numpy(dtype=float)
        c = self.colors
        self.plot(xs, ys, pen=pg.mkPen(c["series"][0], width=2))
        for lvl, txt in ((70, "overbought 70"), (30, "oversold 30")):
            self.addItem(pg.InfiniteLine(pos=lvl, angle=0, movable=False, pen=pg.mkPen(c["axis"], style=Qt.PenStyle.DotLine),
                                         label=txt, labelOpts={"position": 0.98, "color": c["axis"]}))
        self.setYRange(0, 100, padding=0.02)
        self.crosshair.attach(xs, {"RSI": ys})
        return True


class DcfChart(_ThemedPlot):
    def __init__(self, parent=None):
        super().__init__("DCF value per share by scenario vs. today's price", parent=parent)
        self.setFixedHeight(210)

    def set(self, rep: Report, price: float | None) -> bool:
        self.clear()
        dcf = rep.metrics.get("DCF")
        if not dcf or not price:
            return False
        c = self.colors
        names = list(dcf.keys())[::-1]  # Bull on top
        vals = [dcf[k]["value"] for k in names]
        ys = list(range(len(names)))
        self.addItem(pg.BarGraphItem(x0=0, y=ys, height=0.5, width=vals, brush=c["series"][0], pen=pg.mkPen(None)))
        top = max(vals + [price]) * 1.3
        for y, v in zip(ys, vals):
            t = pg.TextItem(fmt_money(v), color=c["text"], anchor=(0, 0.5))
            t.setPos(v + top * 0.01, y)
            self.addItem(t)
        self.addItem(pg.InfiniteLine(pos=price, angle=90, movable=False, pen=pg.mkPen(c["text"], width=1, style=Qt.PenStyle.DashLine),
                                     label=f"Price {fmt_money(price)}", labelOpts={"position": 0.04, "color": c["text"]}))
        ax = self.getPlotItem().getAxis("left")
        ax.setTicks([[(y, f"{n} ({fmt_pct(dcf[n]['growth'])})") for y, n in zip(ys, names)]])
        self.setXRange(0, top, padding=0)
        self.setYRange(-0.6, len(names) - 0.4, padding=0)
        return True
