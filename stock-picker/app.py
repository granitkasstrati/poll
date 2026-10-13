"""Munger Lens — a stock research companion.

Run:  streamlit run app.py
"""

from __future__ import annotations

import datetime as dt
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from stockpicker import data as data_mod
from stockpicker import screener, universe, watchlist
from stockpicker.research import Assumptions, Research, run_all
from stockpicker.research.base import BAD, GOOD, INFO, WARN, Report, fmt_money, fmt_pct

st.set_page_config(page_title="Munger Lens", page_icon="🧭", layout="wide")

# Chart palette (dark mode): categorical slots 1-3, status colors, chrome.
C_SERIES = ["#3987e5", "#d95926", "#199e70"]
C_GOOD, C_CRIT = "#0ca30c", "#d03b3b"
C_SURFACE, C_GRID, C_AXIS, C_MUTED, C_INK = "#1a1a19", "#2c2c2a", "#383835", "#898781", "#f0efec"
ICON = {GOOD: "✅", WARN: "⚠️", BAD: "⛔", INFO: "ℹ️"}

PAGES = ["Research a company", "Watchlists", "My watchlist", "How it thinks"]


# ---------------------------------------------------------------------------
# State & cached loaders
# ---------------------------------------------------------------------------

if "goto" in st.session_state:  # navigation requested by a button on the previous run
    st.session_state["page"] = st.session_state.pop("goto")
if "goto_ticker" in st.session_state:  # must be set before the ticker widget is created
    st.session_state["ticker"] = st.session_state.pop("goto_ticker")
st.session_state.setdefault("page", PAGES[0])
st.session_state.setdefault("ticker", "")


@st.cache_data(ttl=3600, show_spinner=False)
def cached_rf() -> float:
    return data_mod.risk_free_rate()


@st.cache_resource(ttl=3600, show_spinner=False)
def cached_research(ticker: str, discount: float, aaa: float) -> Research:
    return run_all(data_mod.load(ticker), Assumptions(discount_rate=discount, aaa_yield=aaa))


def open_research(ticker: str) -> None:
    st.session_state["goto_ticker"] = ticker
    st.session_state["goto"] = PAGES[0]
    st.rerun()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🧭 Munger Lens")
    st.caption("A research companion, not an oracle.")
    page = st.radio("Go to", PAGES, key="page", label_visibility="collapsed")
    st.divider()
    st.subheader("Assumptions")
    rf = cached_rf()
    discount = st.slider(
        "Discount rate (DCF)", 0.06, 0.14, 0.09, 0.005, format="%.3f",
        help=f"Your required annual return. 10-yr Treasury is ~{rf:.2%}; 9–10% is a common hurdle for equities.",
    )
    aaa = st.slider(
        "AAA corporate bond yield (Graham formula)", 0.03, 0.08, 0.053, 0.001, format="%.3f",
        help="Graham's Y. Check the current Moody's Aaa yield (FRED series AAA) and set it here.",
    )
    st.divider()
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    if has_key:
        st.caption("🤖 Claude memo: enabled")
    elif os.environ.get("STOCKPICKER_DATA"):  # installed desktop app: settings live in the env file
        env_file = os.path.join(os.path.dirname(os.environ["STOCKPICKER_DATA"]), "env")
        st.caption(f"🤖 Claude memo: add ANTHROPIC_API_KEY to `{env_file}` and restart to enable")
    else:
        st.caption("🤖 Claude memo: set ANTHROPIC_API_KEY to enable")
    st.caption("Data: Yahoo Finance via yfinance (cached 12h). Free data has gaps and errors — verify in filings.")


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def score_label(score: float | None) -> str:
    return "n/a" if score is None else f"{score:.0f}/100"


def render_findings(rep: Report) -> None:
    for f in rep.findings:
        st.markdown(f"{ICON.get(f.status, '•')} {f.text}")


