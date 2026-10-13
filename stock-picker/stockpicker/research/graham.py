"""Benjamin Graham: intrinsic value and the defensive investor's checklist.

Sources: *The Intelligent Investor* ch. 14 (defensive investor criteria) and
the revised growth formula V = EPS x (8.5 + 2g) x 4.4 / Y.
"""

from __future__ import annotations

import math

from ..data import CompanyData, cagr, safe_div
from .base import BAD, GOOD, INFO, WARN, Checklist, Report, fmt_money, fmt_num, fmt_pct

# Graham's "adequate size" was $100M sales in 1971 dollars; ~$2B is a common
# modern restatement for inflation and market growth.
MIN_REVENUE = 2e9


def graham_number(eps: float | None, bvps: float | None) -> float | None:
    """sqrt(22.5 x EPS x BVPS): the most a defensive investor should pay (P/E 15 x P/B 1.5)."""
    if eps is None or bvps is None or eps <= 0 or bvps <= 0:
        return None
    return math.sqrt(22.5 * eps * bvps)


def graham_formula_value(eps: float | None, growth_pct: float, aaa_yield_pct: float) -> float | None:
    """Revised Graham formula. growth_pct and aaa_yield_pct are in percent (e.g. 7.0, 5.3)."""
    if eps is None or eps <= 0 or aaa_yield_pct <= 0:
        return None
    return eps * (8.5 + 2 * growth_pct) * 4.4 / aaa_yield_pct


