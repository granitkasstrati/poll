"""Optional: have Claude write a Munger-style investment memo from the computed research.

Requires the `anthropic` package and credentials (ANTHROPIC_API_KEY, or an
`ant auth login` profile). Claude gets the quantitative findings plus web
search, so it can add what numbers can't show: recent news, competitive
dynamics, management track record, upcoming catalysts.
"""

from __future__ import annotations

import json
from typing import Iterator

from .research import Research

MODEL = "claude-opus-5-5"
MAX_CONTINUATIONS = 5

SYSTEM = """You are a research analyst who thinks like Charlie Munger. You write investment memos for an \
experienced individual investor who uses them as one input among many — never as advice to act on.

How you think:
- Start with inversion: what would make this a bad investment? Look for the reasons to say no first.
- Apply the four filters: circle of competence, durable competitive advantage, able and honest management, sensible price.
- Name the moat precisely (brand, network effect, switching costs, scale, regulation, cost advantage) or say there isn't one.
- Look at incentives — of management, of analysts, of anyone promoting the stock.
- Note where psychology could mislead the reader (anchoring, social proof, commitment bias).
- Be blunt and concise. "Too hard" is a valid conclusion.

Use web search to check recent news, earnings, guidance, competitive threats, regulatory issues, insider \
transactions, and management's capital-allocation record. Cite sources inline. If a quantitative finding \
you were given looks inconsistent with what you find (e.g. a one-off charge distorting earnings), say so.

Structure (markdown, ~600-900 words):
## Thesis in one paragraph
## The business and its moat
## Management and incentives
## Inversion: how this goes wrong
## What the price implies
## Munger's verdict
## What to verify next (5 concrete items: filings, metrics, questions)
"""


def _payload(res: Research) -> str:
    out = {
        "company": {"ticker": res.data.ticker, "name": res.data.name, "sector": res.data.sector,
                    "industry": res.data.industry, "price": res.data.price, "market_cap": res.data.market_cap,
                    "business_summary": (res.data.info.get("longBusinessSummary") or "")[:2000]},
        "assumptions": {"discount_rate": res.assumptions.discount_rate, "aaa_yield": res.assumptions.aaa_yield},
        "munger_synthesis": {
            "verdict": res.munger.report.verdict, "score": res.munger.report.score,
            "filters": [{"name": f.name, "status": f.status, "evidence": f.evidence} for f in res.munger.filters],
            "inversion": res.munger.inversion, "lollapalooza": res.munger.lollapalooza,
        },
        "lenses": {},
    }
    for key, rep in res.reports.items():
        d = rep.to_dict()
        d["metrics"] = {k: v for k, v in d["metrics"].items() if not k.startswith("_")}
        out["lenses"][key] = d
    return json.dumps(out, default=str, indent=1)


def stream_memo(res: Research, effort: str = "high") -> Iterator[str]:
    """Yield the memo as text chunks. Raises anthropic errors to the caller."""
    import anthropic

    client = anthropic.Anthropic()
    messages = [{
        "role": "user",
        "content": (
            f"Write the memo for {res.data.name} ({res.data.ticker}). Here is the quantitative research "
            f"the app computed from public data (Yahoo Finance; may contain errors):\n\n<research>\n{_payload(res)}\n</research>"
        ),
    }]
    for _ in range(MAX_CONTINUATIONS):
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=32000,
            system=SYSTEM,
            messages=messages,
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}],
            output_config={"effort": effort},
            # On a safety-classifier decline, the API retries on Anthropic's recommended fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            for text in stream.text_stream:
                yield text
            final = stream.get_final_message()

        if final.stop_reason == "pause_turn":
            # Server-side tool loop hit its iteration cap; resend to let it resume.
            messages = messages[:1] + [{"role": "assistant", "content": final.content}]
            continue
        if final.stop_reason == "refusal":
            yield "\n\n*The model declined to complete this memo.*"
        elif final.stop_reason == "max_tokens":
            yield "\n\n*Memo truncated (output limit reached).*"
        return
