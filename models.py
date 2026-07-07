from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # onboarding fields
    risk_appetite = db.Column(db.String(20))       # low / medium / high
    horizon = db.Column(db.String(20))              # short / long / both
    experience_level = db.Column(db.String(20))     # new / some / experienced
    focus_sectors = db.Column(db.String(255))        # comma separated
    onboarded = db.Column(db.Boolean, default=False)

    paper_balance = db.Column(db.Float, default=100000.0)

    # autonomous trading settings, off by default, explicit opt-in
    autonomous_enabled = db.Column(db.Boolean, default=False)
    autonomous_max_pct = db.Column(db.Float, default=3.0)
    autonomous_confidence_threshold = db.Column(db.Float, default=75.0)

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)


class MemoryFact(db.Model):
    """Persistent context: durable facts/preferences/constraints the agent has learned about the user."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    kind = db.Column(db.String(30))          # preference / constraint / fact
    content = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(30))        # onboarding / chat / trade
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    active = db.Column(db.Boolean, default=True)


class ThesisEntry(db.Model):
    """Per-ticker running thesis ledger - what the agent has said about a stock and why, for
    contradiction-checking and for the improvement loop once outcomes are known."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    ticker = db.Column(db.String(12), nullable=False)
    direction = db.Column(db.String(10))      # long / short / neutral
    reasoning = db.Column(db.Text)
    price_at_call = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # filled in later once we check outcome (improvement pillar)
    outcome_checked = db.Column(db.Boolean, default=False)
    outcome_correct = db.Column(db.Boolean, nullable=True)
    price_at_check = db.Column(db.Float, nullable=True)


class VerificationLog(db.Model):
    """Every time the LLM's stated number disagreed with the executed/computed number.
    This is what powers 'continuous improvement' - calc types that fail often get stricter checks."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    calc_type = db.Column(db.String(50))       # e.g. sharpe_ratio, cagr, position_size
    llm_claimed = db.Column(db.String(120))
    executed_result = db.Column(db.String(120))
    mismatched = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CalcTypeConfidence(db.Model):
    """Running confidence score per calculation type, used to decide how hard to verify next time."""
    id = db.Column(db.Integer, primary_key=True)
    calc_type = db.Column(db.String(50), unique=True, nullable=False)
    total_checks = db.Column(db.Integer, default=0)
    mismatches = db.Column(db.Integer, default=0)

    @property
    def error_rate(self):
        if self.total_checks == 0:
            return 0.0
        return self.mismatches / self.total_checks


class Trade(db.Model):
    """Simulated / paper trade. Never touches real money or a real brokerage."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    ticker = db.Column(db.String(12), nullable=False)
    side = db.Column(db.String(10))            # buy / sell
    quantity = db.Column(db.Float)
    price = db.Column(db.Float)
    stop_loss = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(20), default="filled")   # filled / held_for_review / cancelled
    rationale = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PortfolioSnapshot(db.Model):
    """One row per day per user, total account value (cash + holdings) at that point.
    This is what lets the dashboard chart real performance over time instead of
    fabricating a sparkline. Empty until the account has been used for more than a day."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    total_value = db.Column(db.Float, nullable=False)

    __table_args__ = (db.UniqueConstraint("user_id", "date", name="uq_snapshot_user_date"),)


class AutonomousAlert(db.Model):
    """One row per ticker reviewed in an autonomous run, whether or not it resulted
    in a trade. This is the audit trail for anything the agent did without a human
    clicking a button first."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    ticker = db.Column(db.String(12), nullable=False)
    decision = db.Column(db.String(10))       # buy / sell / hold
    confidence = db.Column(db.Float)
    reasoning = db.Column(db.Text)
    executed = db.Column(db.Boolean, default=False)
    trade_id = db.Column(db.Integer, db.ForeignKey("trade.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    seen = db.Column(db.Boolean, default=False)


class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    role = db.Column(db.String(10))            # user / assistant
    content = db.Column(db.Text)
    ticker_context = db.Column(db.String(12), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
