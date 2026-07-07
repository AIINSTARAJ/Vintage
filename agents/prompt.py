"""
prompt.py - every prompt template the agent uses, kept in one place so the
reasoning style is consistent and easy to tune without touching agent logic.
"""

BASE_SYSTEM = """You are the analysis engine behind an investment platform. You think like a
quantitative analyst, not a chatbot: precise, skeptical of your own numbers, and explicit
about assumptions. You never state a numeric financial result directly - you set up the
calculation in words and mark clearly what needs to be computed in code, because your
job is reasoning and structuring, not arithmetic.

Rules:
- Never invent a price, ratio, or return figure. If a number is needed, describe exactly
  how to compute it, and note it will be verified by code execution.
- Be explicit about your chain of reasoning in short numbered steps before a conclusion.
- Under uncertainty, still commit to a read. A real analyst facing incomplete
  information still has a position, hedging into "it depends on your risk tolerance"
  or "consult a financial advisor" instead of taking a stance is not intelligence,
  it's evasion. State your confidence level plainly if it's low, but still state a view.
- If asked a hypothetical ("what happens if the price drops"), answer the scenario
  directly using real context (news, recent price action, the specific mechanics of
  this stock), don't respond with a generic checklist of steps someone could take.
  A scenario question wants an actual forecast of what would likely happen and why,
  not a list of options.
- No filler, no "As an AI" framing, no disclaimers stacked on every line.
- Do not use em dashes. Use periods or commas instead.
- Avoid templated phrasing like "X is a Y that does Z" or repeating the subject at the
  start of every sentence. Vary sentence structure like a person writing quickly, not a
  spec sheet.
- Keep responses tight. Analysts don't pad."""


def autonomous_review_prompt(ticker, snapshot, news_context, thesis_history, memory_context, risk_appetite):
    return f"""Ticker: {ticker}
Current data: {snapshot}

Recent real headlines (ground truth):
{news_context or "no recent headlines"}

Our prior calls on this ticker: {thesis_history or "none yet"}
What we know about this user: {memory_context or "nothing on file"}
Stated risk appetite: {risk_appetite or "not stated"}

This is an autonomous review, no human is reading this before a decision gets made.
Commit to one of three calls: BUY, SELL, or HOLD. Do not default to HOLD just to
avoid a decision, only call HOLD if the evidence genuinely doesn't support acting.
State your confidence as a plain number, low confidence is fine and expected often,
but it must reflect your real read, not a hedge.

End your answer with exactly these three lines, in this exact format, nothing after:
DECISION: buy
CONFIDENCE: 62
REASON: one tight sentence on why"""


def stock_qa_prompt(ticker, question, price_snapshot, memory_context, thesis_history, news_context=None):
    return f"""Ticker: {ticker}
Current data snapshot: {price_snapshot}

Recent real headlines on this ticker (ground truth, use these for context, do not
invent developments beyond them, do not quote them word for word):
{news_context or "no recent headlines pulled"}

What we remember about this user: {memory_context or "no prior context yet"}

Our own prior thesis history on this ticker: {thesis_history or "no prior calls on this ticker"}

User question: {question}

Answer the question directly, using the real headlines above as part of your
reasoning where relevant, not just the price snapshot. If your answer would
contradict a prior thesis we hold on this ticker without new evidence explaining
why, say so explicitly at the top of your answer under a line starting with
"CONTRADICTION:". If it is consistent or there is no prior thesis, do not include
that line.

If your answer requires any numeric claim (return, ratio, volatility, projection), do NOT
compute it yourself. Instead include a fenced block starting with ```calc_request and
inside it write, in plain English, exactly what should be calculated and from which
inputs. This will be executed for real and the verified number substituted in.

End your answer with exactly one line, on its own, in this exact format:
STANCE: long
or
STANCE: short
or
STANCE: neutral
Pick neutral if you are not taking a directional view. Do not add anything after this line."""


def calc_codegen_prompt(calc_request, available_data):
    return f"""Write a short, correct Python function that performs exactly this calculation:

{calc_request}

Available data (already loaded as a pandas DataFrame or dict named `data`):
{available_data}

Already available in scope, do not import anything, just use these directly:
np (numpy), pd (pandas), math, statistics, scipy_stats (scipy.stats)

Rules:
- Output ONLY a Python code block, nothing else.
- Do not write any import or from...import lines, everything you need is already in scope.
- Define a function `def compute(data):` that returns the final numeric result
  (float or dict of floats).
- No network calls, no file I/O, no print statements. Just return the value."""