def render_metrics_table(metrics: dict) -> None:
    rows = []
    for k, v in metrics.items():
        if k.startswith("_") or isinstance(v, (dict, pd.DataFrame)):
            continue
        if isinstance(v, float):
            pctish = any(s in k.lower() for s in ("margin", "growth", "roic", "roe", "yield", "rate", "ownership",
                                                 "return", "volatility", "drawdown", "upside", "downside", "from 52w",
                                                 "% of", "/ revenue", "change / yr", "accrual", "sbc / fcf", "short %",
                                                 "fcf / net"))
            if "(%)" in k or "/Downside" in k:
                pctish = False
            v = fmt_pct(v) if pctish else (fmt_money(v) if abs(v) >= 1e6 or any(s in k for s in ("Price", "value", "Value", "share", "Entry", "Stop", "Target", "Close", "target", "Bull", "Bear", "cap")) else f"{v:,.2f}")
        rows.append({"Metric": k, "Value": "n/a" if v is None else str(v)})
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def render_lens(rep: Report) -> None:
    c1, c2 = st.columns([1, 3])
    c1.metric("Score", score_label(rep.score))
    c2.markdown(f"#### {rep.verdict or '—'}")
    with st.expander("How this lens thinks", expanded=False):
        st.write(rep.philosophy)
    render_findings(rep)
    with st.expander("All metrics"):
        render_metrics_table(rep.metrics)
    for c in rep.caveats:
        st.caption(f"Caveat: {c}")


def _layout(fig: go.Figure, height: int, title: str) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(color=C_INK, size=14)),
        height=height, margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor=C_SURFACE, plot_bgcolor=C_SURFACE, font=dict(color=C_MUTED),
        hovermode="x unified", legend=dict(orientation="h", y=1.02, x=1, xanchor="right", yanchor="bottom", font=dict(color=C_INK)),
    )
    fig.update_xaxes(gridcolor=C_GRID, linecolor=C_AXIS, showspikes=True, spikecolor=C_MUTED, spikethickness=1)
    fig.update_yaxes(gridcolor=C_GRID, linecolor=C_AXIS, zeroline=False)
    return fig


def price_chart(rep: Report, days: int = 380) -> go.Figure | None:
    ind = rep.metrics.get("_indicators")
    if ind is None:
        return None
    ind = ind.iloc[-days:]
    fig = go.Figure()
    for name, col, color in (("Close", "Close", C_SERIES[0]), ("50-day avg", "SMA50", C_SERIES[1]), ("200-day avg", "SMA200", C_SERIES[2])):
        fig.add_trace(go.Scatter(x=ind.index, y=ind[col], name=name, line=dict(color=color, width=2),
                                 hovertemplate="%{y:$,.2f}"))
    m = rep.metrics
    if "Stop" in m:
        for label, val, color in (("Stop", m["Stop"], C_CRIT), ("Target", m["Target"], C_GOOD)):
            fig.add_hline(y=val, line=dict(color=color, width=1, dash="dash"),
                          annotation=dict(text=f"{label} {fmt_money(val)}", font=dict(color=C_INK), xanchor="left"),
                          annotation_position="right")
    return _layout(fig, 380, "Price with trend averages")


def rsi_chart(rep: Report, days: int = 380) -> go.Figure | None:
    ind = rep.metrics.get("_indicators")
    if ind is None:
        return None
    ind = ind.iloc[-days:]
    fig = go.Figure(go.Scatter(x=ind.index, y=ind["RSI"], name="RSI(14)", line=dict(color=C_SERIES[0], width=2), hovertemplate="%{y:.0f}"))
    for lvl, txt in ((70, "overbought 70"), (30, "oversold 30")):
        fig.add_hline(y=lvl, line=dict(color=C_AXIS, width=1, dash="dot"), annotation=dict(text=txt, font=dict(color=C_MUTED)))
    fig.update_yaxes(range=[0, 100])
    return _layout(fig, 200, "RSI(14) momentum")


