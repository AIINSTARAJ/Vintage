from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

from agents.agent import Agent
from agents.btl import BTLRuntimeError
from agents import memory as M
from models import ChatMessage
from extensions import db

stock_bp = Blueprint("stock", __name__)


@stock_bp.route("/stock")
@login_required
def stock_search():
    ticker = request.args.get("ticker", "").upper().strip()
    return render_template("stock.html", ticker=ticker)


@stock_bp.route("/api/stock/<ticker>/history")
@login_required
def stock_history(ticker):
    from services import finance as finance_service
    try:
        data = finance_service.get_history(
            ticker,
            period=request.args.get("period", "6mo"),
            interval=request.args.get("interval", "1d"),
        )
        snapshot = finance_service.get_snapshot(ticker)
    except Exception as e:
        return jsonify({"error": f"Couldn't pull data for {ticker.upper()} right now. Check the symbol, or try again in a moment."}), 502

    if not data["series"]:
        return jsonify({"error": f"No price data found for {ticker.upper()} on this range. Check the symbol or try a different timeframe."}), 404

    return jsonify({"ticker": ticker.upper(), "series": data["series"], "snapshot": snapshot})


@stock_bp.route("/api/stock/<ticker>/ask", methods=["POST"])
@login_required
def stock_ask(ticker):
    payload = request.json or {}
    question = payload.get("question", "").strip()
    conversation_history = payload.get("history", [])
    if not question:
        return jsonify({"error": "Ask something first."}), 400

    db.session.add(ChatMessage(user_id=current_user.id, role="user", content=question, ticker_context=ticker.upper()))
    db.session.commit()

    agent = Agent(current_user)
    try:
        result = agent.answer_stock_question(ticker.upper(), question, conversation_history=conversation_history)
    except BTLRuntimeError as e:
        return jsonify({"error": str(e)}), 502

    # history carries a raw pandas DataFrame for internal verification use only,
    # never send it to the client, it isn't JSON serializable
    result.pop("history", None)

    db.session.add(ChatMessage(
        user_id=current_user.id, role="assistant", content=result["text"], ticker_context=ticker.upper()
    ))

    # lightweight fact capture: if the user states a preference or constraint inline in
    # chat, keep it - this is what makes memory feel alive rather than onboarding-only
    lowered = question.lower()
    if any(k in lowered for k in ["i don't like", "i prefer", "never", "always", "my rule"]):
        M.add_fact(current_user.id, question, kind="preference", source="chat")

    db.session.commit()

    return jsonify(result)
