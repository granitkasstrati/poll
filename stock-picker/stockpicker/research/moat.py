"""Business quality, moat and management — the Buffett/Munger 'wonderful business' lens."""

from __future__ import annotations

import pandas as pd

from ..data import CompanyData, cagr, safe_div, stdev
from .base import BAD, GOOD, INFO, WARN, Checklist, Report, fmt_pct, scale


def roic_series(d: CompanyData) -> pd.Series:
    """NOPAT / (equity + debt − cash), per fiscal year."""
    ebit = d.series("ebit")
    if not len(ebit):
        return pd.Series(dtype=float)
    pretax, tax = d.series("pretax_income"), d.series("tax_provision")
    rate = (tax / pretax).where(pretax > 0).clip(0, 0.35).reindex(ebit.index).fillna(0.21)
    nopat = ebit * (1 - rate)
    equity = d.series("equity").reindex(ebit.index)
    debt = d.series("total_debt").reindex(ebit.index).fillna(0.0)
    cash = d.series("cash").reindex(ebit.index).fillna(0.0)
    ic = equity + debt - cash
    return (nopat / ic.where(ic > 0)).dropna()


def analyze(d: CompanyData) -> Report:
    r = Report(
        key="moat",
        title="Business quality & management (Munger)",
        philosophy=(
            "\"It's far better to buy a wonderful company at a fair price than a fair company at a wonderful price.\" "
            "A wonderful business earns high returns on the capital it employs, year after year, because something "
            "— brand, network, switching costs, scale — keeps competitors from bidding those returns away. "
            "It is run by honest, owner-minded people whose incentives line up with yours."
        ),
    )
    cl = Checklist()

    # --- Moat signal 1: high and persistent returns on capital ---
    roic = roic_series(d)
    if len(roic):
        avg, lo = float(roic.mean()), float(roic.min())
        r.metrics["ROIC (avg)"] = avg
        r.metrics["ROIC (worst yr)"] = lo
        cl.check(None, weight=3.0, partial=scale(avg, 0.06, 0.20))
        cl.check(lo >= 0.10, weight=1.0)
        status = GOOD if avg >= 0.15 and lo >= 0.10 else WARN if avg >= 0.08 else BAD
        r.add(status, f"Return on invested capital averaged {fmt_pct(avg)} (worst year {fmt_pct(lo)}). "
              "≥ 15% sustained is the fingerprint of a moat; below the ~8-9% cost of capital destroys value as it grows.")
    elif d.is_financial and d.get("returnOnEquity") is not None:
        roe = d.get("returnOnEquity")
        r.metrics["ROE"] = roe
        cl.check(None, weight=3.0, partial=scale(roe, 0.06, 0.18))
        r.add(GOOD if roe >= 0.13 else WARN, f"Return on equity {fmt_pct(roe)} (for financials ROE replaces ROIC; ≥ 13% is strong).")

    # --- Moat signal 2: pricing power via gross margin level and stability ---
    gp, rev = d.series("gross_profit"), d.series("revenue")
    gm = (gp / rev).dropna() if len(gp) and len(rev) else pd.Series(dtype=float)
    if len(gm):
        level, vol = float(gm.mean()), stdev(gm)
        r.metrics["Gross margin (avg)"] = level
        r.metrics["Gross margin stdev"] = vol
        cl.check(None, weight=1.5, partial=scale(level, 0.20, 0.60))
        if vol is not None:
            cl.check(vol <= 0.03, weight=1.0)
        stable = vol is not None and vol <= 0.03
        r.add(GOOD if level >= 0.4 and stable else WARN if level >= 0.2 else BAD,
              f"Gross margin {fmt_pct(level)} on average, {'stable' if stable else 'variable'} "
              f"(σ {fmt_pct(vol)}). High and steady margins signal pricing power; commodity businesses can't hold them.")

    # --- Moat signal 3: does growth come with cash? ---
    fcf, ni = d.fcf_series(), d.series("net_income")
    if len(fcf) and len(ni):
        joined = pd.concat([fcf, ni], axis=1, keys=["fcf", "ni"]).dropna()
        if len(joined) and joined["ni"].sum() > 0:
            conv = joined["fcf"].sum() / joined["ni"].sum()
            r.metrics["FCF / net income"] = conv
            cl.check(None, weight=1.5, partial=scale(conv, 0.5, 1.0))
            r.add(GOOD if conv >= 0.9 else WARN if conv >= 0.6 else BAD,
                  f"Cash conversion: free cash flow was {conv:.0%} of reported earnings. Real businesses turn profits into cash.")

    # --- Management signal 1: share count (buybacks vs dilution) ---
    shares = d.series("shares_diluted")
    if not len(shares):
        shares = d.series("shares_outstanding")
    sc = cagr(shares) if len(shares) >= 2 else None
    if sc is not None:
        r.metrics["Share count change / yr"] = sc
        cl.check(None, weight=1.5, partial=scale(sc, 0.03, -0.01))
        r.add(GOOD if sc <= -0.005 else WARN if sc <= 0.02 else BAD,
              f"Diluted share count {'shrank' if sc < 0 else 'grew'} {fmt_pct(abs(sc))}/yr — "
              + ("management is returning capital and increasing your slice." if sc <= -0.005 else
                 "roughly flat." if sc <= 0.02 else "owners are being diluted."))

    # --- Management signal 2: stock-based comp as a share of FCF ---
    sbc = d.latest("sbc")
    last_fcf = float(fcf.iloc[-1]) if len(fcf) else None
    sbc_ratio = safe_div(sbc, last_fcf) if last_fcf and last_fcf > 0 else None
    if sbc_ratio is not None:
        r.metrics["SBC / FCF"] = sbc_ratio
        cl.check(None, weight=1.0, partial=scale(sbc_ratio, 0.4, 0.05))
        r.add(GOOD if sbc_ratio <= 0.1 else WARN if sbc_ratio <= 0.3 else BAD,
              f"Stock compensation is {sbc_ratio:.0%} of free cash flow. High SBC quietly transfers ownership to insiders.")

    # --- Management signal 3: skin in the game (incentives) ---
    insiders = d.get("heldPercentInsiders")
    if insiders is not None:
        r.metrics["Insider ownership"] = insiders
        cl.check(None, weight=1.0, partial=scale(insiders, 0.0, 0.10))
        r.add(GOOD if insiders >= 0.05 else INFO,
              f"Insiders own {fmt_pct(insiders)}. Munger: incentives drive behavior — owner-operators tend to think like owners.")

    # --- Balance-sheet conservatism (a moat you can lose by borrowing) ---
    debt, ebitda = d.latest("total_debt"), d.get("ebitda") or d.latest("ebitda")
    cash = d.latest("cash") or 0.0
    if debt is not None and ebitda and ebitda > 0 and not d.is_financial:
        lev = (debt - cash) / ebitda
        r.metrics["Net debt / EBITDA"] = lev
        cl.check(None, weight=1.5, partial=scale(lev, 4.0, 0.5))
        r.add(GOOD if lev <= 1.5 else WARN if lev <= 3 else BAD,
              f"Net debt is {lev:.1f}× EBITDA. Munger: 'Smart men go broke three ways — liquor, ladies and leverage.'")

    r.score = cl.score
    s = r.score or 0
    r.verdict = (
        "Wonderful business: strong moat signals" if s >= 75 else
        "Good business with some moat evidence" if s >= 55 else
        "Ordinary business: little evidence of a durable edge" if s >= 35 else
        "Weak economics"
    )
    r.caveats.append("Numbers can show a moat exists but not *why*. Name the source (brand, network, switching cost, scale, regulation) and ask what would erode it.")
    return r