def dcf_chart(rep: Report, price: float | None) -> go.Figure | None:
    dcf = rep.metrics.get("DCF")
    if not dcf or not price:
        return None
    names = list(dcf.keys())
    vals = [dcf[k]["value"] for k in names]
    labels = [f"{k} ({fmt_pct(dcf[k]['growth'])} growth)" for k in names]
    fig = go.Figure(go.Bar(
        y=labels, x=vals, orientation="h", marker=dict(color=C_SERIES[0], cornerradius=4),
        text=[fmt_money(v) for v in vals], textposition="outside", textfont=dict(color=C_INK),
        hovertemplate="%{y}: %{x:$,.2f}<extra></extra>", name="DCF value / share",
    ))
    fig.add_vline(x=price, line=dict(color=C_INK, width=1, dash="dash"), annotation_position="bottom right",
                  annotation=dict(text=f"Price {fmt_money(price)}", font=dict(color=C_INK), yshift=-18))
    fig = _layout(fig, 220, "DCF value per share by scenario vs. today's price")
    fig.update_layout(hovermode="closest", showlegend=False, bargap=0.45)
    fig.update_xaxes(range=[0, max(vals + [price]) * 1.25], showspikes=False)
    return fig


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def page_research() -> None:
    st.header("Research a company")
    c1, c2, c3 = st.columns([2, 1, 1])
    ticker = c1.text_input("Ticker", key="ticker", placeholder="e.g. COST, MSFT, BRK-B").strip().upper()
    c2.write("")
    c2.write("")
    refresh = c2.button("Refresh data", help="Bypass the 12-hour cache")
    if not ticker:
        st.info("Enter a ticker to generate the full set of research reports.")
        return
    if refresh:
        data_mod.load(ticker, use_cache=False)
        cached_research.clear()

    with st.spinner(f"Pulling filings and prices for {ticker}…"):
        res = cached_research(ticker, discount, aaa)
    d = res.data
    if not d.price:
        st.error(f"No data for {ticker}. Check the symbol (Yahoo format, e.g. BRK-B, RY.TO, SAP.DE).")
        if d.errors:
            st.caption("; ".join(d.errors[:3]))
        return

    c3.write("")
    c3.write("")
    on_list = ticker in watchlist.load()
    if c3.button("★ Remove from my watchlist" if on_list else "☆ Add to my watchlist"):
        (watchlist.remove if on_list else watchlist.add)(ticker)
        st.rerun()

    mv = res.munger
    st.subheader(f"{d.name} ({d.ticker})")
    st.caption(f"{d.sector} · {d.industry} · data as of {dt.datetime.fromtimestamp(d.fetched_at):%Y-%m-%d %H:%M}")
    m = st.columns(5)
    m[0].metric("Price", fmt_money(d.price))
    m[1].metric("Market cap", fmt_money(d.market_cap))
    m[2].metric("Munger score", score_label(mv.report.score))
    m[3].metric("Quality", score_label(res.reports["moat"].score))
    m[4].metric("Price score", score_label(mv.report.metrics.get("Price score")))
    st.markdown(f"### {mv.report.verdict}")

    tabs = st.tabs(["🧭 Munger synthesis", "📘 Graham value", "🔭 Future & expectations", "🏰 Moat & management",
                    "🛡️ Financial strength", "📈 Swing setup", "🎲 Asymmetric bet", "🤖 Claude memo", "📄 Business"])

    with tabs[0]:
        with st.expander("How Munger thinks", expanded=False):
            st.write(mv.report.philosophy)
        st.markdown("#### The four filters")
        for f in mv.filters:
            with st.container(border=True):
                st.markdown(f"**{ICON[f.status]} {f.name}** — *{f.question}*")
                for e in f.evidence:
                    st.markdown(f"- {e}")
        left, right = st.columns(2)
        with left:
            st.markdown("#### Invert, always invert")
            st.caption("How could this investment fail?")
            for x in mv.inversion:
                st.markdown(f"- {x}")
        with right:
            st.markdown("#### Check your own psychology")
            for b in mv.bias_checks:
                st.markdown(f"- {b}")
        if mv.lollapalooza:
            st.markdown("#### Forces in your favour")
            st.markdown(" · ".join(f"`{x}`" for x in mv.lollapalooza)
                        + ("  \n**Lollapalooza** — several factors aligned." if len(mv.lollapalooza) >= 3 else ""))
        st.markdown("#### Lens scorecard")
        rows = [{"Lens": r.title, "Score": r.score, "Verdict": r.verdict} for r in res.reports.values()]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     column_config={"Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.0f")})
        for c in mv.report.caveats:
            st.caption(c)

    with tabs[1]:
        render_lens(res.reports["graham"])

    with tabs[2]:
        rep = res.reports["future"]
        fig = dcf_chart(rep, d.price)
        if fig:
            st.plotly_chart(fig, width="stretch")
        render_lens(rep)

    with tabs[3]:
        render_lens(res.reports["moat"])
        st.markdown("**Circle-of-competence check (answer honestly):**")
        st.checkbox("I can explain how this company makes money in two sentences.", key=f"coc1_{ticker}")
        st.checkbox("I can name the moat and what would destroy it.", key=f"coc2_{ticker}")
        st.checkbox("I know roughly what this business looks like in 10 years.", key=f"coc3_{ticker}")
        st.checkbox("I've read the latest 10-K and the last shareholder letter.", key=f"coc4_{ticker}")

    with tabs[4]:
        render_lens(res.reports["forensic"])

    with tabs[5]:
        rep = res.reports["technical"]
        fig = price_chart(rep)
        if fig:
            st.plotly_chart(fig, width="stretch")
            st.plotly_chart(rsi_chart(rep), width="stretch")
        render_lens(rep)

    with tabs[6]:
        render_lens(res.reports["asymmetric"])

    with tabs[7]:
        render_memo(res)

    with tabs[8]:
        st.write(d.info.get("longBusinessSummary") or "No description available.")
        if d.info.get("website"):
            st.markdown(f"[Company website]({d.info['website']})")
        st.markdown(f"[SEC filings (EDGAR)](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={d.ticker}&type=10-K)")
        if d.errors:
            with st.expander("Data warnings"):
                for e in d.errors:
                    st.caption(e)


