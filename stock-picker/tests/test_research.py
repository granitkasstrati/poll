import math

import pytest

from stockpicker import screener
from stockpicker.research import run_all
from stockpicker.research.future import dcf_per_share, implied_growth
from stockpicker.research.graham import graham_formula_value, graham_number

from .fixtures import make_company


def test_graham_number_matches_definition():
    assert graham_number(4.0, 25.0) == pytest.approx(math.sqrt(22.5 * 4 * 25))
    assert graham_number(-1.0, 25.0) is None


def test_graham_formula():
    # EPS 5, 5% growth, 4.4% yield -> 5 * 18.5 = 92.5
    assert graham_formula_value(5.0, 5.0, 4.4) == pytest.approx(92.5)


def test_reverse_dcf_inverts_dcf():
    v = dcf_per_share(5.0, 0.12, 0.09)
    assert implied_growth(v, 5.0, 0.09) == pytest.approx(0.12, abs=1e-6)


def test_dcf_zero_growth_close_to_perpetuity():
    # With growth == terminal the model is a plain Gordon growth perpetuity.
    v = dcf_per_share(1.0, 0.025, 0.09)
    assert v == pytest.approx(1.025 / (0.09 - 0.025), rel=1e-9)


def test_quality_company_scores_well():
    d = make_company(price=60.0)
    res = run_all(d)
    moat = res.reports["moat"]
    assert moat.score >= 70, moat.findings
    assert res.reports["forensic"].score >= 60
    assert res.munger.report.verdict
    assert len(res.munger.filters) == 4
    assert res.munger.inversion  # always at least the generic risks


def test_cash_burner_flagged():
    d = make_company(burn=True, growth=0.4, share_change=0.08, vol=0.05)
    res = run_all(d)
    assert res.reports["moat"].score < 50
    flags = " ".join(res.munger.inversion)
    assert "Owner earnings" in flags or "runway" in flags
    assert "Avoid" in res.munger.report.verdict or "Pass" in res.munger.report.verdict


def test_expensive_stock_has_negative_mos():
    cheap, dear = run_all(make_company(price=40.0)), run_all(make_company(price=900.0))
    assert cheap.reports["future"].metrics["Base-case margin of safety"] > dear.reports["future"].metrics["Base-case margin of safety"]
    assert dear.reports["future"].metrics["Base-case margin of safety"] < 0


def test_technical_plan_is_coherent():
    from stockpicker.research.technical import indicators, plan_trade

    d = make_company(trend=0.001)
    plan = plan_trade(indicators(d.history), "Pullback to 50-day in uptrend")
    assert plan.stop < plan.entry < plan.target
    assert plan.reward_risk > 0
    m = run_all(d).reports["technical"].metrics
    if "Entry" in m:  # only emitted when a setup exists
        assert m["Stop"] < m["Entry"] < m["Target"]


def test_summary_json_safe_and_screen_ranks():
    companies = {f"T{i}": make_company(ticker=f"T{i}", price=40 + 30 * i, seed=i, trend=0.0002 * i) for i in range(6)}
    df, failed = screener.screen(companies, loader=lambda t: companies[t], workers=2)
    assert not failed and len(df) == 6
    for fn in (screener.long_term, screener.swing, screener.risky):
        out = fn(df)
        assert set(out["Ticker"]).issubset(companies)


def test_missing_data_does_not_crash():
    from stockpicker.data import CompanyData

    res = run_all(CompanyData("EMPTY", info={"currentPrice": 10.0}))
    assert res.munger.report.verdict


def test_memo_payload_is_valid_json_without_internal_frames():
    import json

    from stockpicker.ai_memo import _payload

    j = json.loads(_payload(run_all(make_company())))
    assert set(j["lenses"]) == {"graham", "future", "moat", "forensic", "technical", "asymmetric"}
    assert not any(k.startswith("_") for lens in j["lenses"].values() for k in lens["metrics"])
