"""Synthetic CompanyData shaped like yfinance output, for offline tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stockpicker.data import CompanyData


def _frame(rows: dict[str, list[float]], years: list[int]) -> pd.DataFrame:
    # yfinance puts newest year first in columns; mimic that.
    cols = [pd.Timestamp(f"{y}-12-31") for y in years][::-1]
    return pd.DataFrame({k: v[::-1] for k, v in rows.items()}, index=cols).T


def make_company(
    ticker: str = "TEST",
    price: float = 100.0,
    revenue0: float = 10e9,
    growth: float = 0.08,
    gross_margin: float = 0.55,
    op_margin: float = 0.30,
    shares0: float = 1e9,
    share_change: float = -0.02,
    net_debt: float = 2e9,
    trend: float = 0.0006,
    vol: float = 0.015,
    seed: int = 1,
    sector: str = "Technology",
    burn: bool = False,
) -> CompanyData:
    years = [2021, 2022, 2023, 2024, 2025]
    rev = [revenue0 * (1 + growth) ** i for i in range(5)]
    gp = [r * gross_margin for r in rev]
    ebit = [r * (op_margin if not burn else -0.25) for r in rev]
    pretax = [e * 0.97 for e in ebit]
    tax = [p * 0.2 if p > 0 else 0 for p in pretax]
    ni = [p - t for p, t in zip(pretax, tax)]
    shares = [shares0 * (1 + share_change) ** i for i in range(5)]
    eps = [n / s for n, s in zip(ni, shares)]
    ocf = [n * 1.15 for n in ni]
    capex = [-r * 0.04 for r in rev]
    fcf = [o + c for o, c in zip(ocf, capex)]
    total_assets = [r * 1.2 for r in rev]
    equity = [r * 0.6 for r in rev]
    cash = [3e9] * 5
    debt = [net_debt + c for c in cash]

    income = _frame({
        "Total Revenue": rev, "Gross Profit": gp, "Operating Income": ebit, "EBIT": ebit,
        "Pretax Income": pretax, "Tax Provision": tax, "Net Income": ni, "Diluted EPS": eps,
        "Diluted Average Shares": shares, "Interest Expense": [1e8] * 5, "Research And Development": [r * 0.1 for r in rev],
        "EBITDA": [e + r * 0.05 for e, r in zip(ebit, rev)],
    }, years)
    balance = _frame({
        "Total Assets": total_assets, "Current Assets": [r * 0.5 for r in rev], "Current Liabilities": [r * 0.22 for r in rev],
        "Total Liabilities Net Minority Interest": [a - e for a, e in zip(total_assets, equity)],
        "Stockholders Equity": equity, "Long Term Debt": [d * 0.9 for d in debt], "Total Debt": debt,
        "Cash Cash Equivalents And Short Term Investments": cash, "Retained Earnings": [e * 0.7 for e in equity],
        "Ordinary Shares Number": shares,
    }, years)
    cashflow = _frame({
        "Operating Cash Flow": ocf, "Capital Expenditure": capex, "Free Cash Flow": fcf,
        "Stock Based Compensation": [r * 0.02 for r in rev], "Depreciation And Amortization": [r * 0.03 for r in rev],
    }, years)

    rng = np.random.default_rng(seed)
    n = 1260
    rets = rng.normal(trend, vol, n)
    close = price * np.exp(np.cumsum(rets) - np.sum(rets))  # ends exactly at `price`
    idx = pd.bdate_range(end="2026-10-09", periods=n)
    hist = pd.DataFrame({
        "Open": close * (1 - 0.002), "High": close * (1 + vol / 2), "Low": close * (1 - vol / 2),
        "Close": close, "Volume": rng.integers(5e6, 1e7, n).astype(float),
    }, index=idx)

    info = {
        "longName": f"{ticker} Corp", "sector": sector, "industry": "Software - Application",
        "currentPrice": price, "sharesOutstanding": shares[-1], "marketCap": price * shares[-1],
        "trailingEps": eps[-1], "forwardEps": eps[-1] * (1 + growth), "bookValue": equity[-1] / shares[-1],
        "returnOnEquity": ni[-1] / equity[-1] if ni[-1] > 0 else -0.2, "payoutRatio": 0.2,
        "heldPercentInsiders": 0.06, "targetMeanPrice": price * 1.1, "targetHighPrice": price * 1.4,
        "targetLowPrice": price * 0.8, "numberOfAnalystOpinions": 25, "recommendationKey": "buy",
        "revenueGrowth": growth, "beta": 1.1, "shortPercentOfFloat": 0.02,
    }
    divs = pd.Series(0.5, index=pd.date_range("2004-03-31", periods=88, freq="QE"))
    return CompanyData(ticker, info, income, balance, cashflow, hist, divs)