def render_memo(res: Research) -> None:
    st.markdown(
        "Claude reads the computed research above, searches the web for recent news, competitive dynamics and "
        "management's record, and writes a Munger-style memo. It cites sources; check them."
    )
    key = f"memo_{res.data.ticker}"
    effort = st.select_slider("Depth", ["low", "medium", "high", "xhigh"], value="high",
                              help="Higher = more searching and reasoning, slower and costlier.")
    if st.button("Write memo", type="primary"):
        try:
            from stockpicker.ai_memo import stream_memo
            import anthropic
        except ImportError:
            st.error("Install the SDK first: pip install anthropic")
            return
        try:
            st.session_state[key] = st.write_stream(stream_memo(res, effort=effort))
        except anthropic.AuthenticationError:
            st.error("No valid credentials. Set ANTHROPIC_API_KEY (or run `ant auth login`) and restart.")
        except anthropic.RateLimitError:
            st.error("Rate limited by the API — try again in a minute.")
        except anthropic.APIStatusError as e:
            st.error(f"API error {e.status_code}: {e.message}")
        except anthropic.APIConnectionError:
            st.error("Couldn't reach the Anthropic API. Check your connection.")
    elif key in st.session_state:
        st.markdown(st.session_state[key])


TABLE_COLS = {
    "long": ["Ticker", "Name", "Price", "Munger score", "Quality", "Strength", "ROIC", "Base MoS", "Implied growth", "Action", "Munger verdict"],
    "swing": ["Ticker", "Name", "Price", "Swing score", "Setup", "Trend", "RSI", "Entry", "Stop", "Target", "R/R"],
    "risky": ["Ticker", "Name", "Price", "Market cap", "Asymmetry score", "Upside", "Downside", "Payoff ratio", "Volatility", "Short % float", "Strength"],
}

COL_CFG = {
    "Price": st.column_config.NumberColumn(format="dollar"),
    "Entry": st.column_config.NumberColumn(format="dollar"),
    "Stop": st.column_config.NumberColumn(format="dollar"),
    "Target": st.column_config.NumberColumn(format="dollar"),
    "Market cap": st.column_config.NumberColumn(format="compact"),
    "ROIC": st.column_config.NumberColumn(format="percent"),
    "Base MoS": st.column_config.NumberColumn("Margin of safety", format="percent", help="vs base-case DCF"),
    "Implied growth": st.column_config.NumberColumn(format="percent", help="Growth the price implies (reverse DCF)"),
    "Upside": st.column_config.NumberColumn(format="percent"),
    "Downside": st.column_config.NumberColumn(format="percent"),
    "Volatility": st.column_config.NumberColumn(format="percent"),
    "Short % float": st.column_config.NumberColumn(format="percent"),
    "Payoff ratio": st.column_config.NumberColumn(format="%.1f : 1"),
    "R/R": st.column_config.NumberColumn(format="%.1f"),
    **{c: st.column_config.ProgressColumn(c, min_value=0, max_value=100, format="%.0f")
       for c in ("Munger score", "Quality", "Strength", "Swing score", "Asymmetry score")},
}


