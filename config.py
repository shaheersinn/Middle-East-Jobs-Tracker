"""
Configuration — loaded from environment variables / .env file
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass


class Config:
    # ── Telegram ──────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str  = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID:   str  = os.getenv("TELEGRAM_CHAT_ID", "")

    # ── Dashboard ─────────────────────────────────────────────────────────
    # Fixed: Vercel deployment URL
    DASHBOARD_URL: str = os.getenv(
        "DASHBOARD_URL",
        "https://middle-east-jobs-tracker.vercel.app/"
    )

    # ── Database ──────────────────────────────────────────────────────────
    DB_PATH: str = os.getenv("DB_PATH", "me_legal_jobs.db")

    # ── Behaviour ─────────────────────────────────────────────────────────
    INSTANT_ALERT_ON_NEW_JOB: bool = (
        os.getenv("INSTANT_ALERT_ON_NEW_JOB", "true").lower() == "true"
    )

    # ── Self-Training ─────────────────────────────────────────────────────
    ENABLE_SELF_TRAINING: bool = (
        os.getenv("ENABLE_SELF_TRAINING", "true").lower() == "true"
    )
    TRAINING_INTERVAL_HOURS: int = int(os.getenv("TRAINING_INTERVAL_HOURS", "2"))
