import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-not-for-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "SQLALCHEMY_DATABASE_URI", f"sqlite:///{os.path.join(BASE_DIR, 'data', 'vintage.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    GATEWAY_API_KEY = os.environ.get("GATEWAY_API_KEY", "")
    GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "https://api.badtheorylabs.com/v1")
    GATEWAY_MODEL = os.environ.get("GATEWAY_MODEL", "gpt-4.1-mini")

    ALPHAVANTAGE_API_KEY = os.environ.get("ALPHAVANTAGE_API_KEY", "")

    STARTING_PAPER_BALANCE = float(os.environ.get("STARTING_PAPER_BALANCE", 100000))
