"""
Telegram Notifier  (v2)
========================
FIXED: Dashboard URL now correctly points to Vercel deployment
ADDED: Top 4 ME practice areas in demand shown in every alert and digest
"""

import logging
import json
from datetime import datetime, timezone

import requests

from learning.evolution import get_top4_departments

logger = logging.getLogger("alerts.notifier")

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
VERCEL_URL   = "https://middle-east-jobs-tracker.vercel.app/"

SIGNAL_EMOJI = {
    "job_posting":       "💼",
    "recruiter_posting": "🔍",
    "lateral_hire":      "🚀",
    "press_release":     "📢",
    "ranking":           "🏆",
    "website_snapshot":  "🌐",
}

DEPT_EMOJI = {
    "Corporate / M&A":                "🤝",
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
        # Always use Vercel URL, but allow env override
        self._dashboard_url = getattr(config, "DASHBOARD_URL", VERCEL_URL) or VERCEL_URL
        if not self._dashboard_url.startswith("http"):
            self._dashboard_url = VERCEL_URL
        self._instant = config.INSTANT_ALERT_ON_NEW_JOB

    # ── Public interface ──────────────────────────────────────────────────

    def send_instant_alert(self, signal: dict):
        if not self._instant:
            return
        msg = self._format_instant(signal)
        self._send(msg)

    def send_combined_digest(self, expansion_alerts, website_changes,
                             new_signals=None):
        if not expansion_alerts and not (new_signals or []):
            logger.info("Nothing to digest — skipping Telegram send")
            return
        msg = self._format_digest(expansion_alerts, new_signals or [])
        self._send(msg)

    # ── Formatters ────────────────────────────────────────────────────────

    def _format_instant(self, signal: dict) -> str:
        emoji     = SIGNAL_EMOJI.get(signal.get("signal_type", ""), "📌")
        dept_e    = DEPT_EMOJI.get(signal.get("department", ""), "⚖️")
        loc       = signal.get("location", "Middle East")
        seniority = signal.get("seniority", "Associate")
        recruiter = signal.get("recruiter", "")
        top4      = get_top4_departments()

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
            f"📝 {signal['title'][:90]}",
            f"🔗 <a href='{signal.get('url','#')}'>View Posting</a>",
            "",
        ]

        # ── Top 4 Practice Areas ──────────────────────────────────────────
        if top4:
            lines.append("📊 <b>Top ME Practice Areas This Week</b>")
            medals = ["🥇", "🥈", "🥉", "4️⃣"]
            for i, dept in enumerate(top4[:4]):
                d_name  = dept.get("department", "")
                d_count = dept.get("signal_count", 0)
                d_emoji = DEPT_EMOJI.get(d_name, "⚖️")
                medal   = medals[i] if i < len(medals) else f"{i+1}."
                lines.append(f"{medal} {d_emoji} {d_name}  ({d_count} signals)")
            lines.append("")

        lines.append(f"🖥 <a href='{self._dashboard_url}'>Open Dashboard →</a>")
        return "\n".join(lines)

    def _format_digest(self, alerts: list, new_signals: list) -> str:
        today     = datetime.now(timezone.utc).strftime("%-d %B %Y")
        job_sigs  = [s for s in new_signals
                     if s.get("signal_type") in ("job_posting", "recruiter_posting")]
        hire_sigs = [s for s in new_signals if s.get("signal_type") == "lateral_hire"]
        top4      = get_top4_departments()

        lines = [
            "⚖️ <b>ME Legal Jobs Tracker — Weekly Digest</b>",
            f"Week ending {today}",
            f"🖥 <a href='{self._dashboard_url}'>Open Dashboard →</a>",
            "─" * 36,
            f"💼 {len(job_sigs)} new job posting(s)  |  🚀 {len(hire_sigs)} lateral hire(s)",
            f"📊 {len(alerts)} firm-department alert(s)",
            "",
        ]

        # ── Top 4 Practice Areas Block ─────────────────────────────────────
        if top4:
            lines.append("📊 <b>Top 4 ME Practice Areas in Demand</b>")
            medals = ["🥇", "🥈", "🥉", "4️⃣"]
            for i, dept in enumerate(top4[:4]):
                d_name   = dept.get("department", "")
                d_count  = dept.get("signal_count", 0)
                d_firms  = dept.get("firm_count", 0)
                d_emoji  = DEPT_EMOJI.get(d_name, "⚖️")
                medal    = medals[i] if i < len(medals) else f"{i+1}."
                firm_str = f" · {d_firms} firm(s)" if d_firms else ""
                lines.append(f"{medal} {d_emoji} <b>{d_name}</b>  {d_count} signals{firm_str}")
            lines.append("")

        lines.append("─" * 36)

        # ── Firm expansion alerts ──────────────────────────────────────────
        for i, alert in enumerate(alerts[:10], 1):
            dept_e  = DEPT_EMOJI.get(alert["department"], "⚖️")
            loc     = alert.get("location", "Middle East")
            bkd     = alert.get("signal_breakdown", {})
            bkd_str = "  ".join(f"{v}×{k.replace('_',' ')}" for k, v in bkd.items())
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

        # ── Latest associate openings ──────────────────────────────────────
        if job_sigs:
            lines.append("─" * 36)
            lines.append("💼 <b>Latest Associate Openings</b>")
            for sig in job_sigs[:8]:
                loc = sig.get("location", "ME")
                r   = f" (via {sig['recruiter']})" if sig.get("recruiter") else ""
                dept_e = DEPT_EMOJI.get(sig.get("department",""), "⚖️")
                lines.append(
                    f"• {dept_e} <a href='{sig.get('url','#')}'>"
                    f"{sig['title'][:65]}</a>  📍{loc}{r}"
                )

        lines.append(f"\n🖥 <a href='{self._dashboard_url}'>View full dashboard →</a>")
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
