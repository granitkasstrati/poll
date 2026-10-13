"""Shared result types for every research module."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

GOOD, WARN, BAD, INFO = "good", "warn", "bad", "info"


@dataclass
class Finding:
    status: str  # GOOD / WARN / BAD / INFO
    text: str


@dataclass
class Report:
    key: str
    title: str
    philosophy: str  # one-paragraph "how this lens thinks"
    score: float | None = None  # 0-100, None when the lens doesn't apply
    verdict: str = ""
    findings: list[Finding] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    caveats: list[str] = field(default_factory=list)

    def add(self, status: str, text: str) -> None:
        self.findings.append(Finding(status, text))

    @property
    def red_flags(self) -> list[str]:
        return [f.text for f in self.findings if f.status == BAD]

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "score": self.score,
            "verdict": self.verdict,
            "findings": [{"status": f.status, "text": f.text} for f in self.findings],
            "metrics": {k: _jsonable(v) for k, v in self.metrics.items() if not k.startswith("_")},
            "caveats": self.caveats,
        }


def _jsonable(v: Any) -> Any:
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if hasattr(v, "item"):  # numpy scalar
        return v.item()
    return v


class Checklist:
    """Accumulates pass/fail points so a lens can turn criteria into a 0-100 score.

    Criteria whose data is missing are skipped rather than counted as failures,
    so a thin data feed lowers confidence (reported via `coverage`) instead of
    silently punishing the company.
    """

    def __init__(self) -> None:
        self.earned = 0.0
        self.possible = 0.0
        self.skipped = 0

    def check(self, ok: bool | None, weight: float = 1.0, partial: float | None = None) -> None:
        if ok is None and partial is None:
            self.skipped += 1
            return
        self.possible += weight
        if partial is not None:
            self.earned += weight * max(0.0, min(1.0, partial))
        elif ok:
            self.earned += weight

    @property
    def score(self) -> float | None:
        return None if self.possible == 0 else round(float(100 * self.earned / self.possible), 1)

    @property
    def coverage(self) -> float:
        total = self.possible + self.skipped
        return 0.0 if total == 0 else self.possible / total


def fmt_pct(x: float | None, digits: int = 1) -> str:
    return "n/a" if x is None or not math.isfinite(x) else f"{x * 100:.{digits}f}%"


def fmt_num(x: float | None, digits: int = 2) -> str:
    return "n/a" if x is None or not math.isfinite(x) else f"{x:,.{digits}f}"


def fmt_money(x: float | None) -> str:
    if x is None or not math.isfinite(x):
        return "n/a"
    a = abs(x)
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            return f"${x / div:,.2f}{suf}"
    return f"${x:,.2f}"


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def scale(x: float | None, lo: float, hi: float) -> float | None:
    """Linear map of x from [lo, hi] onto [0, 1] (clamped). Works for lo > hi too."""
    if x is None or not math.isfinite(x):
        return None
    if hi == lo:
        return 1.0 if x >= hi else 0.0
    return clamp01((x - lo) / (hi - lo))
