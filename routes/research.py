from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

from agents.agent import Agent
from agents.btl import BTLRuntimeError

research_bp = Blueprint("research", __name__)


@research_bp.route("/research")
@login_required
def research_page():
    return render_template("research.html")


@research_bp.route("/api/research/ask", methods=["POST"])
@login_required
def research_ask():
    payload = request.json or {}
    query = payload.get("query", "").strip()
    brief = bool(payload.get("brief", False))
    history = payload.get("history", [])
    if not query:
        return jsonify({"error": "Ask a research question or ticker first."}), 400

    agent = Agent(current_user)
    try:
        result = agent.research(query, brief=brief, history=history)
    except BTLRuntimeError as e:
        return jsonify({"error": str(e)}), 502

    return jsonify(result)
