"""Display formatting shared by the web and desktop front ends."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .research.base import fmt_money, fmt_pct

_PCT_HINTS = ("margin", "growth", "roic", "roe", "yield", "rate", "ownership", "return", "volatility",
              "drawdown", "upside", "downside", "from 52w", "% of", "/ revenue", "change / yr", "accrual",
              "sbc / fcf", "short %", "fcf / net")
_MONEY_HINTS = ("Price", "value", "Value", "share", "Entry", "Stop", "Target", "Close", "target", "Bull", "Bear", "cap")


def format_metric(key: str, value: Any) -> str:
    """Pick %, $ or plain formatting for a metric from its name."""
    if value is None:
        return "n/a"
    if isinstance(value, float):
        pctish = any(s in key.lower() for s in _PCT_HINTS) and "(%)" not in key and "/Downside" not in key
        if pctish:
            return fmt_pct(value)
        if abs(value) >= 1e6 or any(s in key for s in _MONEY_HINTS):
            return fmt_money(value)
        return f"{value:,.2f}"
    return str(value)


def metric_rows(metrics: dict) -> list[tuple[str, str]]:
    """(name, formatted value) pairs, skipping internal and nested entries."""
    return [(k, format_metric(k, v)) for k, v in metrics.items()
            if not k.startswith("_") and not isinstance(v, (dict, pd.DataFrame))]
