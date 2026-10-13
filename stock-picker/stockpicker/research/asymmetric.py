"""High-risk, asymmetric-payoff lens.

For speculative positions the question isn't 'is this a good company' but
'if I'm right, how much do I make vs. how much do I lose if I'm wrong,
and can I size it so being wrong doesn't hurt?' Munger's version: bet
heavily only when the odds are lopsided, and never in a way that can
take you out of the game.
"""

from __future__ import annotations

import math

import numpy as np

from ..data import CompanyData, safe_div
from .base import BAD, GOOD, INFO, WARN, Report, fmt_money, fmt_num, fmt_pct, scale


def analyze(d: CompanyData, future_report=None) -> Report:
    r = Report(
        key="asymmetric",
        title="Asymmetric bet (high risk / high reward)",
        philosophy=(
            "Speculation done sensibly: estimate a realistic bull-case and bear-case value, compare the "
            "upside to the downside, and check what could wipe the position out (cash burn, debt, dilution). "
            "Only lopsided bets — 3:1 or better — justify the risk, and only in position sizes you can lose entirely."
        ),
    )
    price = d.price
    h = d.history
    if not price:
        r.add(INFO, "No price available.")
        return r

    # --- Volatility and drawdown profile ---
    vol = mdd = None
    if h is not None and len(h) > 60:
        rets = np.log(h["Close"]).diff().dropna()
        vol = float(rets.iloc[-252:].std() * math.sqrt(252))
        roll_max = h["Close"].cummax()
        mdd = float((h["Close"] / roll_max - 1).min())
        r.metrics["Annualized volatility"] = vol
        r.metrics["Max drawdown (period)"] = mdd
        r.add(INFO, f"Annualized volatility {fmt_pct(vol)}; worst peak-to-trough fall in the period {fmt_pct(mdd)}.")

    # --- Bull / bear values: analyst extremes and DCF scenarios, whichever exist ---
    bull_candidates, bear_candidates = [], []
    if d.get("targetHighPrice"):
        bull_candidates.append(d.get("targetHighPrice"))
    if d.get("targetLowPrice"):
        bear_candidates.append(d.get("targetLowPrice"))
    dcf = (future_report.metrics.get("DCF") if future_report else None) or {}
    if dcf:
        bull_candidates.append(dcf["Bull"]["value"])
        bear_candidates.append(dcf["Bear"]["value"])
    if h is not None and len(h) > 252:
        hi52, lo52 = float(h["High"].iloc[-252:].max()), float(h["Low"].iloc[-252:].min())
        bull_candidates.append(hi52)  # a round-trip to the 52w high is a plausible re-rating
        bear_candidates.append(lo52)

    # Book value (tangible floor) for asset-heavy names
    bvps = d.get("bookValue")
    if bvps and bvps > 0 and price / bvps < 3:  # book is meaningless for asset-light firms
        bear_candidates.append(bvps)

    upside = downside = ratio = None
    if bull_candidates and bear_candidates:
        bull = float(np.median(bull_candidates))
        bear = float(min(np.median(bear_candidates), price))  # downside can't be negative
        upside = bull / price - 1
        downside = 1 - bear / price
        # When downside is tiny, guard the ratio with a volatility-based minimum loss.
        floor_loss = max(downside, 0.5 * (vol or 0.3) * math.sqrt(0.5))
        ratio = upside / floor_loss if floor_loss > 0 else None
        r.metrics.update({"Bull value": bull, "Bear value": bear, "Upside": upside, "Downside": downside, "Upside/Downside": ratio})
        r.add(GOOD if ratio and ratio >= 3 else WARN if ratio and ratio >= 1.5 else BAD,
              f"Bull ≈ {fmt_money(bull)} ({fmt_pct(upside)}) vs bear ≈ {fmt_money(bear)} (−{fmt_pct(downside)}): "
              f"payoff ratio {fmt_num(ratio, 1)}:1.")

    # --- Catalysts / fuel ---
    short = d.get("shortPercentOfFloat")
    if short is not None:
        r.metrics["Short % of float"] = short
        if short >= 0.15:
            r.add(WARN, f"Short interest {fmt_pct(short)} of float — squeeze fuel, but also a crowd betting on failure. Find out why.")
        else:
            r.add(INFO, f"Short interest {fmt_pct(short)} of float.")
    mcap = d.market_cap
    if mcap:
        r.metrics["Market cap"] = mcap
        if mcap < 2e9:
            r.add(INFO, f"Small cap ({fmt_money(mcap)}): less analyst coverage → more mispricing, and more blow-ups.")
    rev_g = d.get("revenueGrowth")
    if rev_g is not None:
        r.metrics["Revenue growth (YoY)"] = rev_g
        if rev_g >= 0.3:
            r.add(GOOD, f"Revenue growing {fmt_pct(rev_g)} YoY — a real business is forming under the story.")

    # --- What kills the bet ---
    kill = []
    fcf = d.fcf_series()
    cash = d.latest("cash")
    runway = None
    if len(fcf) and fcf.iloc[-1] < 0 and cash:
        runway = cash / abs(float(fcf.iloc[-1]))
        r.metrics["Cash runway (years)"] = round(runway, 1)
        if runway < 1.5:
            kill.append(f"only ~{runway:.1f} years of cash at current burn (expect dilution)")
    debt, equity = d.latest("total_debt"), d.latest("equity")
    de = safe_div(debt, equity)
    if de is not None and (de > 2 or (equity is not None and equity < 0)):
        kill.append("heavy debt relative to equity")
    sc = d.series("shares_diluted")
    if len(sc) >= 2 and sc.iloc[-1] > sc.iloc[0] * 1.15:
        kill.append(f"share count up {sc.iloc[-1] / sc.iloc[0] - 1:.0%} over the statement window (serial diluter)")
    for k in kill:
        r.add(BAD, f"Wipe-out risk: {k}.")

    # --- Score: payoff asymmetry, tempered by survivability ---
    parts = []
    if ratio is not None:
        parts.append((0.55, scale(ratio, 1.0, 5.0)))
    if vol is not None:
        parts.append((0.15, scale(vol, 0.2, 0.7)))  # for this tab, volatility = opportunity
    parts.append((0.30, 1.0 - min(1.0, 0.4 * len(kill))))
    parts = [(w, v) for w, v in parts if v is not None]
    if parts:
        raw = sum(w * v for w, v in parts) / sum(w for w, _ in parts)
        # Each wipe-out risk cuts the score: a great payoff is worthless if you're diluted to zero first.
        r.score = round(100 * raw * max(0.0, 1 - 0.25 * len(kill)), 1)
    s = r.score or 0
    r.verdict = (
        "Lopsided bet — worth a small, speculative position after research" if s >= 65 and (ratio or 0) >= 3 else
        "Speculative — payoff not yet compelling" if s >= 40 else
        "Poor odds"
    )
    r.add(INFO, "Size speculative bets so a total loss costs ≤ 1–2% of your portfolio. Expect most to fail; a few winners pay for the rest.")
    r.caveats.append("Bull/bear values blend analyst extremes, DCF scenarios and the 52-week range: rough anchors, not forecasts.")
    return r