def show_table(df: pd.DataFrame, kind: str, empty_msg: str) -> None:
    if df.empty:
        st.info(empty_msg)
        return
    cols = [c for c in TABLE_COLS[kind] if c in df.columns]
    event = st.dataframe(df[cols], hide_index=True, width="stretch", column_config=COL_CFG,
                         on_select="rerun", selection_mode="single-row", key=f"tbl_{kind}")
    st.caption("Select a row to open its full research.")
    sel = event.selection.rows if event and event.selection else []
    if sel:
        open_research(df.iloc[sel[0]]["Ticker"])


def page_watchlists() -> None:
    st.header("Stocks to watch")
    st.caption("Ranked by the same research lenses, run over a screening universe. A starting point for research — not a buy list.")

    with st.expander("Screening universe", expanded=False):
        groups = st.multiselect("Lists", ["Quality compounders", "Swing-trading liquids", "Speculative"],
                                default=["Quality compounders", "Swing-trading liquids", "Speculative"])
        extra = st.text_input("Extra tickers (comma-separated)", placeholder="e.g. RACE, NVO, SAP.DE")
        include_mine = st.checkbox("Include my watchlist", value=True)
    tickers: list[str] = []
    for g, lst in (("Quality compounders", universe.QUALITY), ("Swing-trading liquids", universe.SWING), ("Speculative", universe.SPECULATIVE)):
        if g in groups:
            tickers += lst
    tickers += [t.strip().upper() for t in extra.split(",") if t.strip()]
    if include_mine:
        tickers += list(watchlist.load())
    tickers = list(dict.fromkeys(tickers))

    df, saved_at = screener.load_saved()
    c1, c2 = st.columns([1, 3])
    run = c1.button(f"Run screen ({len(tickers)} tickers)", type="primary")
    if saved_at:
        c2.caption(f"Last screen: {dt.datetime.fromtimestamp(saved_at):%Y-%m-%d %H:%M} · {len(df)} companies. Re-run for fresh prices (data is cached 12h per ticker).")

    if run:
        bar = st.progress(0.0, text="Starting…")
        df, failed = screener.screen(
            tickers, Assumptions(discount, aaa),
            progress=lambda i, n, t: bar.progress(i / n, text=f"{i}/{n} · {t}"),
        )
        bar.empty()
        if not df.empty:
            screener.save(df)
        if failed:
            with st.expander(f"{len(failed)} tickers failed"):
                st.write(failed)

    if df.empty:
        st.info("No screen yet. Click **Run screen** — the first run takes a few minutes while data downloads.")
        return

    t1, t2, t3 = st.tabs(["🏛️ Long-term investments", "📈 Swing trades", "🎲 High risk / high reward"])
    with t1:
        st.markdown("**Wonderful businesses** (quality ≥ 55, sound balance sheets), ranked by Munger score. "
                    "*Action* tells you whether the price is reasonable now or whether to wait for Mr. Market.")
        show_table(screener.long_term(df), "long", "No company in the universe passed the quality bar.")
    with t2:
        st.markdown("**Active technical setups** in non-downtrending stocks with reward/risk ≥ 1.8. "
                    "Levels are mechanical suggestions; set your own stop and size the position for it.")
        show_table(screener.swing(df), "swing", "No clean setups today. No trade is a position too.")
    with t3:
        st.warning("Speculative. Payoff ratio ≥ 2:1 on rough bull/bear anchors. Many of these will go to zero — "
                   "size every position as if it will.", icon="⚠️")
        show_table(screener.risky(df), "risky", "Nothing with a lopsided payoff right now.")


