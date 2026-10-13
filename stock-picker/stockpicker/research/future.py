"""Future prospects: growth runway, reinvestment, and what the price already assumes.

Central idea (Munger/Buffett via Mauboussin's "Expectations Investing"):
instead of forecasting the future, back out the growth the current price
implies (reverse DCF) and ask whether that bar is easy or heroic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..data import CompanyData, cagr, safe_div
from .base import BAD, GOOD, INFO, WARN, Checklist, Report, fmt_money, fmt_pct, scale

TERMINAL_GROWTH = 0.025
HIGH_GROWTH_YEARS = 5
FADE_YEARS = 5


@dataclass
class DCFResult:
    growth: float
    value_per_share: float


def dcf_per_share(cf0: float, growth: float, discount: float, terminal: float = TERMINAL_GROWTH) -> float:
    """Two-stage DCF on a per-share cash flow.

    Years 1-5 grow at `growth`, years 6-10 fade linearly to `terminal`,
    then a Gordon-growth terminal value.
    """
    if discount <= terminal:
        raise ValueError("discount rate must exceed terminal growth")
    value, cf = 0.0, cf0
    years = HIGH_GROWTH_YEARS + FADE_YEARS
    for t in range(1, years + 1):
        if t <= HIGH_GROWTH_YEARS:
            g = growth
        else:
            k = (t - HIGH_GROWTH_YEARS) / FADE_YEARS
            g = growth + (terminal - growth) * k
        cf *= 1 + g
        value += cf / (1 + discount) ** t
    tv = cf * (1 + terminal) / (discount - terminal)
    return value + tv / (1 + discount) ** years


def implied_growth(price: float, cf0: float, discount: float, lo: float = -0.5, hi: float = 1.0) -> float | None:
    """Reverse DCF: the stage-1 growth rate at which DCF value equals price (bisection)."""
    if cf0 <= 0 or price <= 0:
        return None
    f = lambda g: dcf_per_share(cf0, g, discount) - price
    if f(lo) > 0:
        return lo  # even shrinking 50%/yr justifies the price
    if f(hi) < 0:
        return None  # price implies > 100%/yr: off the charts
    for _ in range(80):
        mid = (lo + hi) / 2
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def owner_earnings_per_share(d: CompanyData) -> tuple[float | None, str]:
    """Average of the last 3 years of (free cash flow − stock comp) per share.

    Stock comp is a real cost to owners even though it's added back to
    operating cash flow — Buffett's "if compensation isn't an expense, what is?"
    """
    fcf = d.fcf_series()
    if not len(fcf):
        return None, "no cash-flow data"
    sbc = d.series("sbc").reindex(fcf.index).fillna(0.0)
    oe = (fcf - sbc).iloc[-3:]
    shares = d.shares
    if not shares:
        return None, "unknown share count"
    return float(oe.mean()) / shares, f"avg of last {len(oe)} yrs FCF − SBC"


def growth_estimate(d: CompanyData) -> tuple[float | None, dict[str, float]]:
    """Blend historical and analyst growth signals into one base-case rate."""
    signals: dict[str, float] = {}
    rev_cagr = cagr(d.series("revenue"))
    if rev_cagr is not None:
        signals["Revenue CAGR (hist.)"] = rev_cagr
    fcf_cagr = cagr(d.fcf_series())
    if fcf_cagr is not None:
        signals["FCF CAGR (hist.)"] = fcf_cagr
    fe, te = d.get("forwardEps"), d.get("trailingEps")
    if fe and te and te > 0:
        signals["Analyst next-yr EPS growth"] = fe / te - 1
    if d.get("revenueGrowth") is not None:
        signals["Latest revenue growth (YoY)"] = d.get("revenueGrowth")
    if not signals:
        return None, signals
    base = float(np.median(list(signals.values())))
    # Very high growth never persists; cap the starting rate and let the fade do the rest.
    return max(-0.05, min(0.25, base)), signals


def analyze(d: CompanyData, discount_rate: float = 0.09) -> Report:
    r = Report(
        key="future",
        title="Future prospects & expectations",
        philosophy=(
            "Value is the cash a business will produce from here on, discounted. Rather than pretending "
            "to know the future, this lens asks: how much runway and reinvestment capacity does the company "
            "have, and what growth is the market *already* pricing in? Buying is attractive when the "
            "bar the price sets is low relative to what the business has shown it can do."
        ),
    )
    cl = Checklist()
    price = d.price

    revenue = d.series("revenue")
    rev_cagr = cagr(revenue)
    if rev_cagr is not None:
        cl.check(None, partial=scale(rev_cagr, 0.0, 0.15))
        status = GOOD if rev_cagr >= 0.08 else WARN if rev_cagr >= 0.0 else BAD
        r.add(status, f"Revenue grew {fmt_pct(rev_cagr)}/yr over {len(revenue)} years of statements.")

    # Operating margin trend: are economies of scale showing up?
    op, rev = d.series("operating_income"), revenue
    if len(op) >= 2 and len(rev) >= 2:
        margins = (op / rev).dropna()
        if len(margins) >= 2:
            delta = float(margins.iloc[-1] - margins.iloc[0])
            trend = "expanding" if delta > 0.005 else "contracting" if delta < -0.005 else "stable"
            cl.check(delta >= -0.005 and margins.iloc[-1] > 0, weight=0.75)
            r.add(GOOD if trend != "contracting" and margins.iloc[-1] > 0 else WARN,
                  f"Operating margin moved {fmt_pct(margins.iloc[0])} → {fmt_pct(margins.iloc[-1])} ({trend}).")
            r.metrics["Operating margin (latest)"] = float(margins.iloc[-1])

    # Reinvestment: R&D intensity and growth capex
    rnd = d.latest("rnd")
    rd_int = safe_div(rnd, d.latest("revenue"))
    if rd_int is not None:
        r.metrics["R&D / revenue"] = rd_int
        r.add(INFO, f"R&D intensity {fmt_pct(rd_int)} of revenue — spending on future products.")
    capex, dep = d.latest("capex"), d.latest("depreciation")
    if capex is not None and dep:
        ratio = abs(capex) / dep
        r.metrics["Capex / D&A"] = ratio
        r.add(INFO, f"Capex is {ratio:.1f}× depreciation "
              f"({'investing for growth' if ratio > 1.3 else 'roughly maintenance level' if ratio > 0.8 else 'under-investing or asset-light'}).")

    # Sustainable growth from internal funding: ROE × retention
    roe = d.get("returnOnEquity")
    payout = d.get("payoutRatio") or 0.0
    if roe is not None and 0 < roe < 1.0:
        sgr = roe * (1 - min(max(payout, 0.0), 1.0))
        r.metrics["Sustainable growth (ROE × retention)"] = sgr
        cl.check(None, weight=0.75, partial=scale(sgr, 0.0, 0.15))
        r.add(INFO, f"Self-funded growth capacity ≈ {fmt_pct(sgr)}/yr (ROE {fmt_pct(roe)} × retention {fmt_pct(1 - payout)}).")

    # Analyst view (a data point, not a verdict)
    target, n = d.get("targetMeanPrice"), d.get("numberOfAnalystOpinions")
    if target and price:
        up = target / price - 1
        r.metrics["Analyst mean target"] = target
        r.add(INFO, f"{int(n or 0)} analysts' mean target {fmt_money(target)} ({fmt_pct(up)} vs price). "
              "Munger: 'Show me the incentive and I'll show you the outcome' — sell-side targets skew optimistic.")

    # --- DCF scenarios & reverse DCF ---
    base_g, signals = growth_estimate(d)
    r.metrics.update({f"Signal · {k}": v for k, v in signals.items()})
    oe_ps, oe_note = owner_earnings_per_share(d)
    r.metrics["Owner earnings / share"] = oe_ps
    r.metrics["Discount rate"] = discount_rate

    if d.is_financial:
        r.caveats.append("Free-cash-flow DCF is unreliable for banks/insurers (deposits and float distort cash flow).")

    if oe_ps is not None and oe_ps > 0 and base_g is not None and price:
        scenarios = {
            "Bear": max(-0.10, base_g * 0.5 - 0.02),
            "Base": base_g,
            "Bull": min(0.35, base_g * 1.5 + 0.02),
        }
        dcf = {k: DCFResult(g, dcf_per_share(oe_ps, g, discount_rate)) for k, g in scenarios.items()}
        r.metrics["DCF"] = {k: {"growth": v.growth, "value": v.value_per_share} for k, v in dcf.items()}
        base_val = dcf["Base"].value_per_share
        mos = 1 - price / base_val
        r.metrics["Base-case margin of safety"] = mos
        cl.check(None, weight=2.0, partial=scale(mos, -0.5, 0.3))
        r.add(GOOD if mos >= 0.2 else WARN if mos >= -0.15 else BAD,
              f"DCF ({oe_note}, {fmt_pct(discount_rate)} discount): bear {fmt_money(dcf['Bear'].value_per_share)} · "
              f"base {fmt_money(base_val)} · bull {fmt_money(dcf['Bull'].value_per_share)} vs price {fmt_money(price)}.")
        if price < dcf["Bear"].value_per_share:
            r.add(GOOD, "Price is below even the bear-case value — the kind of asymmetry Munger waits years for.")

        ig = implied_growth(price, oe_ps, discount_rate)
        r.metrics["Implied growth (reverse DCF)"] = ig
        hist = rev_cagr if rev_cagr is not None else base_g
        if ig is None:
            cl.check(False, weight=2.0)
            r.add(BAD, "Reverse DCF: price implies >100%/yr growth on current owner earnings — priced for a miracle.")
        else:
            gap = ig - hist
            cl.check(None, weight=2.0, partial=scale(gap, 0.10, -0.05))
            status = GOOD if gap <= 0 else WARN if gap <= 0.07 else BAD
            r.add(status, f"Reverse DCF: the price implies {fmt_pct(ig)}/yr cash-flow growth for 5 years (then fading), "
                  f"vs {fmt_pct(hist)}/yr historical. "
                  + ("The bar is at or below what the business has already done." if gap <= 0 else
                     "The market expects acceleration — ask what would cause it." if gap <= 0.07 else
                     "The market expects much more than history shows: high expectations, thin margin for error."))
    elif oe_ps is not None and oe_ps <= 0:
        cl.check(False, weight=2.0)
        r.add(BAD, "Owner earnings (FCF − stock comp) are negative: value rests entirely on a future turnaround.")
    else:
        r.add(INFO, "Not enough data for a DCF.")

    r.score = cl.score
    s = r.score or 0
    r.verdict = (
        "Attractive runway at a reasonable expectation bar" if s >= 70 else
        "Mixed: growth or price expectations need scrutiny" if s >= 45 else
        "Future looks priced in or uncertain"
    )
    r.caveats.append(
        f"DCF assumes {HIGH_GROWTH_YEARS} years at the scenario rate, a {FADE_YEARS}-year fade to "
        f"{fmt_pct(TERMINAL_GROWTH)}, and owner earnings averaged over 3 years. Small input changes move the result a lot."
    )
    return r
