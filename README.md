# Vintage

Vintage is a trading desk that reasons before it speaks, verifies before it states a
number, remembers every call it makes, and acts on its own when it's earned the right
to. Every model call in the system, chat, verification, portfolio analysis, the daily
briefing, and autonomous trade decisions, runs through the BTL Runtime. There is no
other LLM provider wired into this codebase.

## The core idea

Most AI trading tools are a chat window bolted onto a stock ticker. Vintage is built
around a different premise: an LLM should never be trusted to state a number, should
always be checked against its own prior calls, and should be allowed to act on its
own only inside limits a human set in advance. Four systems carry that premise
through the whole app.

### 1. Verified reasoning, not guessed reasoning

Ask a question that needs a number, a return, a ratio, a volatility figure, and the
model never states it directly. It writes the calculation as a plain-English request,
that request becomes real Python code, the code executes against real historical
price data in a locked-down sandbox, and only the executed result reaches you. If the
generated code fails, the model is shown its own error and gets one attempt to
correct itself before the app admits, plainly, that it couldn't verify the number.
This is the same reasoning-and-execution pattern that a much larger engineering team
would recognize as "tool use with self-correction", built here at the scale a
48-hour desk actually needs.

### 2. Memory that gets checked against, not just stored

Every directional call the desk makes on a ticker is logged with the price and the
reasoning behind it. The next time you ask about that ticker, the model sees its own
prior calls and is instructed to flag a contradiction up front if the new answer
doesn't square with the old one, rather than quietly forgetting what it said last
week. Preferences and constraints stated in chat get captured the same way and
retrieved by relevance on every future question.

### 3. A three-stage reasoning pipeline for the daily briefing

The morning briefing isn't one model call dressed up as intelligence. It's three
distinct calls, each doing a different job, chained together:

1. **Significance filter** takes raw pulled headlines and picks out what's actually
   worth knowing, explicitly instructed to say "nothing here matters" rather than
   force a signal out of noise.
2. **Relevance check** takes stage one's output and checks it against this specific
   user's actual holdings and followed sectors, not a generic market summary.
3. **Synthesis** combines both into the final briefing, prioritizing whatever is
   personally relevant first.

The feed UI exposes "show how this was put together" so the intermediate stages are
inspectable, not hidden behind a single polished paragraph.

### 4. Autonomous trading, with a real audit trail

This is the pillar that separates a chatbot from an agent: the desk can act without
being asked. Every morning at 07:00 UTC, and on demand from the dashboard, an
autonomous review runs against your holdings and watchlist. For each ticker, it
pulls a live price snapshot, real recent news, and this account's own trading
history, then is required to commit to buy, sell, or hold with a stated confidence,
explicitly instructed not to default to hold just to dodge a decision. If you've
opted in and that confidence clears the threshold you set, it executes a real
(simulated) trade capped at the position size you set, no human in the loop for that
specific action. If it doesn't clear the bar, or you haven't opted in, nothing
trades, but the review is logged either way. Every autonomous decision, acted on or
not, is visible on the dashboard with its full reasoning attached.

## Everything else in the app

- **Real portfolio value**, reconstructed from actual trade history and actual
  historical prices at the actual times you traded, not a fabricated sparkline.
  Granularity adapts: hourly for a position opened today, daily once the span
  stretches out.
- **A portfolio health check** that looks at the whole account at once: concentration
  math (Herfindahl-Hirschman Index, largest position size, idle cash) computed
  directly, never estimated by the model, with a decisive narrative read on top.
- **A real chart**, candlesticks, moving averages, volume, six timeframes from
  1-day intraday candles up to 5 years, click any candle to ask what happened then.
- **Research as an actual multi-turn chat**, not a search box. Remembers the
  conversation, persists across navigation, supports voice input and read-aloud via
  the browser's native speech APIs, highlight any line for an inline follow-up, and
  surfaces real web search results (via DuckDuckGo, no key required) alongside
  ticker-specific news.
- **Per-ticker chat memory** on the stock page itself, come back to a ticker later
  and the conversation is still there.

## Project structure

```
app.py                    App factory, blueprint registration, autonomous scheduler
config.py                 Env-driven config
extensions.py             Shared db / login_manager instances
models.py                 SQLAlchemy models, including the autonomous alert log

agents/
  btl.py                  The only module that talks to the BTL Runtime
  prompt.py               Every prompt template, including the autonomous decision format
  tool.py                 Sandboxed code execution, portfolio math, trade recording
  memory.py               Persistent facts, thesis ledger, confidence scoring
  agent.py                Orchestrator: Q&A, verification, briefing pipeline, autonomous review

services/
  interface.py            yfinance / Alpha Vantage / DuckDuckGo search, low level
  finance.py               Source selection, data shaping

routes/                   auth, onboarding, dashboard, stock, trade, research, feed
templates/, static/       Flask/Jinja UI, lightweight-charts, Chart.js, native speech APIs
```

## The sandbox, by design

`agents/tool.py::run_calc_code` executes model-generated Python in a locked-down
namespace with numpy, pandas, math, statistics, and scipy.stats pre-loaded. It does
not grant the ability to install packages or reach the network at runtime, and that
line doesn't move. Letting model output control what gets installed on a running
server is a real security boundary, not a missing feature, and the self-correction
loop already delivers the practical benefit (code that fixes its own mistakes)
without that exposure.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# paste your BTL workspace key into GATEWAY_API_KEY

python app.py
```

If the runtime returns a 402, the workspace is out of credits. Either top up in the
BTL dashboard or point `GATEWAY_MODEL` at an explicitly free route (one ending in
`:free`), see `runtime.badtheorylabs.com/docs` for the current list.

Auth, onboarding, dashboard, stock search, and charting all work without a key,
they only depend on yfinance. Chat, verification, research, the briefing, portfolio
health, and autonomous review need the runtime connected.