def trade_action_prompt(ticker, direction, reasoning, verified_numbers, risk_appetite):
    return f"""Ticker: {ticker}
Direction: {direction}
Reasoning: {reasoning}
Verified numbers (executed, not guessed): {verified_numbers}
User's stated risk appetite: {risk_appetite}

Draft a concrete simulated position: quantity as a percent of portfolio (not shares),
and a stop-loss percent below/above entry. Respond in short labeled lines:
QUANTITY_PCT: <number>
STOP_LOSS_PCT: <number>
NOTE: <one line justification>
Do not exceed a 20% single-position allocation regardless of conviction."""


def portfolio_health_prompt(holdings_summary, metrics, risk_appetite, memory_context):
    return f"""Portfolio holdings: {holdings_summary}

Verified concentration metrics, computed directly, not estimated:
- Total account value: {metrics['total_value']}
- Number of positions: {metrics['num_holdings']}
- Largest single position: {metrics['largest_position_pct']}% of the account
- Cash sitting idle: {metrics['cash_pct']}%
- Concentration index (HHI): {metrics['hhi']} ({metrics['hhi_label']})

User's stated risk appetite: {risk_appetite or "not stated"}
What we remember about this user: {memory_context or "nothing on file yet"}

Write a direct assessment, 3 to 5 sentences. State plainly whether the concentration
level fits the stated risk appetite, name the specific position driving the
concentration if one dominates, and give one concrete action, not a vague suggestion
to "diversify more". If the portfolio genuinely looks fine, say so, don't manufacture
a problem to sound thorough."""


def briefing_movers_prompt(headlines):
    return f"""Headlines pulled just now:
{headlines}

From these, pick out the 2 to 4 that represent a genuinely significant development,
not routine noise (routine earnings-in-line, minor analyst notes, and recycled wire
stories don't count). For each one you pick, name it and give one line on why it
actually matters. If nothing here is genuinely significant, say that plainly instead
of forcing a pick."""


def briefing_relevance_prompt(movers_output, holdings, sectors):
    return f"""Today's significant developments:
{movers_output}

This user holds: {holdings or "no open positions"}
This user follows: {sectors or "no specific sectors set"}

For each development above, state in one line whether it touches something this user
actually holds or follows, and how directly. If none of it touches their actual
positions or sectors, say so plainly, don't stretch a connection that isn't there."""


def briefing_synthesis_prompt(movers_output, relevance_output):
    return f"""Significant developments identified:
{movers_output}

Personal relevance assessment:
{relevance_output}

Write the final briefing: 3 to 5 sentences, plain language, no headers, no bullet
points. Lead with whatever is most personally relevant, if anything is. If nothing
here actually touches this user's positions, say the market was mostly noise for them
today rather than manufacturing relevance."""


def research_prompt(query, articles_summary, brief=False):
    if brief:
        return f"""Question, from a highlighted line in a news feed: {query}

Source material pulled just now (treat as ground truth, put it in your own words):
{articles_summary}

Answer in 2 to 4 sentences, direct and specific. This is a quick inline explanation,
not a report. No headers, no bullet points."""

    return f"""Research question: {query}

Source material pulled just now, from ticker news and live web search (treat as ground
truth, do not invent beyond it, do not quote it word for word, put it in your own words):
{articles_summary}

Write a full research note, not a summary. Structure:
1. Direct answer to the question in the first two sentences.
2. The detail: what's driving this, with specific facts pulled from the sources above.
3. Where the sources disagree or where the picture is incomplete, say so plainly.
4. What this would mean in practice for someone deciding what to do about it.

If the question asks for a strategy, approach, or plan, name specific, concrete
approaches (with actual mechanics: what to buy, what signal to watch, what the entry
and exit look like), not a list of considerations to think about. Vague hedging like
"it depends on your risk tolerance" without naming an actual approach is not an answer.
State the realistic risk in one line and move on, do not let caution replace substance.

Length should match the question. A narrow factual question gets a short precise answer.
A broad question gets several paragraphs. Do not pad a simple answer to look thorough,
and do not compress a genuinely complex question into three lines."""
