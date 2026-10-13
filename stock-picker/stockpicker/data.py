"""Market and fundamentals data, fetched from Yahoo Finance via yfinance.

Everything downstream works on `CompanyData`, so swapping the data source
(a paid API, SEC XBRL, a CSV) only means writing another loader that fills
the same fields.
"""

from __future__ import annotations

import math
import os
import pickle
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

CACHE_DIR = Path(os.environ.get("STOCKPICKER_CACHE", Path(__file__).resolve().parent.parent / ".cache"))
CACHE_TTL_SECONDS = 12 * 3600

# yfinance has renamed statement rows across versions; try each alias in order.
ALIASES: dict[str, tuple[str, ...]] = {
    "revenue": ("Total Revenue", "Operating Revenue", "Revenue"),
    "gross_profit": ("Gross Profit",),
    "operating_income": ("Operating Income", "Total Operating Income As Reported"),
    "ebit": ("EBIT", "Operating Income"),
    "ebitda": ("EBITDA", "Normalized EBITDA"),
    "net_income": ("Net Income", "Net Income Common Stockholders", "Net Income From Continuing Operation Net Minority Interest"),
    "eps_diluted": ("Diluted EPS", "Basic EPS"),
    "shares_diluted": ("Diluted Average Shares", "Basic Average Shares"),
    "interest_expense": ("Interest Expense", "Interest Expense Non Operating"),
    "pretax_income": ("Pretax Income",),
    "tax_provision": ("Tax Provision",),
    "rnd": ("Research And Development",),
    "total_assets": ("Total Assets",),
    "current_assets": ("Current Assets",),
    "current_liabilities": ("Current Liabilities",),
    "total_liabilities": ("Total Liabilities Net Minority Interest", "Total Liabilities"),
    "equity": ("Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"),
    "long_term_debt": ("Long Term Debt", "Long Term Debt And Capital Lease Obligation"),
    "total_debt": ("Total Debt",),
    "cash": ("Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"),
    "retained_earnings": ("Retained Earnings",),
    "shares_outstanding": ("Ordinary Shares Number", "Share Issued"),
    "goodwill": ("Goodwill And Other Intangible Assets", "Goodwill"),
    "operating_cash_flow": ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities"),
    "capex": ("Capital Expenditure", "Purchase Of PPE"),
    "free_cash_flow": ("Free Cash Flow",),
    "buybacks": ("Repurchase Of Capital Stock", "Common Stock Payments"),
    "dividends_paid": ("Cash Dividends Paid", "Common Stock Dividend Paid"),
    "sbc": ("Stock Based Compensation",),
    "depreciation": ("Depreciation And Amortization", "Depreciation Amortization Depletion", "Reconciled Depreciation"),
}

FINANCIAL_SECTORS = {"Financial Services"}


@dataclass
class CompanyData:
    ticker: str
    info: dict[str, Any] = field(default_factory=dict)
    income: pd.DataFrame = field(default_factory=pd.DataFrame)
    balance: pd.DataFrame = field(default_factory=pd.DataFrame)
    cashflow: pd.DataFrame = field(default_factory=pd.DataFrame)
    history: pd.DataFrame = field(default_factory=pd.DataFrame)  # daily OHLCV, oldest first
    dividends: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    fetched_at: float = field(default_factory=time.time)
    errors: list[str] = field(default_factory=list)

    # ---------- info helpers ----------
    def get(self, key: str, default: float | None = None) -> float | None:
        v = self.info.get(key)
        if v is None:
            return default
        try:
            f = float(v)
        except (TypeError, ValueError):
            return default
        return f if math.isfinite(f) else default

    @property
    def name(self) -> str:
        return self.info.get("longName") or self.info.get("shortName") or self.ticker

    @property
    def sector(self) -> str:
        return self.info.get("sector") or "Unknown"

    @property
    def industry(self) -> str:
        return self.info.get("industry") or "Unknown"

    @property
    def is_financial(self) -> bool:
        """Banks/insurers: current ratio, Altman Z and FCF models don't apply."""
        return self.sector in FINANCIAL_SECTORS

    @property
    def price(self) -> float | None:
        p = self.get("currentPrice") or self.get("regularMarketPrice") or self.get("previousClose")
        if p is None and not self.history.empty:
            p = float(self.history["Close"].iloc[-1])
        return p

    @property
    def shares(self) -> float | None:
        s = self.get("sharesOutstanding") or self.get("impliedSharesOutstanding")
        if s is None:
            ser = self.series("shares_outstanding")
            s = float(ser.iloc[-1]) if len(ser) else None
        return s

    @property
    def market_cap(self) -> float | None:
        mc = self.get("marketCap")
        if mc is None and self.price and self.shares:
            mc = self.price * self.shares
        return mc

    # ---------- statement helpers ----------
    def series(self, item: str) -> pd.Series:
        """Annual values for a line item, oldest -> newest, NaNs dropped."""
        df = self._frame_for(item)
        for name in ALIASES.get(item, (item,)):
            if df is not None and not df.empty and name in df.index:
                s = pd.to_numeric(df.loc[name], errors="coerce")
                if isinstance(s, pd.DataFrame):  # duplicate row labels
                    s = s.iloc[0]
                s = s.dropna()
                if len(s):
                    return s.sort_index()
        return pd.Series(dtype=float)

    def latest(self, item: str) -> float | None:
        s = self.series(item)
        return float(s.iloc[-1]) if len(s) else None

    def previous(self, item: str) -> float | None:
        s = self.series(item)
        return float(s.iloc[-2]) if len(s) >= 2 else None

    def _frame_for(self, item: str) -> pd.DataFrame | None:
        names = ALIASES.get(item, (item,))
        for df in (self.income, self.balance, self.cashflow):
            if df is not None and not df.empty and any(n in df.index for n in names):
                return df
        return None

    def fcf_series(self) -> pd.Series:
        fcf = self.series("free_cash_flow")
        if len(fcf):
            return fcf
        ocf, capex = self.series("operating_cash_flow"), self.series("capex")
        if len(ocf) and len(capex):
            return (ocf + capex).dropna()  # capex is reported negative
        return pd.Series(dtype=float)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _cache_path(ticker: str) -> Path:
    return CACHE_DIR / f"{ticker.upper().replace('/', '_')}.pkl"


