"""
tool.py - the agent's hands. Every side-effecting or computed action the agent can take
goes through here: running verification code, pulling market data, fetching news,
recording a simulated trade. Keeping this separate from agent.py means the reasoning
layer never touches numbers directly - it only ever sees what tool.py hands back.
"""
import re
import math
import statistics
import numpy as np
import pandas as pd

from services import finance as finance_service


class ToolError(Exception):
    pass


def extract_code_block(text):
    """Pull a ```python fenced block out of an LLM response."""
    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    if not match:
        raise ToolError("No code block found in model output.")
    return match.group(1).strip()


def extract_calc_request(text):
    match = re.search(r"```calc_request\s*\n(.*?)```", text, re.DOTALL)
    if not match:
        return None
    return match.group(1).strip()


SAFE_BUILTINS = {
    "len": len, "sum": sum, "min": min, "max": max, "abs": abs,
    "round": round, "range": range, "enumerate": enumerate,
    "float": float, "int": int, "list": list, "dict": dict, "sorted": sorted,
    "zip": zip, "map": map, "filter": filter, "any": any, "all": all,
}


def _strip_import_lines(code_str):
    """The model is told pd/np/math/statistics/scipy are already available and not to
    import them itself, but models sometimes do it anyway. Rather than fail the whole
    calculation over a redundant import line, strip those lines, since the same names
    are already bound in the execution namespace below."""
    kept = []
    for line in code_str.splitlines():
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            continue
        kept.append(line)
    return "\n".join(kept)


def run_calc_code(code_str, data):
    """Execute a model-generated calculation in a locked-down namespace.

    This is the verification step: the LLM never gets to state a number directly,
    it has to produce code, and that code runs for real against real data.

    Note on scope: this namespace intentionally does NOT allow installing or importing
    arbitrary packages at runtime. Letting model-generated code pull in new packages on
    demand is a real remote-code-execution risk, not a feature. Instead the namespace is
    pre-loaded with everything a financial calculation is realistically going to need.
    """
    fn_name = "compute"
    code_str = _strip_import_lines(code_str)
    if f"def {fn_name}" not in code_str:
        raise ToolError("Generated code must define a compute(data) function.")

    try:
        import scipy.stats as scipy_stats
    except ImportError:
        scipy_stats = None

    namespace = {
        "__builtins__": SAFE_BUILTINS,
        "np": np,
        "pd": pd,
        "math": math,
        "statistics": statistics,
        "scipy_stats": scipy_stats,
    }
    try:
        exec(code_str, namespace)  # noqa: S102 - locked-down namespace, no I/O, no dunder builtins
        result = namespace[fn_name](data)
    except Exception as e:
        raise ToolError(f"Execution failed: {e}")

    return result


def get_price_snapshot(ticker):
    return finance_service.get_snapshot(ticker)


def get_price_history(ticker, period="6mo"):
    return finance_service.get_history(ticker, period=period)


def get_price_history_range(ticker, start, end, interval="1d"):
    return finance_service.get_history_range(ticker, start, end, interval=interval)


def fetch_news(query):
    return finance_service.get_news(query)


def fetch_feed(sectors):
    return finance_service.get_feed_articles(sectors)


def insert_trade_row(user_id, ticker, side, shares, price, stop_loss_price, rationale):
    from models import Trade
    from extensions import db

    trade = Trade(
        user_id=user_id, ticker=ticker, side=side, quantity=shares,
        price=price, stop_loss=stop_loss_price, status="filled", rationale=rationale,
    )
    db.session.add(trade)
    db.session.commit()
    return trade


def get_holdings(user_id):
    """Aggregate every filled trade into current net positions, weighted-average cost
    basis per ticker. This is what makes the dashboard reflect trades that actually
    happened instead of showing a balance that never moves."""
    from models import Trade

    trades = Trade.query.filter_by(user_id=user_id, status="filled").order_by(Trade.created_at.asc()).all()
    positions = {}
    for t in trades:
        pos = positions.setdefault(t.ticker, {"shares": 0.0, "cost_basis": 0.0})
        if t.side == "buy":
            pos["cost_basis"] += t.quantity * t.price
            pos["shares"] += t.quantity
        else:
            if pos["shares"] > 0:
                avg_cost = pos["cost_basis"] / pos["shares"]
                sell_qty = min(t.quantity, pos["shares"])
                pos["shares"] -= sell_qty
                pos["cost_basis"] -= avg_cost * sell_qty

    holdings = []
    for ticker, pos in positions.items():
        if pos["shares"] > 0.0001:
            avg_cost = pos["cost_basis"] / pos["shares"]
            holdings.append({"ticker": ticker, "shares": round(pos["shares"], 4), "avg_cost": round(avg_cost, 2)})
    return holdings


def portfolio_concentration_metrics(enriched_holdings, cash):
    """Real concentration math, computed directly, never guessed by the model.
    HHI (Herfindahl-Hirschman Index) is the standard concentration measure: sum of
    squared position weights. Under ~1500 is well diversified, over ~2500 is
    concentrated, by the same thresholds used for market concentration analysis."""
    total_value = cash + sum(h["market_value"] for h in enriched_holdings)
    if total_value <= 0 or not enriched_holdings:
        return {
            "total_value": total_value, "num_holdings": 0,
            "largest_position_pct": 0.0, "cash_pct": 100.0,
            "hhi": 0.0, "hhi_label": "no positions",
        }

    weights = [h["market_value"] / total_value for h in enriched_holdings]
    hhi = round(sum(w * w for w in weights) * 10000, 1)
    largest_pct = round(max(weights) * 100, 1) if weights else 0.0
    cash_pct = round((cash / total_value) * 100, 1)

    if hhi < 1500:
        label = "well diversified"
    elif hhi <= 2500:
        label = "moderately concentrated"
    else:
        label = "highly concentrated"

    return {
        "total_value": round(total_value, 2),
        "num_holdings": len(enriched_holdings),
        "largest_position_pct": largest_pct,
        "cash_pct": cash_pct,
        "hhi": hhi,
        "hhi_label": label,
    }
