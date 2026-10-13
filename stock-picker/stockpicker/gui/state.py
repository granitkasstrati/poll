"""Application-wide state shared by every page."""

from __future__ import annotations

import os
import re
import shlex
import threading
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, pyqtSignal

from .. import data as data_mod
from ..data import CompanyData
from ..research import Assumptions, Research, run_all


class AppState(QObject):
    assumptions_changed = pyqtSignal()
    watchlist_changed = pyqtSignal()
    open_ticker = pyqtSignal(str)       # any page can ask to show a company's research
    open_settings = pyqtSignal()
    status = pyqtSignal(str)            # transient status-bar message

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings()
        self._cache: dict[str, CompanyData] = {}
        self._lock = threading.Lock()

    # ---------------- assumptions (persisted) ----------------
    @property
    def assumptions(self) -> Assumptions:
        return Assumptions(
            discount_rate=float(self.settings.value("assumptions/discount_rate", 0.09)),
            aaa_yield=float(self.settings.value("assumptions/aaa_yield", 0.053)),
        )

    def set_assumptions(self, discount_rate: float, aaa_yield: float) -> None:
        old = self.assumptions
        self.settings.setValue("assumptions/discount_rate", discount_rate)
        self.settings.setValue("assumptions/aaa_yield", aaa_yield)
        if (old.discount_rate, old.aaa_yield) != (discount_rate, aaa_yield):
            self.assumptions_changed.emit()

    # ---------------- data & research (call from worker threads) ----------------
    def company(self, ticker: str, refresh: bool = False) -> CompanyData:
        ticker = ticker.strip().upper()
        with self._lock:
            d = None if refresh else self._cache.get(ticker)
        if d is None:
            d = data_mod.load(ticker, use_cache=not refresh)
            if d.price:
                with self._lock:
                    self._cache[ticker] = d
        return d

    def research(self, ticker: str, refresh: bool = False) -> Research:
        return run_all(self.company(ticker, refresh), self.assumptions)

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()
        for f in data_mod.CACHE_DIR.glob("*.pkl"):
            try:
                f.unlink()
            except OSError:
                pass

    # ---------------- API key ----------------
    @staticmethod
    def env_file() -> Path | None:
        """The installed app's settings file (sourced by the launcher), if installed."""
        data = os.environ.get("STOCKPICKER_DATA")
        return Path(data).parent / "env" if data else None

    @staticmethod
    def has_api_key() -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))

    def save_api_key(self, key: str) -> Path | None:
        """Use the key now, and persist it to the env file when installed. Returns the file written."""
        key = key.strip()
        if key:
            os.environ["ANTHROPIC_API_KEY"] = key
        else:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        path = self.env_file()
        if path is None:
            return None
        lines = path.read_text().splitlines() if path.exists() else []
        lines = [ln for ln in lines if not re.match(r"\s*(export\s+)?ANTHROPIC_API_KEY=", ln)]
        if key:
            lines.append(f"export ANTHROPIC_API_KEY={shlex.quote(key)}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n")
        path.chmod(0o600)
        return path
