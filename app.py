import os
from flask import Flask
from config import Config
from extensions import db, login_manager


def run_autonomous_reviews_for_all_users(app):
    """Called once a day by the scheduler. Only reviews users who've explicitly
    opted in, everyone else is untouched. This is what makes 'autonomous' real
    rather than just a button someone has to remember to click."""
    with app.app_context():
        from models import User
        from agents.agent import Agent

        opted_in = User.query.filter_by(autonomous_enabled=True).all()
        for user in opted_in:
            try:
                Agent(user).autonomous_review(dry_run=False)
            except Exception:
                continue


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    os.makedirs(os.path.join(app.root_path, "instance"), exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from routes.auth import auth_bp
    from routes.onboarding import onboarding_bp
    from routes.main import main_bp
    from routes.stock import stock_bp
    from routes.trade import trade_bp
    from routes.research import research_bp
    from routes.feed import feed_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(onboarding_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(stock_bp)
    app.register_blueprint(trade_bp)
    app.register_blueprint(research_bp)
    app.register_blueprint(feed_bp)

    with app.app_context():
        db.create_all()

    # Flask's debug reloader runs two processes; only the reloaded child (or a
    # non-debug run) should actually start the background scheduler.
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        _start_scheduler(app)

    return app


def _start_scheduler(app):
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(
            run_autonomous_reviews_for_all_users,
            trigger="cron", hour=7, minute=0,
            args=[app], id="daily_autonomous_review", replace_existing=True,
        )
        scheduler.start()
    except Exception:
        # scheduler is a nice-to-have, never let it block the app from starting
        pass


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5820, host="0.0.0.0")
