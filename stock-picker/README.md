# Munger Lens: a stock research companion

A stock research app that runs each company through several independent research lenses. It then pulls them together the way Charlie Munger would: invert first, run the four filters, check your own psychology, and look for lollapalooza effects.

It comes in two front ends that share the same analysis engine (`stockpicker/`):

- **Native desktop app.** A real Qt (PyQt6) application with native widgets and charts. It has no web server and no browser, and it follows your desktop theme.
- **Web version.** The original Streamlit app, which runs in your browser.

> **This is a research aid, not advice.** It works from free Yahoo Finance data, which has gaps and errors, and from simple, transparent models. Use it to decide *what* to research, then read the filings.

## Install on Linux (CachyOS, Arch, other distros)

```bash
cd stock-picker
./install.sh
```

Then open **Munger Lens** from your app menu. You can also run it from a terminal:

| Command | What it does |
|---|---|
| `munger-lens` | Opens the native app. |
| `munger-lens COST` | Opens straight to a company. |
| `munger-lens --web` | Opens the web version in your browser. It's also in the menu entry's right-click actions. |

### Matching your desktop

- **CachyOS / Arch:** the installer offers to install your distro's `python-pyqt6` (`sudo pacman -S python-pyqt6`; it's the only step that asks for sudo). With it, the app runs on your system Qt, so the Breeze style, your Plasma color scheme and accent color, fonts and icons all apply natively. It also works on Wayland, with its own taskbar icon.
- **Without the system package,** the app uses pip's PyQt6. It still reads your Plasma color scheme, font and icon theme from `~/.config/kdeglobals`, so colors and icons match, but the widget shapes use Qt's Fusion style instead of Breeze.
- **On other desktops,** it follows your system's light/dark preference.

### Where things go (no sudo needed)

| Path | What's there |
|---|---|
| `~/.local/share/munger-lens/app`, `venv` | The app and its private Python environment. Both are replaced when you upgrade. |
| `~/.local/share/munger-lens/data` | Your watchlist. |
| `~/.local/share/munger-lens/env` | Your Anthropic API key, for Claude memos. Set it from **Settings → Configure Munger Lens**. |
| `~/.config/munger-lens/` | Window layout, valuation assumptions and checklist answers. |
| `~/.cache/munger-lens` | The market-data cache. |

- **Upgrade:** pull the latest code and run `./install.sh` again. Your watchlist and settings are kept.
- **Remove:** run `./uninstall.sh`. Add `--purge` to also delete your data and settings.

**Needs:** Python 3.10+ with venv (`sudo apt install python3-venv` on Debian/Ubuntu). On Debian/Ubuntu, the system PyQt6 also needs `pyqt6-dev-tools`, which provides `PyQt6.uic` for the charts; without it, the installer uses pip's PyQt6.

## Run from source (development)

```bash
cd stock-picker
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-desktop.txt -r requirements-pyqt.txt
python -m stockpicker.gui       # native app
streamlit run app.py            # web version
```

To get optional Claude-written memos, export `ANTHROPIC_API_KEY` first, or enter it in the native app's Settings.

**Keyboard shortcuts** in the native app:

| Keys | Action |
|---|---|
| Ctrl+L | Jump to the ticker field |
| F5 | Refresh data |
| Ctrl+1 to Ctrl+4 | Switch pages |
| Ctrl+Shift+, | Settings |
| Ctrl+Q | Quit |

## What it does

### Research a company: one tab per lens

| Tab | Question it answers | Under the hood |
|---|---|---|
| 🧭 **Munger synthesis** | Should this go to deep research, onto the watchlist, or into the too-hard pile? | Four filters (circle of competence, moat, management, price). An **inversion** list of everything that could go wrong. A **misjudgment check** tailored to the stock (anchoring, social proof, commitment bias). **Lollapalooza** detection. |
| 📘 **Graham value** | Is it cheap relative to *proven* earnings and assets? | Defensive-investor checklist, Graham number √(22.5·EPS·BVPS), revised formula EPS·(8.5+2g)·4.4/Y, NCAV net-net test, margin of safety |
| 🔭 **Future & expectations** | What growth is already priced in, and is that bar low or heroic? | Revenue and FCF CAGR, margin trend, R&D and capex reinvestment, ROE×retention, bear/base/bull **DCF on owner earnings** (FCF − SBC), **reverse DCF** |
| 🏰 **Moat & management** | Is it a wonderful business run by owner-minded people? | ROIC level and persistence, gross-margin stability, cash conversion, buybacks vs dilution, SBC/FCF, insider ownership, net debt/EBITDA |
| 🛡️ **Financial strength** | Can it survive a bad stretch? Are the profits real? | Piotroski F-score, Altman Z, interest coverage, Sloan accrual ratio, cash runway |
| 📈 **Swing setup** | Is there a low-risk entry in the coming days or weeks? | 20/50/200-day averages, RSI, MACD, ATR, Bollinger squeeze, volume. Setup detection with an entry, stop, target and R:R plan. |
| 🎲 **Asymmetric bet** | If I'm right, how much do I make, and how much do I lose if I'm wrong? What kills it? | Bull/bear anchors (analyst range, DCF scenarios, 52-week range, book value), volatility, short interest, runway, dilution |
| 🤖 **Claude memo** | What can't the numbers show? | Claude, with web search, reads the computed research and writes a sourced, Munger-style memo: thesis, moat, incentives, inversion, verdict, what to verify next |

### Watchlists: stocks to watch

The screen runs the same lenses across about 190 tickers. You can edit the lists in `stockpicker/universe.py` or add tickers in the UI. Results are ranked into three tabs:

- **Long-term investments.** Quality ≥ 55 and a sound balance sheet, ranked by Munger score. Each row is tagged *Research now* (fair price) or *Wait* (price ahead of value).
- **Swing trades.** Active setups in stocks that are not in a downtrend, with R:R ≥ 1.8.
- **High risk / high reward.** Payoff ratio ≥ 2:1, with the score cut for each wipe-out risk (short runway, heavy debt, serial dilution).

Click a row to open that company's full research.

### My watchlist

Save tickers along with your thesis, then see their current scores at a glance.

## Assumptions you control (sidebar)

- **Discount rate** (default 9%): your hurdle rate for the DCFs.
- **AAA corporate yield** (default 5.3%): Graham's *Y*. Check the current Moody's Aaa yield (FRED series `AAA`) and set it here.

## Known limitations

- The free feed gives about 4–5 years of annual statements, so Graham's 10-year tests are approximations.
- Banks and insurers break the FCF, current-ratio and Altman models. Those tests are skipped and flagged.
- Scores are checklists. Missing inputs are skipped rather than counted as failures, so read the caveats under each lens.
- Yahoo rate-limits heavy use. Data is cached for 12 hours per ticker in `.cache/`.

## Layout

```
app.py                      web UI (Streamlit)
stockpicker/gui/            native desktop UI (PyQt6 + pyqtgraph); theme.py matches your desktop
stockpicker/data.py         yfinance loader, disk cache, statement helpers
stockpicker/research/       one module per lens + munger.py synthesis
stockpicker/screener.py     universe screening and watchlist rankings
stockpicker/ai_memo.py      optional Claude memo (streaming, web search)
desktop/web_launcher.py     `munger-lens --web`: serves the web UI and opens your browser
install.sh / uninstall.sh   per-user install (app menu entry, icon, launcher)
tests/                      offline tests on synthetic yfinance-shaped data
```

Run the tests with `python -m pytest -q`. The GUI tests run offscreen, and they're skipped when PyQt6 isn't installed.
