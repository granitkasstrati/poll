"""'How it thinks' text, shared by the web and desktop front ends (Markdown)."""

METHODOLOGY_MD = """\
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

*Nothing here is investment advice. Use it to decide what to research, then read the filings.*
"""
