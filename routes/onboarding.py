from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user

from extensions import db
from agents import memory as M

onboarding_bp = Blueprint("onboarding", __name__)

SECTORS = ["Technology", "Finance", "Healthcare", "Energy", "Consumer", "Industrials", "Crypto-adjacent"]


@onboarding_bp.route("/onboarding", methods=["GET", "POST"])
@login_required
def onboarding():
    if current_user.onboarded:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        risk = request.form.get("risk_appetite", "medium")
        horizon = request.form.get("horizon", "both")
        experience = request.form.get("experience_level", "some")
        sectors = request.form.getlist("sectors")

        if username:
            current_user.username = username
        current_user.risk_appetite = risk
        current_user.horizon = horizon
        current_user.experience_level = experience
        current_user.focus_sectors = ",".join(sectors)
        current_user.onboarded = True
        db.session.commit()

        # seed persistent context immediately so the agent's first answer already
        # reflects who this user is, not a cold start
        M.add_fact(current_user.id, f"Risk appetite: {risk}", kind="preference", source="onboarding")
        M.add_fact(current_user.id, f"Preferred horizon: {horizon}", kind="preference", source="onboarding")
        if sectors:
            M.add_fact(current_user.id, f"Interested sectors: {', '.join(sectors)}", kind="preference", source="onboarding")

        return redirect(url_for("main.dashboard"))

    return render_template("onboarding.html", sectors=SECTORS, default_username=current_user.username)
