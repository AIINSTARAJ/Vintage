from flask import Blueprint, render_template
from flask_login import login_required, current_user

from models import Trade, ThesisEntry, MemoryFact
from agents.agent import Agent

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def landing():
    return render_template("landing.html")


@main_bp.route("/dashboard")
@login_required
def dashboard():
    agent = Agent(current_user)
    try:
        resolved = agent.refresh_thesis_outcomes()
    except Exception:
        resolved = []

    try:
        portfolio = agent.portfolio_snapshot()
        value_history = agent.value_history()
    except Exception:
        portfolio = {"cash": current_user.paper_balance, "market_value": 0, "total_value": current_user.paper_balance, "holdings": []}
        value_history = []

    recent_trades = Trade.query.filter_by(user_id=current_user.id).order_by(Trade.created_at.desc()).limit(6).all()
    thesis_log = ThesisEntry.query.filter_by(user_id=current_user.id).order_by(ThesisEntry.created_at.desc()).limit(6).all()
    fact_count = MemoryFact.query.filter_by(user_id=current_user.id, active=True).count()

    correct = sum(1 for t in thesis_log if t.outcome_correct)
    checked = sum(1 for t in thesis_log if t.outcome_checked)
    hit_rate = round((correct / checked) * 100, 1) if checked else None

    return render_template(
        "dashboard.html",
        recent_trades=recent_trades,
        thesis_log=thesis_log,
        fact_count=fact_count,
        hit_rate=hit_rate,
        just_resolved=resolved,
        portfolio=portfolio,
        value_history=value_history,
    )
