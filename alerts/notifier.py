"""
Telegram Notifier
==================
Sends instant alerts on new job postings + weekly digest.

Instant alert fires when:
  - A new lawyer/associate job at a tracked US firm in ME is found
  - A recruiter posts a role matching a tracked firm
  - A Chambers/Legal 500 ranking change detected

Weekly digest fires every Sunday with:
  - All new job postings by firm × location × department
  - Recruiter activity summary
  - Lateral hire signals
  - Rankings changes
"""

import logging
import json
from datetime import datetime, timezone

import requests

logger = logging.getLogger("alerts.notifier")

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

SIGNAL_EMOJI = {
    "job_posting":       "💼",
    "recruiter_posting": "🔍",
    "lateral_hire":      "🚀",
    "press_release":     "📢",
    "ranking":           "🏆",
    "website_snapshot":  "🌐",
}

DEPT_EMOJI = {
    "Corporate / M&A":               "🤝",
    "Banking & Finance":              "🏦",
    "Capital Markets":                "📈",
    "Project Finance & Infrastructure":"🏗️",
    "Energy & Natural Resources":     "⚡",
    "Real Estate":                    "🏢",
    "Arbitration & Disputes":         "⚖️",
    "Islamic Finance":                "☪️",
    "Private Equity & Funds":         "💰",
    "Regulatory & Compliance":        "📋",
    "Employment & Labour":            "👷",
    "Data Privacy & Technology":      "🔒",
    "Construction & Engineering":     "🔧",
    "Restructuring & Insolvency":     "🔄",
}


class Notifier:
    def __init__(self, config):
        self._token   = config.TELEGRAM_BOT_TOKEN
        self._chat_id = config.TELEGRAM_CHAT_ID
        self._dashboard_url = config.DASHBOARD_URL
        self._instant = config.INSTANT_ALERT_ON_NEW_JOB

    # ── Public interface ──────────────────────────────────────────────────

    def send_instant_alert(self, signal: dict):
        if not self._instant:
            return
        msg = self._format_instant(signal)
        self._send(msg)

    def send_combined_digest(
        self,
        expansion_alerts: list[dict],
        website_changes: list[dict],
        new_signals: list[dict] = None,
    ):
        if not expansion_alerts and not (new_signals or []):
            logger.info("Nothing to digest — skipping Telegram send")
            return

        msg = self._format_digest(expansion_alerts, new_signals or [])
        self._send(msg)

    # ── Formatters ────────────────────────────────────────────────────────

    def _format_instant(self, signal: dict) -> str:
        emoji    = SIGNAL_EMOJI.get(signal.get("signal_type", ""), "📌")
        dept_e   = DEPT_EMOJI.get(signal.get("department", ""), "⚖️")
        loc      = signal.get("location", "Middle East")
        seniority = signal.get("seniority", "Associate")
        recruiter = signal.get("recruiter", "")

        lines = [
            f"{emoji} <b>New ME Legal Job Posting</b>",
            "",
            f"🏛 <b>{signal['firm_name']}</b>",
            f"📍 Location: {loc}",
            f"👤 Role: {seniority}",
            f"{dept_e} Practice: {signal.get('department', 'N/A')}",
        ]
        if recruiter:
            lines.append(f"🔍 Via: {recruiter}")
        lines += [
            f"📝 {signal['title']}",
            f"🔗 <a href='{signal.get('url','#')}'>View Posting</a>",
            "",
            f"🖥 <a href='{self._dashboard_url}'>Open Dashboard →</a>",
        ]
        return "\n".join(lines)

    def _format_digest(self, alerts: list[dict], new_signals: list[dict]) -> str:
        today = datetime.now(timezone.utc).strftime("%-d %B %Y")

        # Count job postings
        job_sigs = [s for s in new_signals if s.get("signal_type") in ("job_posting", "recruiter_posting")]
        hire_sigs = [s for s in new_signals if s.get("signal_type") == "lateral_hire"]

        lines = [
            "⚖️ <b>ME Legal Jobs Tracker</b>",
            f"Week ending {today}",
            f"🖥 <a href='{self._dashboard_url}'>Open Dashboard →</a>",
            "─" * 36,
            f"{len(job_sigs)} new job posting(s)  |  {len(hire_sigs)} lateral hire signal(s)",
            f"{len(alerts)} firm-department alert(s)",
            "",
        ]

        for i, alert in enumerate(alerts[:10], 1):
            dept_e = DEPT_EMOJI.get(alert["department"], "⚖️")
            loc    = alert.get("location", "Middle East")
            bkd    = alert.get("signal_breakdown", {})
            bkd_str = "  ".join(f"{v}× {k.replace('_',' ')}" for k, v in bkd.items())

            lines += [
                f"{i}. 🏛 <b>{alert['firm_name']}</b>",
                f"   {dept_e} {alert['department']} — 📍 {loc}",
                f"   Score: {alert['expansion_score']}  |  {alert['signal_count']} signal(s)",
                f"   {bkd_str}",
            ]

            for sig in alert.get("signals", [])[:3]:
                e = SIGNAL_EMOJI.get(sig.get("signal_type", ""), "•")
                lines.append(f"   {e} {sig['title'][:80]}")

            lines.append("")

        # Top jobs listing
        if job_sigs:
            lines.append("─" * 36)
            lines.append("💼 <b>Latest Associate Openings</b>")
            for sig in job_sigs[:8]:
                loc = sig.get("location", "ME")
                s   = sig.get("seniority", "")
                r   = f" (via {sig['recruiter']})" if sig.get("recruiter") else ""
                lines.append(f"• <a href='{sig.get('url','#')}'>{sig['title'][:70]}</a>  📍{loc}{r}")

        return "\n".join(lines)

    # ── HTTP sender ───────────────────────────────────────────────────────

    def _send(self, text: str):
        if not self._token or not self._chat_id:
            logger.warning("Telegram credentials missing — skipping send")
            return

        try:
            resp = requests.post(
                TELEGRAM_API.format(token=self._token),
                json={
                    "chat_id":    self._chat_id,
                    "text":       text[:4096],
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=15,
            )
            if resp.ok:
                logger.info("Telegram message sent")
            else:
                logger.warning(f"Telegram error {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
