"""Load configuration from .env"""
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@batikairuz")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
RUN_TIME = os.getenv("RUN_TIME", "09:00")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Tashkent")
MODEL = os.getenv("MODEL", "claude-sonnet-4-6")

RELEVANCE_THRESHOLD = 60
MAX_CANDIDATES_KEPT = 3

DB_PATH = os.getenv("DB_PATH", "bot.db")


def validate():
    """Raise if required secrets are missing. Call at startup."""
    missing = []
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if not ADMIN_CHAT_ID:
        missing.append("ADMIN_CHAT_ID")
    if missing:
        raise RuntimeError(
            f"Missing required .env values: {', '.join(missing)}. "
            f"See .env.example for the full list."
        )
