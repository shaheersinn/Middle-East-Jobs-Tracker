"""
Configuration loader — reads from environment variables.
All secrets live in GitHub Secrets; never hard-coded here.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── Telegram ──────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str   = os.getenv("TELEGRAM_CHAT_ID", "")

    # ── Dashboard ─────────────────────────────────────────────────────────
    DASHBOARD_URL: str = os.getenv(
        "DASHBOARD_URL",
        "https://YOUR_USERNAME.github.io/me-legal-jobs-tracker/"
    )

    # ── Database ──────────────────────────────────────────────────────────
    DB_PATH: str = os.getenv("DB_PATH", "me_legal_jobs.db")

    # ── HTTP ──────────────────────────────────────────────────────────────
    REQUEST_TIMEOUT: int  = int(os.getenv("REQUEST_TIMEOUT", "25"))
    MIN_DELAY_SECS: float = float(os.getenv("MIN_DELAY_SECS", "1.5"))
    MAX_DELAY_SECS: float = float(os.getenv("MAX_DELAY_SECS", "4.0"))

    # ── Signal filtering ──────────────────────────────────────────────────
    SIGNAL_LOOKBACK_DAYS: int = int(os.getenv("SIGNAL_LOOKBACK_DAYS", "14"))

    # ── Instant alerts ────────────────────────────────────────────────────
    # Fire a Telegram message immediately when a new associate role is found
    INSTANT_ALERT_ON_NEW_JOB: bool = (
        os.getenv("INSTANT_ALERT_ON_NEW_JOB", "true").lower() == "true"
    )

    # ── ME location filtering (set to "strict" to skip non-ME jobs) ───────
    ME_LOCATION_FILTER: str = os.getenv("ME_LOCATION_FILTER", "strict")
