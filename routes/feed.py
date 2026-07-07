from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user

from agents.agent import Agent
from agents.btl import BTLRuntimeError

feed_bp = Blueprint("feed", __name__)


@feed_bp.route("/feed")
@login_required
def feed_page():
    from services import finance as finance_service
    sectors = current_user.focus_sectors.split(",") if current_user.focus_sectors else []
    articles = finance_service.get_feed_articles(sectors)
    return render_template("feed.html", articles=articles)


@feed_bp.route("/api/feed/briefing")
@login_required
def briefing():
    agent = Agent(current_user)
    try:
        result = agent.daily_briefing()
    except BTLRuntimeError as e:
        return jsonify({"error": str(e)}), 502
    return jsonify(result)
