"""Screen a universe of tickers and rank them into the three watchlists."""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd

from . import data as data_mod
from .research import Assumptions, run_all

SCREEN_FILE = data_mod.CACHE_DIR / "screen.json"


def screen(
    tickers: Iterable[str],
    assumptions: Assumptions | None = None,
    workers: int = 6,
    progress: Callable[[int, int, str], None] | None = None,
    loader: Callable[[str], data_mod.CompanyData] = data_mod.load,
    cancel: threading.Event | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Run all research lenses over `tickers`. Returns (summary table, failures).

    Setting `cancel` stops the screen early and returns what finished so far.
    """
    tickers = list(dict.fromkeys(t.strip().upper() for t in tickers if t.strip()))
    rows, failed = [], []

    def one(t: str):
        d = loader(t)
        if not d.price or d.history.empty:
            raise ValueError("no price data")
        return run_all(d, assumptions).summary()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(one, t): t for t in tickers}
        for i, fut in enumerate(as_completed(futs), 1):
            t = futs[fut]
            try:
                rows.append(fut.result())
            except Exception as exc:
                failed.append(f"{t}: {exc}")
            if progress:
                progress(i, len(tickers), t)
            if cancel is not None and cancel.is_set():
                for f in futs:
                    f.cancel()
                break
    return pd.DataFrame(rows), failed


def save(df: pd.DataFrame, path: Path = SCREEN_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"saved_at": time.time(), "rows": json.loads(df.to_json(orient="records"))}
    path.write_text(json.dumps(payload))


def load_saved(path: Path = SCREEN_FILE) -> tuple[pd.DataFrame, float | None]:
    if not path.exists():
        return pd.DataFrame(), None
    try:
        payload = json.loads(path.read_text())
        return pd.DataFrame(payload["rows"]), payload["saved_at"]
    except (ValueError, KeyError):
        return pd.DataFrame(), None


# ---------------------------------------------------------------------------
# Watchlist rankings
# ---------------------------------------------------------------------------

def _num(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(df.get(col), errors="coerce") if col in df else pd.Series(float("nan"), index=df.index)


def long_term(df: pd.DataFrame, top: int = 25) -> pd.DataFrame:
    """Wonderful businesses first; price decides whether it's 'buy zone' or 'wait'."""
    if df.empty:
        return df
    q, s, mos = _num(df, "Quality"), _num(df, "Strength"), _num(df, "Base MoS")
    out = df[(q >= 55) & (s.fillna(50) >= 45)].copy()
    out["Action"] = [
        "Research now — fair price" if m >= 0 else "Wait — price ahead of value" if m >= -0.3 else "Wait — far above value"
        for m in _num(out, "Base MoS").fillna(-1)
    ]
    return out.sort_values("Munger score", ascending=False).head(top)


def swing(df: pd.DataFrame, top: int = 25) -> pd.DataFrame:
    if df.empty:
        return df
    sc, rr = _num(df, "Swing score"), _num(df, "R/R")
    out = df[(sc >= 45) & (rr >= 1.8) & (df.get("Trend") != "Downtrend")].copy()
    return out.sort_values("Swing score", ascending=False).head(top)


def risky(df: pd.DataFrame, top: int = 25) -> pd.DataFrame:
    if df.empty:
        return df
    pr, a = _num(df, "Payoff ratio"), _num(df, "Asymmetry score")
    out = df[(pr >= 2.0) & (a >= 45)].copy()
    return out.sort_values("Asymmetry score", ascending=False).head(top)