def load(ticker: str, use_cache: bool = True, history_period: str = "5y") -> CompanyData:
    ticker = ticker.strip().upper()
    path = _cache_path(ticker)
    if use_cache and path.exists() and time.time() - path.stat().st_mtime < CACHE_TTL_SECONDS:
        try:
            with path.open("rb") as fh:
                return pickle.load(fh)
        except Exception:
            pass  # corrupt cache: refetch

    data = fetch_yfinance(ticker, history_period)
    if data.info or not data.history.empty:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with path.open("wb") as fh:
                pickle.dump(data, fh)
        except OSError:
            pass
    return data


def fetch_yfinance(ticker: str, history_period: str = "5y") -> CompanyData:
    import yfinance as yf  # imported lazily so tests run without network

    t = yf.Ticker(ticker)
    d = CompanyData(ticker=ticker)

    def attempt(label: str, fn):
        try:
            return fn()
        except Exception as exc:  # yfinance raises a zoo of exception types
            d.errors.append(f"{label}: {exc}")
            return None

    d.info = attempt("info", lambda: t.info) or {}
    for attr, label in (("income", "income_stmt"), ("balance", "balance_sheet"), ("cashflow", "cashflow")):
        df = attempt(label, lambda label=label: getattr(t, label))
        if isinstance(df, pd.DataFrame):
            setattr(d, attr, df)
    hist = attempt("history", lambda: t.history(period=history_period, auto_adjust=True))
    if isinstance(hist, pd.DataFrame) and not hist.empty:
        hist.index = pd.to_datetime(hist.index).tz_localize(None)
        d.history = hist
    divs = attempt("dividends", lambda: t.dividends)
    if isinstance(divs, pd.Series) and not divs.empty:
        divs.index = pd.to_datetime(divs.index).tz_localize(None)
        d.dividends = divs
    return d


def risk_free_rate(default: float = 0.043) -> float:
    """10-year US Treasury yield from ^TNX, falling back to `default`."""
    try:
        import yfinance as yf

        h = yf.Ticker("^TNX").history(period="5d")
        if not h.empty:
            v = float(h["Close"].iloc[-1]) / 100
            if 0.0 < v < 0.2:
                return v
    except Exception:
        pass
    return default


# ---------------------------------------------------------------------------
# Small numeric helpers shared by research modules
# ---------------------------------------------------------------------------

def cagr(series: pd.Series) -> float | None:
    """Compound annual growth between first and last value; None if undefined."""
    s = series.dropna()
    if len(s) < 2:
        return None
    first, last = float(s.iloc[0]), float(s.iloc[-1])
    years = (s.index[-1] - s.index[0]).days / 365.25 if isinstance(s.index, pd.DatetimeIndex) else len(s) - 1
    if years <= 0 or first <= 0 or last <= 0:
        return None
    return (last / first) ** (1 / years) - 1


def safe_div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0 or not math.isfinite(a) or not math.isfinite(b):
        return None
    return a / b


def stdev(values: pd.Series) -> float | None:
    v = values.dropna()
    return float(np.std(v, ddof=1)) if len(v) >= 2 else None
