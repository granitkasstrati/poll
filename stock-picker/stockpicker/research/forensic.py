"""Financial strength & accounting quality: Piotroski F-score, Altman Z, accruals."""

from __future__ import annotations

from ..data import CompanyData, safe_div
from .base import BAD, GOOD, INFO, WARN, Checklist, Report, fmt_num, fmt_pct, scale


def piotroski(d: CompanyData) -> tuple[int | None, list[tuple[str, bool]]]:
    """Piotroski's 9-point F-score from the two latest fiscal years."""
    def pair(item):
        return d.latest(item), d.previous(item)

    ni, ni0 = pair("net_income")
    ta, ta0 = pair("total_assets")
    cfo, _ = pair("operating_cash_flow")
    ltd, ltd0 = pair("long_term_debt")
    ca, ca0 = pair("current_assets")
    cli, cli0 = pair("current_liabilities")
    sh, sh0 = pair("shares_diluted")
    gp, gp0 = pair("gross_profit")
    rev, rev0 = pair("revenue")
    if None in (ni, ni0, ta, ta0, cfo):
        return None, []

    roa, roa0 = ni / ta, ni0 / ta0
    tests: list[tuple[str, bool | None]] = [
        ("Positive net income (ROA > 0)", roa > 0),
        ("Positive operating cash flow", cfo > 0),
        ("ROA improved", roa > roa0),
        ("Cash flow exceeds earnings (low accruals)", cfo > ni),
        ("Leverage fell", (ltd or 0) / ta <= (ltd0 or 0) / ta0 if ltd is not None or ltd0 is not None else None),
        ("Current ratio improved", (ca / cli > ca0 / cli0) if None not in (ca, cli, ca0, cli0) and cli and cli0 else None),
        ("No new shares issued", sh <= sh0 * 1.005 if sh and sh0 else None),
        ("Gross margin improved", (gp / rev > gp0 / rev0) if None not in (gp, rev, gp0, rev0) and rev and rev0 else None),
        ("Asset turnover improved", (rev / ta > rev0 / ta0) if rev and rev0 else None),
    ]
    known = [(name, bool(ok)) for name, ok in tests if ok is not None]
    return sum(ok for _, ok in known), known


def altman_z(d: CompanyData) -> float | None:
    """Original Altman Z for public manufacturers."""
    ta = d.latest("total_assets")
    ca, cl = d.latest("current_assets"), d.latest("current_liabilities")
    re, ebit = d.latest("retained_earnings"), d.latest("ebit")
    tl, rev, mcap = d.latest("total_liabilities"), d.latest("revenue"), d.market_cap
    if None in (ta, ca, cl, re, ebit, tl, rev, mcap) or not ta or not tl:
        return None
    return 1.2 * (ca - cl) / ta + 1.4 * re / ta + 3.3 * ebit / ta + 0.6 * mcap / tl + 1.0 * rev / ta


def analyze(d: CompanyData) -> Report:
    r = Report(
        key="forensic",
        title="Financial strength & accounting quality",
        philosophy=(
            "Munger's first rule is to avoid ruin, and the second is to avoid being fooled. "
            "This lens asks: can the company survive a bad stretch, and do the reported profits look "
            "like real cash? It uses well-tested academic scores rather than opinions."
        ),
    )
    cl = Checklist()

    f, tests = piotroski(d)
    if f is not None:
        r.metrics["Piotroski F-score"] = f"{f}/{len(tests)}"
        cl.check(None, weight=2.0, partial=f / len(tests) if tests else None)
        r.add(GOOD if f >= 7 else WARN if f >= 4 else BAD,
              f"Piotroski F-score {f}/{len(tests)} — {'improving fundamentals' if f >= 7 else 'mixed' if f >= 4 else 'deteriorating fundamentals'}.")
        failed = [name for name, ok in tests if not ok]
        if failed:
            r.add(INFO, "Failed F-score tests: " + "; ".join(failed) + ".")

    if d.is_financial:
        r.caveats.append("Altman Z and interest-coverage tests are designed for non-financial companies and were skipped.")
    else:
        z = altman_z(d)
        if z is not None:
            r.metrics["Altman Z"] = round(z, 2)
            cl.check(None, weight=2.0, partial=scale(z, 1.8, 3.0))
            r.add(GOOD if z >= 3 else WARN if z >= 1.8 else BAD,
                  f"Altman Z-score {fmt_num(z)} — {'safe zone' if z >= 3 else 'grey zone' if z >= 1.8 else 'distress zone (elevated bankruptcy risk)'}.")

        ebit, interest = d.latest("ebit"), d.latest("interest_expense")
        if ebit is not None and ebit <= 0 and interest:
            cl.check(False, weight=1.5)
            r.add(BAD, "Operating profit is negative — interest is being paid from cash reserves or new capital, not earnings.")
        elif ebit is not None and interest:
            cov = ebit / abs(interest)
            r.metrics["Interest coverage"] = round(cov, 1)
            cl.check(None, weight=1.5, partial=scale(cov, 2.0, 10.0))
            r.add(GOOD if cov >= 8 else WARN if cov >= 3 else BAD, f"EBIT covers interest {cov:.1f}×.")
        elif ebit is not None and ebit > 0:
            r.add(GOOD, "No meaningful interest expense reported.")
            cl.check(True, weight=1.5)

    # Sloan accrual ratio: earnings far above cash flow is the classic warning sign
    ni, cfo = d.latest("net_income"), d.latest("operating_cash_flow")
    ta, ta0 = d.latest("total_assets"), d.previous("total_assets")
    avg_ta = (ta + ta0) / 2 if ta and ta0 else ta
    accrual = safe_div((ni - cfo) if ni is not None and cfo is not None else None, avg_ta)
    if accrual is not None:
        r.metrics["Accrual ratio"] = accrual
        cl.check(None, weight=1.5, partial=scale(accrual, 0.10, -0.05))
        r.add(GOOD if accrual <= 0 else WARN if accrual <= 0.07 else BAD,
              f"Accrual ratio {fmt_pct(accrual)} — "
              + ("earnings are backed by cash." if accrual <= 0 else
                 "earnings modestly exceed cash flow." if accrual <= 0.07 else
                 "earnings well above cash flow; check receivables, inventory and capitalized costs."))

    # Liquidity runway for cash-burning companies
    fcf = d.fcf_series()
    cash = d.latest("cash")
    if len(fcf) and fcf.iloc[-1] < 0 and cash:
        runway = cash / abs(float(fcf.iloc[-1]))
        r.metrics["Cash runway (years)"] = round(runway, 1)
        cl.check(None, weight=1.5, partial=scale(runway, 0.5, 3.0))
        r.add(BAD if runway < 1.5 else WARN, f"Burning cash: about {runway:.1f} years of runway at last year's burn — dilution or debt likely before profitability.")

    r.score = cl.score
    s = r.score or 0
    r.verdict = (
        "Fortress: strong and clean financials" if s >= 75 else
        "Adequate financial strength" if s >= 50 else
        "Fragile: survival or accounting quality is a concern"
    )
    return r
