"""Your own saved tickers, with a note on why each is on the list."""

from __future__ import annotations

import json
import time
from pathlib import Path

from .data import CACHE_DIR

FILE = CACHE_DIR.parent / "my_watchlist.json"


def load(path: Path = FILE) -> dict[str, dict]:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def save(items: dict[str, dict], path: Path = FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2))


def add(ticker: str, note: str = "", path: Path = FILE) -> None:
    items = load(path)
    items[ticker.upper()] = {"note": note, "added": time.strftime("%Y-%m-%d")}
    save(items, path)


def remove(ticker: str, path: Path = FILE) -> None:
    items = load(path)
    items.pop(ticker.upper(), None)
    save(items, path)