def analyze(d: CompanyData, aaa_yield: float = 0.053) -> Report:
    r = Report(
        key="graham",
        title="Intrinsic value (Graham)",
        philosophy=(
            "Graham treats a stock as a fractional claim on a business and demands a margin of safety: "
            "buy only when price sits well below a conservative estimate of value, from a company "
            "strong enough to survive bad years. He cares about what the business *has* and has "
            "*proven* — not stories about the future."
        ),
    )
    cl = Checklist()
    price = d.price
    eps = d.get("trailingEps") or d.latest("eps_diluted")
    bvps = d.get("bookValue")
    if bvps is None:
        bvps = safe_div(d.latest("equity"), d.shares)

    # 1. Adequate size
    revenue = d.latest("revenue")
    if revenue is not None:
        ok = revenue >= MIN_REVENUE
        cl.check(ok)
        r.add(GOOD if ok else WARN, f"Size: revenue {fmt_money(revenue)} (Graham wants a large, established firm; ≥ {fmt_money(MIN_REVENUE)}).")

    # 2. Strong financial condition
    ca, cli = d.latest("current_assets"), d.latest("current_liabilities")
    current_ratio = safe_div(ca, cli)
    ltd = d.latest("long_term_debt") or 0.0
    nca = (ca - cli) if ca is not None and cli is not None else None
    if d.is_financial:
        r.caveats.append("Financial company: current-ratio and net-current-asset tests don't apply to banks/insurers and were skipped.")
    else:
        if current_ratio is not None:
            ok = current_ratio >= 2
            cl.check(ok)
            r.add(GOOD if ok else (WARN if current_ratio >= 1.2 else BAD),
                  f"Current ratio {fmt_num(current_ratio)} (Graham: ≥ 2.0).")
        if nca is not None:
            ok = ltd <= nca
            cl.check(ok)
            r.add(GOOD if ok else WARN,
                  f"Long-term debt {fmt_money(ltd)} vs net current assets {fmt_money(nca)} (Graham: debt should not exceed NCA).")

    # 3. Earnings stability
    ni = d.series("net_income")
    if len(ni):
        positive = int((ni > 0).sum())
        ok = positive == len(ni)
        cl.check(ok, weight=1.5)
        r.add(GOOD if ok else BAD, f"Earnings stability: profitable in {positive} of the last {len(ni)} reported years (Graham wanted 10 of 10).")
        if len(ni) < 10:
            r.caveats.append(f"Only {len(ni)} years of annual statements are available from the free feed; Graham's 10-year tests are approximated.")

    # 4. Dividend record
    if not d.dividends.empty:
        years_paid = d.dividends.groupby(d.dividends.index.year).sum()
        span = years_paid.index.max() - years_paid.index.min() + 1
        uninterrupted = len(years_paid) == span
        ok = uninterrupted and span >= 20
        cl.check(ok, partial=None if ok else min(1.0, len(years_paid) / 20) * (1.0 if uninterrupted else 0.5))
        r.add(GOOD if ok else (WARN if span >= 5 else INFO),
              f"Dividend record: paid in {len(years_paid)} calendar years since {years_paid.index.min()}"
              f"{'' if uninterrupted else ' (with gaps)'} (Graham: 20 uninterrupted years).")
    else:
        cl.check(False, weight=0.5)
        r.add(INFO, "No dividend history — fails Graham's dividend test (common for growth companies; not damning on its own).")

    # 5. Earnings growth
    eps_series = d.series("eps_diluted")
    eps_growth = cagr(eps_series) if len(eps_series) >= 3 else None
    if eps_growth is not None:
        ok = eps_growth >= 0.03  # ~33% over 10 years ≈ 2.9%/yr
        cl.check(ok)
        r.add(GOOD if ok else WARN, f"EPS growth {fmt_pct(eps_growth)}/yr over {len(eps_series)} years (Graham: ≥ ~3%/yr, i.e. +33% per decade).")

    # 6. Moderate P/E on average earnings
    avg_eps = float(eps_series.iloc[-3:].mean()) if len(eps_series) >= 3 else eps
    pe_avg = safe_div(price, avg_eps) if avg_eps and avg_eps > 0 else None
    if pe_avg is not None:
        ok = pe_avg <= 15
        cl.check(ok, weight=1.5, partial=None if ok else max(0.0, 1 - (pe_avg - 15) / 25))
        r.add(GOOD if ok else (WARN if pe_avg <= 25 else BAD), f"P/E on 3-yr average EPS: {fmt_num(pe_avg, 1)} (Graham: ≤ 15).")
    elif avg_eps is not None and avg_eps <= 0:
        cl.check(False, weight=1.5)
        r.add(BAD, "Average earnings are negative — no earnings-based value to anchor on.")

    # 7. Moderate P/B (or P/E x P/B ≤ 22.5)
    pb = safe_div(price, bvps) if bvps and bvps > 0 else None
    if pb is not None:
        pexpb = pe_avg * pb if pe_avg is not None else None
        ok = pb <= 1.5 or (pexpb is not None and pexpb <= 22.5)
        cl.check(ok, weight=1.5)
        r.add(GOOD if ok else WARN,
              f"P/B {fmt_num(pb)}; P/E × P/B {fmt_num(pexpb, 1)} (Graham: P/B ≤ 1.5 or product ≤ 22.5).")

    # --- Valuations ---
    gnum = graham_number(eps, bvps)
    growth_for_formula = max(0.0, min(15.0, 100 * (eps_growth if eps_growth is not None else (d.get("earningsGrowth") or 0.0))))
    gform = graham_formula_value(eps, growth_for_formula, aaa_yield * 100)

    # Net current asset value: Graham's "net-net" bargains trade below 2/3 of it
    tl = d.latest("total_liabilities")
    ncav_ps = safe_div((ca - tl) if ca is not None and tl is not None else None, d.shares)

    r.metrics.update({
        "Price": price,
        "Trailing EPS": eps,
        "Book value / share": bvps,
        "Graham number": gnum,
        "Graham formula value": gform,
        "Growth used in formula (%)": round(growth_for_formula, 1),
        "AAA yield used (%)": round(aaa_yield * 100, 2),
        "NCAV / share": ncav_ps,
        "Current ratio": current_ratio,
        "P/E (3y avg EPS)": pe_avg,
        "P/B": pb,
    })

    values = [v for v in (gnum, gform) if v]
    if values and price:
        # Use the more conservative of the two estimates — the margin-of-safety spirit.
        iv = min(values)
        mos = 1 - price / iv
        r.metrics["Conservative intrinsic value"] = iv
        r.metrics["Margin of safety"] = mos
        cl.check(mos >= 0.33, weight=2.0, partial=None if mos >= 0.33 else max(0.0, (mos + 0.5) / 0.83))
        if mos >= 0.33:
            r.add(GOOD, f"Price {fmt_money(price)} vs conservative value {fmt_money(iv)}: {fmt_pct(mos)} margin of safety (Graham liked ≥ 33%).")
        elif mos > 0:
            r.add(WARN, f"Price {fmt_money(price)} vs conservative value {fmt_money(iv)}: only {fmt_pct(mos)} margin of safety.")
        else:
            r.add(BAD, f"Price {fmt_money(price)} is {fmt_pct(-mos)} *above* the conservative Graham value {fmt_money(iv)}.")
    else:
        if eps is not None and eps <= 0:
            cl.check(False, weight=2.0)  # no earnings power = no Graham value at all
        r.add(INFO, "Graham number/formula undefined (needs positive EPS and book value).")

    if ncav_ps is not None and price and ncav_ps > 0 and price < ncav_ps * 2 / 3:
        r.add(GOOD, f"Net-net: price below 2/3 of NCAV/share ({fmt_money(ncav_ps)}) — a classic Graham cigar butt.")

    r.score = cl.score
    s = r.score or 0
    r.verdict = (
        "Passes as a defensive Graham buy" if s >= 75 else
        "Partially meets Graham's standards" if s >= 50 else
        "Fails Graham's defensive standards"
    )
    if cl.coverage < 0.6:
        r.caveats.append("Many inputs were missing; treat this score as low-confidence.")
    r.caveats.append(
        "Graham's formulas penalize asset-light compounders (low book value, no dividend). "
        "Munger's point: a great business at a fair price usually beats a fair business at a great price."
    )
    return r
