from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from agents.agent import Agent
from agents.btl import BTLRuntimeError
from extensions import db

trade_bp = Blueprint("trade", __name__)


@trade_bp.route("/api/trade/draft", methods=["POST"])
@login_required
def draft_trade():
    payload = request.json or {}
    ticker = payload.get("ticker", "").upper().strip()
    direction = payload.get("direction", "long")
    reasoning = payload.get("reasoning", "")
    verified_numbers = payload.get("verified_numbers", "")

    if not ticker:
        return jsonify({"error": "Ticker required."}), 400

    agent = Agent(current_user)
    try:
        draft = agent.draft_trade(ticker, direction, reasoning, verified_numbers)
    except BTLRuntimeError as e:
        return jsonify({"error": str(e)}), 502

    return jsonify(draft)


@trade_bp.route("/api/trade/execute", methods=["POST"])
@login_required
def execute_trade():
    payload = request.json or {}
    ticker = payload.get("ticker", "").upper().strip()
    side = payload.get("side", "buy")
    price = float(payload.get("price", 0))
    quantity_pct = payload.get("quantity_pct")
    amount_usd = payload.get("amount_usd")
    stop_loss_pct = payload.get("stop_loss_pct")
    rationale = payload.get("note", "")

    if not ticker or not price:
        return jsonify({"error": "Ticker and price are required."}), 400
    if quantity_pct is None and amount_usd is None:
        return jsonify({"error": "Specify either an amount or a percent of the account."}), 400

    agent = Agent(current_user)
    try:
        trade = agent.execute_paper_trade(
            ticker, side, price,
            quantity_pct=float(quantity_pct) if quantity_pct is not None else None,
            amount_usd=float(amount_usd) if amount_usd is not None else None,
            stop_loss_pct=float(stop_loss_pct) if stop_loss_pct else None,
            rationale=rationale,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({
        "id": trade.id,
        "ticker": trade.ticker,
        "side": trade.side,
        "quantity": trade.quantity,
        "price": trade.price,
        "stop_loss": trade.stop_loss,
        "status": trade.status,
        "new_cash_balance": round(current_user.paper_balance, 2),
        "simulated": True,
    })


@trade_bp.route("/api/portfolio")
@login_required
def portfolio():
    agent = Agent(current_user)
    return jsonify(agent.portfolio_snapshot())


@trade_bp.route("/api/autonomous/run-now", methods=["POST"])
@login_required
def autonomous_run_now():
    """Safe to click any time, this is a dry run, it reasons and logs but never
    trades on its own unless autonomous_enabled is also on."""
    agent = Agent(current_user)
    try:
        alerts = agent.autonomous_review(dry_run=not current_user.autonomous_enabled)
    except BTLRuntimeError as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"alerts": [
        {"ticker": a.ticker, "decision": a.decision, "confidence": a.confidence,
         "reasoning": a.reasoning, "executed": a.executed}
        for a in alerts
    ]})


@trade_bp.route("/api/autonomous/settings", methods=["GET", "POST"])
@login_required
def autonomous_settings():
    from extensions import db
    if request.method == "POST":
        payload = request.json or {}
        current_user.autonomous_enabled = bool(payload.get("enabled", False))
        current_user.autonomous_max_pct = float(payload.get("max_pct", 3.0))
        current_user.autonomous_confidence_threshold = float(payload.get("confidence_threshold", 75.0))
        db.session.commit()
    return jsonify({
        "enabled": current_user.autonomous_enabled,
        "max_pct": current_user.autonomous_max_pct,
        "confidence_threshold": current_user.autonomous_confidence_threshold,
    })


@trade_bp.route("/api/autonomous/alerts")
@login_required
def autonomous_alerts():
    from models import AutonomousAlert
    from extensions import db
    alerts = (
        AutonomousAlert.query.filter_by(user_id=current_user.id)
        .order_by(AutonomousAlert.created_at.desc())
        .limit(10)
        .all()
    )
    unseen = [a for a in alerts if not a.seen]
    for a in unseen:
        a.seen = True
    if unseen:
        db.session.commit()
    return jsonify({"alerts": [
        {
            "ticker": a.ticker, "decision": a.decision, "confidence": a.confidence,
            "reasoning": a.reasoning, "executed": a.executed,
            "created_at": a.created_at.strftime("%b %d, %H:%M"),
            "was_new": a in unseen,
        }
        for a in alerts
    ]})
@login_required
def portfolio_health():
    agent = Agent(current_user)
    try:
        result = agent.portfolio_health()
    except BTLRuntimeError as e:
        return jsonify({"error": str(e)}), 502
    return jsonify(result)