def page_my_watchlist() -> None:
    st.header("My watchlist")
    items = watchlist.load()
    with st.form("add", clear_on_submit=True):
        c1, c2, c3 = st.columns([1, 3, 1])
        t = c1.text_input("Ticker")
        note = c2.text_input("Why is it here? (your thesis, the price you'd pay…)")
        c3.write("")
        c3.write("")
        if c3.form_submit_button("Add") and t.strip():
            watchlist.add(t.strip(), note)
            st.rerun()
    if not items:
        st.info("Empty. Add tickers here or from any research page.")
        return
    rows = []
    with st.spinner("Refreshing…"):
        for tk, meta in items.items():
            try:
                s = cached_research(tk, discount, aaa).summary()
            except Exception:
                s = {"Ticker": tk}
            s["Note"], s["Added"] = meta.get("note", ""), meta.get("added", "")
            rows.append(s)
    df = pd.DataFrame(rows)
    cols = [c for c in ["Ticker", "Name", "Price", "Munger score", "Munger verdict", "Base MoS", "Swing score", "Setup", "Asymmetry score", "Note", "Added"] if c in df]
    event = st.dataframe(df[cols], hide_index=True, width="stretch", column_config=COL_CFG,
                         on_select="rerun", selection_mode="single-row", key="tbl_mine")
    sel = event.selection.rows if event and event.selection else []
    c1, c2 = st.columns(2)
    if sel:
        tk = df.iloc[sel[0]]["Ticker"]
        if c1.button(f"Open {tk} research", type="primary"):
            open_research(tk)
        if c2.button(f"Remove {tk}"):
            watchlist.remove(tk)
            st.rerun()
    else:
        st.caption("Select a row to open or remove it.")


def page_method() -> None:
    st.header("How it thinks")
    st.markdown("""
Every company is run through six independent lenses, then a Munger-style synthesis reads them together.

| Lens | Core question | Main tools |
|---|---|---|
| **Graham intrinsic value** | Is it cheap relative to proven earnings and assets? | Defensive-investor checklist, Graham number √(22.5·EPS·BVPS), revised formula EPS·(8.5+2g)·4.4/Y, net-net NCAV |
| **Future & expectations** | What growth does the price assume, and is that bar low or heroic? | Revenue/FCF CAGR, reinvestment (R&D, capex/D&A), ROE×retention, 3-scenario DCF on owner earnings, **reverse DCF** |
| **Moat & management** | Is this a wonderful business run by owner-minded people? | ROIC level and persistence, gross-margin stability, cash conversion, share count, SBC/FCF, insider ownership, leverage |
| **Financial strength** | Can it survive a bad stretch; are profits real cash? | Piotroski F-score, Altman Z, interest coverage, Sloan accrual ratio, cash runway |
| **Swing setup** | Is there a low-risk entry in the next days–weeks? | 20/50/200-day averages, RSI, MACD, ATR, Bollinger squeeze, volume; ATR/swing-low stop and R:R |
| **Asymmetric bet** | If right, how much do I make vs. lose if wrong — and what kills it? | Bull/bear anchors (analyst range, DCF scenarios, 52-week range, book value), volatility, short interest, runway, dilution |

**Munger synthesis** applies his four filters (circle of competence, durable advantage, able & honest management,
sensible price), **inverts** by collecting every red flag into a "how this fails" list, runs a **psychology-of-misjudgment**
check tailored to the stock (anchoring, social proof, commitment bias…), and flags **lollapalooza** effects when several
favourable forces line up at once.

**Owner earnings** used in the DCF = free cash flow − stock-based compensation, averaged over three years.

**Scores** are 0–100 checklists. Missing data is skipped rather than counted as a failure, so check the caveats when inputs are thin.

**Known limits**
- The free feed provides ~4–5 years of annual statements; Graham's 10-year tests are approximations.
- Banks and insurers break FCF, current-ratio and Altman models; those tests are skipped and flagged.
- A number can show that a moat exists, never *why*. That part is your job (or the Claude memo's first draft).
""")
    st.caption("Nothing here is investment advice. Use it to decide what to research, then read the filings.")


{PAGES[0]: page_research, PAGES[1]: page_watchlists, PAGES[2]: page_my_watchlist, PAGES[3]: page_method}[page]()
