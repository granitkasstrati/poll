"""Run every research lens on one company."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..data import CompanyData
from . import asymmetric, forensic, future, graham, moat, technical
from .base import Report
from .munger import MungerView, synthesize


@dataclass
class Assumptions:
    discount_rate: float = 0.09
    aaa_yield: float = 0.053


@dataclass
class Research:
    data: CompanyData
    reports: dict[str, Report]
    munger: MungerView
    assumptions: Assumptions = field(default_factory=Assumptions)

    def summary(self) -> dict[str, Any]:
        """Flat dict used by the screener tables and the AI memo prompt."""
        d = self.data
        g = lambda k: self.reports[k].score if k in self.reports else None
        fut, tech, asym = self.reports["future"], self.reports["technical"], self.reports["asymmetric"]
        return {
            "Ticker": d.ticker,
            "Name": d.name,
            "Sector": d.sector,
            "Price": d.price,
            "Market cap": d.market_cap,
            "Munger score": self.munger.report.score,
            "Munger verdict": self.munger.report.verdict,
            "Quality": g("moat"),
            "Graham": g("graham"),
            "Future": g("future"),
            "Strength": g("forensic"),
            "ROIC": self.reports["moat"].metrics.get("ROIC (avg)"),
            "Base MoS": fut.metrics.get("Base-case margin of safety"),
            "Implied growth": fut.metrics.get("Implied growth (reverse DCF)"),
            "Swing score": g("technical"),
            "Setup": tech.metrics.get("Setup"),
            "Trend": tech.metrics.get("Trend"),
            "RSI": tech.metrics.get("RSI(14)"),
            "Entry": tech.metrics.get("Entry"),
            "Stop": tech.metrics.get("Stop"),
            "Target": tech.metrics.get("Target"),
            "R/R": tech.metrics.get("Reward/Risk"),
            "Asymmetry score": g("asymmetric"),
            "Upside": asym.metrics.get("Upside"),
            "Downside": asym.metrics.get("Downside"),
            "Payoff ratio": asym.metrics.get("Upside/Downside"),
            "Volatility": asym.metrics.get("Annualized volatility"),
            "Short % float": asym.metrics.get("Short % of float"),
            "Lollapalooza": len(self.munger.lollapalooza),
        }


def run_all(d: CompanyData, assumptions: Assumptions | None = None) -> Research:
    a = assumptions or Assumptions()
    reports: dict[str, Report] = {}
    reports["graham"] = graham.analyze(d, aaa_yield=a.aaa_yield)
    reports["future"] = future.analyze(d, discount_rate=a.discount_rate)
    reports["moat"] = moat.analyze(d)
    reports["forensic"] = forensic.analyze(d)
    reports["technical"] = technical.analyze(d)
    reports["asymmetric"] = asymmetric.analyze(d, future_report=reports["future"])
    return Research(d, reports, synthesize(d, reports), a)
