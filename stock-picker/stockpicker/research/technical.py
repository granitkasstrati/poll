"""Swing-trading lens: trend, momentum and a concrete entry/stop/target plan.

Munger himself didn't trade, so this lens borrows only his discipline:
decide in advance where you're wrong (the stop), size so being wrong is
survivable, and only take setups where the payoff dwarfs the risk.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..data import CompanyData
from .base import BAD, GOOD, INFO, WARN, Report, fmt_money, fmt_num, fmt_pct


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100)


def macd(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    line = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    return line, line.ewm(span=9, adjust=False).mean()


def atr(h: pd.DataFrame, period: int = 14) -> pd.Series:
    prev = h["Close"].shift()
    tr = pd.concat([h["High"] - h["Low"], (h["High"] - prev).abs(), (h["Low"] - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def indicators(h: pd.DataFrame) -> pd.DataFrame:
    out = h.copy()
    c = out["Close"]
    for n in (20, 50, 200):
        out[f"SMA{n}"] = c.rolling(n).mean()
    out["RSI"] = rsi(c)
    out["MACD"], out["MACDsig"] = macd(c)
    out["ATR"] = atr(out)
    mid, sd = c.rolling(20).mean(), c.rolling(20).std()
    out["BBup"], out["BBlo"] = mid + 2 * sd, mid - 2 * sd
    out["BBwidth"] = (out["BBup"] - out["BBlo"]) / mid
    out["VolAvg50"] = out["Volume"].rolling(50).mean()
    return out


@dataclass
class TradePlan:
    setup: str
    entry: float
    stop: float
    target: float

    @property
    def reward_risk(self) -> float:
        risk = self.entry - self.stop
        return (self.target - self.entry) / risk if risk > 0 else 0.0


def detect_setup(ind: pd.DataFrame) -> tuple[str, float]:
    """Return (setup name, quality 0-1) for the latest bar."""
    last = ind.iloc[-1]
    c, s20, s50, s200 = last["Close"], last["SMA20"], last["SMA50"], last["SMA200"]
    r = last["RSI"]
    uptrend = c > s200 and s50 > s200
    hi55 = ind["Close"].iloc[-56:-1].max()
    vol_ratio = last["Volume"] / last["VolAvg50"] if last["VolAvg50"] else 1.0
    squeeze = last["BBwidth"] <= ind["BBwidth"].iloc[-126:].quantile(0.15)
    macd_cross_up = ind["MACD"].iloc[-1] > ind["MACDsig"].iloc[-1] and ind["MACD"].iloc[-4] <= ind["MACDsig"].iloc[-4]

    if uptrend and c >= hi55 and vol_ratio >= 1.4:
        return "Breakout on volume", min(1.0, 0.6 + 0.2 * (vol_ratio - 1.4))
    if uptrend and 38 <= r <= 55 and abs(c - s50) / s50 <= 0.04:
        return "Pullback to 50-day in uptrend", 0.8 if macd_cross_up else 0.65
    if uptrend and 40 <= r <= 58 and abs(c - s20) / s20 <= 0.02:
        return "Pullback to 20-day in uptrend", 0.55 if not macd_cross_up else 0.7
    if uptrend and squeeze:
        return "Volatility squeeze in uptrend", 0.5
    if c > s200 and r < 32:
        return "Oversold in long-term uptrend", 0.5
    if c < s200 and s50 < s200:
        return "Downtrend — no long setup", 0.0
    return "No clear setup", 0.15


def plan_trade(ind: pd.DataFrame, setup: str) -> TradePlan:
    last = ind.iloc[-1]
    entry, a = float(last["Close"]), float(last["ATR"])
    swing_low = float(ind["Low"].iloc[-20:].min())
    # Stop below the recent swing low, but never tighter than 1 ATR or wider than 3 ATR.
    stop = min(max(swing_low - 0.25 * a, entry - 3 * a), entry - 1 * a)
    prior_high = float(ind["High"].iloc[-252:].max())
    target = prior_high if prior_high > entry + 2 * a and "Breakout" not in setup else entry + 3 * (entry - stop)
    return TradePlan(setup, entry, stop, target)


def analyze(d: CompanyData) -> Report:
    r = Report(
        key="technical",
        title="Swing-trade setup",
        philosophy=(
            "A swing trade is a bet on the next few days to weeks of price action, not on the business. "
            "Trade with the primary trend, enter on low-risk setups (pullbacks, breakouts on volume), "
            "define the exit *before* entering, and only take trades where reward is at least 2× risk."
        ),
    )
    h = d.history
    if h is None or len(h) < 210:
        r.add(INFO, "Need at least ~10 months of daily prices for trend analysis.")
        return r

    ind = indicators(h)
    last = ind.iloc[-1]
    setup, quality = detect_setup(ind)
    plan = plan_trade(ind, setup)
    rr = plan.reward_risk

    c = float(last["Close"])
    trend = ("Uptrend" if c > last["SMA200"] and last["SMA50"] > last["SMA200"] else
             "Downtrend" if c < last["SMA200"] and last["SMA50"] < last["SMA200"] else "Transition")
    hi52, lo52 = float(h["High"].iloc[-252:].max()), float(h["Low"].iloc[-252:].min())
    ret_3m = c / float(h["Close"].iloc[-63]) - 1

    r.metrics.update({
        "Setup": setup,
        "Trend": trend,
        "Close": c,
        "RSI(14)": round(float(last["RSI"]), 1),
        "ATR(14)": round(float(last["ATR"]), 2),
        "ATR % of price": float(last["ATR"]) / c,
        "3-month return": ret_3m,
        "From 52w high": c / hi52 - 1,
        "From 52w low": c / lo52 - 1,
        "Volume vs 50d avg": round(float(last["Volume"] / last["VolAvg50"]), 2) if last["VolAvg50"] else None,
        "Setup quality": round(quality, 2),
    })
    actionable = quality >= 0.3
    if actionable:
        r.metrics.update({"Entry": plan.entry, "Stop": plan.stop, "Target": plan.target, "Reward/Risk": round(rr, 2)})
    r.metrics["_indicators"] = ind  # for charting; stripped from JSON exports

    r.add(GOOD if trend == "Uptrend" else BAD if trend == "Downtrend" else WARN,
          f"Primary trend: {trend} (price {fmt_money(c)}, 50-day {fmt_money(last['SMA50'])}, 200-day {fmt_money(last['SMA200'])}).")
    rv = float(last["RSI"])
    r.add(WARN if rv >= 70 else GOOD if 40 <= rv <= 60 else INFO,
          f"RSI {rv:.0f} — {'overbought; chasing here gives poor reward/risk' if rv >= 70 else 'oversold' if rv <= 30 else 'neutral momentum'}.")
    r.add(GOOD if quality >= 0.6 else WARN if quality >= 0.3 else BAD, f"Setup: {setup}.")
    if not actionable:
        r.add(INFO, "No trade plan: without a defined setup there's no logical place for the stop. Wait for one.")
    else:
        r.add(GOOD if rr >= 2 else WARN if rr >= 1.5 else BAD,
              f"Plan: entry ≈ {fmt_money(plan.entry)}, stop {fmt_money(plan.stop)} ({fmt_pct(plan.stop / plan.entry - 1)}), "
              f"target {fmt_money(plan.target)} ({fmt_pct(plan.target / plan.entry - 1)}) → reward/risk {fmt_num(rr, 1)}.")
        r.add(INFO, "Position sizing: risk a fixed 0.5–1% of the account per trade. "
              "Shares = (account × risk%) ÷ (entry − stop).")

    rr_score = min(1.0, max(0.0, (rr - 1) / 2)) if actionable else 0.0
    trend_score = 1.0 if trend == "Uptrend" else 0.4 if trend == "Transition" else 0.0
    r.score = round(100 * (0.5 * quality + 0.3 * rr_score + 0.2 * trend_score), 1)
    if rv >= 75:  # extended: entering here usually means buying someone else's exit
        r.score = round(r.score * 0.7, 1)
    r.verdict = (
        f"Actionable: {setup.lower()}" if r.score >= 65 and rr >= 2 else
        "Watch for a better entry" if r.score >= 40 else
        "No trade"
    )
    r.caveats.append("Technical setups have modest edges at best. The stop is the strategy — honour it.")
    return r
