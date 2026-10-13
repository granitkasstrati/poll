"""Charlie Munger synthesis: four filters, inversion, bias check, lollapalooza.

This module doesn't fetch anything new. It reads the other lenses the way
Munger would read a stack of research: look for reasons to say no first,
then see whether several strong factors line up at once.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..data import CompanyData
from .base import BAD, GOOD, INFO, WARN, Report, fmt_pct, scale

TOO_HARD_INDUSTRIES = ("Biotechnology", "Shell Companies", "Conglomerates", "Insurance - Reinsurance")


@dataclass
class Filter:
    name: str
    question: str
    status: str
    evidence: list[str] = field(default_factory=list)


@dataclass
class MungerView:
    report: Report
    filters: list[Filter]
    inversion: list[str]
    bias_checks: list[str]
    lollapalooza: list[str]


def _status(score: float | None, good: float, ok: float) -> str:
    if score is None:
        return INFO
    return GOOD if score >= good else WARN if score >= ok else BAD


def synthesize(d: CompanyData, reports: dict[str, Report]) -> MungerView:
    moat, graham, future, forensic = (reports.get(k) for k in ("moat", "graham", "future", "forensic"))
    technical, asym = reports.get("technical"), reports.get("asymmetric")

    r = Report(
        key="munger",
        title="Munger synthesis",
        philosophy=(
            "\"All I want to know is where I'm going to die, so I'll never go there.\" Munger's process: "
            "(1) stay inside your circle of competence, (2) demand a durable competitive advantage, "
            "(3) insist on able and trustworthy management, (4) pay a sensible price. Invert — look for "
            "what would make this a mistake — and watch your own psychology as hard as the company's."
        ),
    )

    # ---------------- Four filters ----------------
    complex_biz = d.industry in TOO_HARD_INDUSTRIES or d.is_financial
    f1 = Filter(
        "Circle of competence", "Can you explain how this business makes money and what it looks like in 10 years?",
        WARN if complex_biz else INFO,
        [f"{d.name} — {d.sector} / {d.industry}."] + (
            ["Balance sheets in this industry are hard to judge from the outside: a candidate for Munger's 'too hard' pile."]
            if complex_biz else ["Only you can answer this. If you can't explain it to a 10-year-old, put it in the 'too hard' pile."]),
    )
    moat_ev = [f.text for f in moat.findings[:3]] if moat else []
    f2 = Filter("Durable competitive advantage", "Do high returns on capital persist, and why?",
                _status(moat.score if moat else None, 70, 50), moat_ev)

    mgmt_ev = [f.text for f in (moat.findings if moat else []) if any(k in f.text for k in ("share count", "Stock compensation", "Insiders"))]
    mgmt_scores = []
    if moat:
        sc = moat.metrics.get("Share count change / yr")
        if sc is not None:
            mgmt_scores.append(1.0 if sc <= 0 else 0.5 if sc <= 0.02 else 0.0)
        sbc = moat.metrics.get("SBC / FCF")
        if sbc is not None:
            mgmt_scores.append(1.0 if sbc <= 0.1 else 0.5 if sbc <= 0.3 else 0.0)
        ins = moat.metrics.get("Insider ownership")
        if ins is not None:
            mgmt_scores.append(min(1.0, ins / 0.05))
    if forensic:
        acc = forensic.metrics.get("Accrual ratio")
        if acc is not None:
            mgmt_scores.append(1.0 if acc <= 0 else 0.5 if acc <= 0.07 else 0.0)
            mgmt_ev.append(f"Accrual ratio {fmt_pct(acc)} (honest accounting shows cash ≥ earnings).")
    mgmt = 100 * sum(mgmt_scores) / len(mgmt_scores) if mgmt_scores else None
    f3 = Filter("Able & trustworthy management", "Do they allocate capital well and treat shareholders as partners?",
                _status(mgmt, 70, 45), mgmt_ev or ["Not enough data — read the proxy statement and several years of shareholder letters."])

    # Price is judged on valuation outputs only (not Graham's balance-sheet tests).
    # Graham's margin of safety gets a low weight and a wide band because his
    # formulas systematically undervalue asset-light compounders.
    fm = future.metrics if future else {}
    gm = graham.metrics if graham else {}
    hist_g = fm.get("Signal · Revenue CAGR (hist.)")
    implied = fm.get("Implied growth (reverse DCF)")
    pparts = [
        (2.0, scale(fm.get("Base-case margin of safety"), -0.4, 0.25)),
        (2.0, scale(implied - hist_g, 0.10, -0.05) if implied is not None and hist_g is not None else None),
        (1.0, scale(gm.get("Margin of safety"), -1.5, 0.33)),
    ]
    flags = " ".join(future.red_flags) if future else ""
    if "Owner earnings" in flags or "miracle" in flags:
        pparts.append((2.0, 0.0))  # nothing to anchor a price on, or priced for perfection
    pparts = [(w, v) for w, v in pparts if v is not None]
    price_score = round(100 * sum(w * v for w, v in pparts) / sum(w for w, _ in pparts), 1) if pparts else None
    price_ev = []
    if future and future.metrics.get("Implied growth (reverse DCF)") is not None:
        price_ev.append(f"Price implies {fmt_pct(future.metrics['Implied growth (reverse DCF)'])}/yr owner-earnings growth.")
    if future and future.metrics.get("Base-case margin of safety") is not None:
        price_ev.append(f"Base-case DCF margin of safety: {fmt_pct(future.metrics['Base-case margin of safety'])}.")
    if graham and graham.metrics.get("Margin of safety") is not None:
        price_ev.append(f"Margin of safety vs conservative Graham value: {fmt_pct(graham.metrics['Margin of safety'])}.")
    f4 = Filter("Sensible price", "Does the price leave room for being wrong?", _status(price_score, 55, 35), price_ev)

    filters = [f1, f2, f3, f4]

    # ---------------- Inversion: how does this go wrong? ----------------
    inversion: list[str] = []
    for rep in (forensic, moat, future, graham, asym):
        if rep:
            inversion.extend(rep.red_flags)
    if moat and (moat.metrics.get("Gross margin stdev") or 0) > 0.05:
        inversion.append("Margins swing a lot — a competitor or input-cost shock could hit earnings hard.")
    if future and (future.metrics.get("Implied growth (reverse DCF)") or 0) > 0.15:
        inversion.append("The price needs years of fast growth; a merely good outcome could still lose money (multiple compression).")
    if d.get("beta") and d.get("beta") > 1.5:
        inversion.append(f"Beta {d.get('beta'):.1f}: in a market sell-off this will likely fall much harder than the index.")
    inversion.append("Generic risks to research: customer concentration, regulation, technological disruption, key-person dependence, litigation.")
    # de-dup while keeping order
    seen: set[str] = set()
    inversion = [x for x in inversion if not (x in seen or seen.add(x))]

    # ---------------- Psychology of human misjudgment ----------------
    bias: list[str] = []
    h = d.history
    if h is not None and len(h) > 252:
        c = float(h["Close"].iloc[-1])
        hi52, c1y = float(h["High"].iloc[-252:].max()), float(h["Close"].iloc[-252])
        if c < hi52 * 0.6:
            bias.append(f"Anchoring: it's {1 - c / hi52:.0%} below its 52-week high. 'It used to be $X' says nothing about value — the old price may have been the mistake.")
        if c > c1y * 1.8:
            bias.append(f"Social proof / FOMO: up {c / c1y - 1:.0%} in a year. Are you buying the business or the chart everyone is talking about?")
    rec, n = d.info.get("recommendationKey"), d.get("numberOfAnalystOpinions") or 0
    if rec in ("strong_buy", "buy") and n >= 20:
        bias.append(f"Authority / social proof: {int(n)} analysts, consensus '{rec.replace('_', ' ')}'. When everyone agrees, it's usually in the price.")
    if rec in ("sell", "underperform"):
        bias.append("Contrast effect: Street consensus is negative. That can be opportunity — or they may simply be right. Know which.")
    bias.extend([
        "Commitment & consistency: if you already own it, would you buy it today at this price?",
        "Incentive-caused bias: who benefits from you believing the bullish story (management, promoters, analysts)?",
        "Confirmation bias: write down the strongest bear case before you look for reasons to buy.",
    ])

    # ---------------- Lollapalooza: several forces aligned ----------------
    lolla: list[str] = []
    if moat and (moat.metrics.get("ROIC (avg)") or 0) >= 0.15:
        lolla.append("High returns on capital")
    if future and (future.metrics.get("Base-case margin of safety") or -1) >= 0.15:
        lolla.append("Trading below base-case value")
    if moat and (moat.metrics.get("Share count change / yr") or 1) < -0.01:
        lolla.append("Shrinking share count")
    if moat and (moat.metrics.get("Insider ownership") or 0) >= 0.05:
        lolla.append("Owner-operators")
    if forensic and forensic.score is not None and forensic.score >= 75:
        lolla.append("Fortress financials")
    if future and (future.metrics.get("Implied growth (reverse DCF)") is not None) and (
        future.metrics["Implied growth (reverse DCF)"] <= max(0.0, (future.metrics.get("Signal · Revenue CAGR (hist.)") or 0.0))
    ):
        lolla.append("Low expectations priced in")

    # ---------------- Score & verdict ----------------
    weights = {"moat": 0.35, "price": 0.25, "forensic": 0.20, "mgmt": 0.20}
    parts = {
        "moat": moat.score if moat else None,
        "price": price_score,
        "forensic": forensic.score if forensic else None,
        "mgmt": mgmt,
    }
    known = {k: v for k, v in parts.items() if v is not None}
    score = round(sum(weights[k] * v for k, v in known.items()) / sum(weights[k] for k in known), 1) if known else None
    serious = [x for x in (forensic.red_flags if forensic else []) if "distress" in x or "runway" in x]

    if serious:
        verdict = "Avoid — survival risk (invert: where would we die? here)"
    elif complex_biz and (moat is None or (moat.score or 0) < 70):
        verdict = "Too-hard pile — hard to judge from outside; pass unless it's in your circle of competence"
    elif f2.status == GOOD and f4.status == GOOD:
        verdict = "Wonderful business at a sensible price — worth deep research"
    elif f2.status == GOOD:
        verdict = "Wonderful business, price not compelling — put on watchlist, wait for Mr. Market"
    elif f4.status == GOOD:
        verdict = "Cheap, but not wonderful — Graham might buy; Munger usually passes"
    else:
        verdict = "Pass — neither a wonderful business nor a bargain"

    r.score = score
    r.verdict = verdict
    r.metrics.update({"Management score": mgmt, "Price score": price_score, "Lollapalooza factors": len(lolla)})
    for f in filters:
        r.add(f.status, f"{f.name}: {f.question}")
    if len(lolla) >= 3:
        r.add(GOOD, "Lollapalooza: " + ", ".join(lolla) + " — several forces pushing the same way.")
    if technical and technical.score is not None:
        r.add(INFO, f"Timing note (swing lens): {technical.verdict}. Munger ignored timing; a long-term buyer can too, but buying into strength is cheaper on the nerves.")
    r.caveats.append("A checklist reduces errors; it doesn't replace reading the 10-K, the proxy, and the last five shareholder letters.")
    return MungerView(r, filters, inversion, bias, lolla)
