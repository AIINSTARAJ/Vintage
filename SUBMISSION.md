# Submission materials

## GitHub repo description (337 characters)

Vintage is a paper-trading desk built entirely on the BTL Runtime. It never lets a
model state a number, it writes and executes real code instead. It remembers every
call it makes, flags contradictions, runs a three-stage reasoning pipeline each
morning, and can trade on its own within limits you set, logging every decision
either way.

## Short description for the submission form (1-3 sentences)

Vintage is a paper-trading platform where an LLM never states a number without
computing it first, remembers and checks its own prior calls on every ticker, and
can execute trades on its own each morning once its confidence clears a threshold
you set, with every decision logged whether it acted or not. It solves the two
things that make AI-driven trading tools untrustworthy: models that state financial
figures from pattern-matching instead of computation, and assistants with no memory
of what they told you five minutes ago, let alone yesterday. Everything runs on the
BTL Runtime, single-turn Q&A, codegen-and-execute verification, a multi-stage
briefing pipeline, and the autonomous decision loop.

## Demo video script (2-3 minutes)

**[0:00-0:15] Cold open, on the dashboard**
"This is Vintage. It's a paper-trading desk, and the thing that makes it different
is that it doesn't trust itself, and I mean that literally, every number you're
about to see was computed, not guessed, by the model."

Show the dashboard: total value chart, cash, holdings.

**[0:15-0:40] Verified reasoning**
Go to a stock page, type a question that needs a real number ("what's the 20-day
volatility on this compared to its 90-day average"). Show the answer come back with
the `Verified` tag visible.
"Watch what just happened. The model didn't calculate that number. It wrote code,
that code ran for real against real price data, and only the answer that came back
from execution is shown. If the code fails, it sees its own error and fixes it once
before admitting it couldn't verify it. That's the whole point, an LLM should never
get to state a financial number from a guess."

**[0:40-1:05] Memory and contradiction**
Ask a follow-up on the same ticker that contradicts an earlier stance. Show the
"contradicts a prior call" flag appear.
"It remembers every call it's made on this stock. Ask something that doesn't square
with what it said last time, and it tells you before you find out the hard way."

**[1:05-1:30] The three-stage briefing**
Go to Feed, expand "show how this was put together."
"The morning briefing isn't one call pretending to be smart. It's three: one filters
raw headlines for what's actually significant, one checks that against what you
personally hold, one writes the final briefing. You can see all three stages here,
not just the polished paragraph."

**[1:30-2:05] Autonomous trading, the big one**
Go to the autonomous trading card on the dashboard. Toggle it on, show the
confidence threshold and max position size. Click "run now."
"Here's the part I actually care about most. Every morning at 7am, and any time I
click this button, it reviews my holdings and watchlist against live prices and
real news, and commits, buy, sell, or hold, with a stated confidence. If that
confidence clears the bar I set, it trades on its own. No human clicks buy. If it
doesn't clear the bar, nothing happens, but it's logged either way, so I can see
every decision it made, not just the ones it acted on."
Show an alert appear with reasoning and, if confidence cleared, the "traded" badge.

**[2:05-2:25] Portfolio health and close**
Quick cut to the portfolio health check running, showing the concentration numbers.
"Every calculation in this app, from a single stock's volatility to whether my
whole account is too concentrated in one position, runs the same way: computed for
real, never guessed. And every reasoning step, from a single answer to an
autonomous trade, runs on the BTL Runtime."

**[2:25-2:30] End card**
Vintage. Built on BTL Runtime.
