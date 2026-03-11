"""
Telegram Notifier  (v3)
========================
CRITICAL FIX: All alerts batched into ONE Telegram message per run.
               No more individual per-signal spam (was 16+ messages per run).

FIXED:  Dashboard URL hardcoded to https://middle-east-jobs-tracker.vercel.app/
ADDED:  Top 4 practice areas block in every message
ADDED:  Pending queue — instant alerts are buffered and flushed as one batch
"""
import logging
from datetime import datetime, timezone
from typing import Optional
import requests
from learning.evolution import get_top4_departments

logger = logging.getLogger("alerts.notifier")

TELEGRAM_API  = "https://api.telegram.org/bot{token}/sendMessage"
VERCEL_URL    = "https://middle-east-jobs-tracker.vercel.app/"

SIGNAL_EMOJI = {
    "job_posting":       "💼",
    "recruiter_posting": "🔍",
    "lateral_hire":      "🚀",
    "press_release":     "📢",
    "ranking":           "🏆",
    "regulatory_filing": "🏛",
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

MEDALS = ["🥇", "🥈", "🥉", "4️⃣"]


class Notifier:
    def __init__(self, config):
        self._token   = config.TELEGRAM_BOT_TOKEN
        self._chat_id = config.TELEGRAM_CHAT_ID
        # Always use Vercel URL — env var can override but default is hardcoded
        self._dashboard_url = (
            getattr(config, "DASHBOARD_URL", None) or VERCEL_URL
        )
        if not self._dashboard_url.startswith("http"):
            self._dashboard_url = VERCEL_URL

        # ── FIXED: Buffer instant alerts instead of sending per-signal ────
        self._pending_signals: list[dict] = []
        self._instant_enabled = getattr(config, "INSTANT_ALERT_ON_NEW_JOB", True)

    # ── Public API ─────────────────────────────────────────────────────────

    def queue_instant_alert(self, signal: dict):
        """Buffer a signal. Call flush_instant_alerts() after the run to send ONE message."""
        if self._instant_enabled:
            self._pending_signals.append(signal)

    # Keep backwards-compat alias — but now it just queues, not sends
    def send_instant_alert(self, signal: dict):
        self.queue_instant_alert(signal)

    def flush_instant_alerts(self):
        """Send all queued signals as ONE batched Telegram message."""
        if not self._pending_signals:
            return
        msg = self._format_batched_alerts(self._pending_signals)
        self._send(msg)
        logger.info(f"Flushed {len(self._pending_signals)} alert(s) as single Telegram message")
        self._pending_signals.clear()

    def send_combined_digest(self, expansion_alerts: list, website_changes: list,
                             new_signals: list = None):
        """Weekly digest — ONE message with everything."""
        signals = new_signals or []
        if not expansion_alerts and not signals:
            logger.info("Nothing to digest — skipping Telegram send")
            return
        msg = self._format_digest(expansion_alerts, signals)
        self._send(msg)

    # ── Formatters ─────────────────────────────────────────────────────────

    def _format_batched_alerts(self, signals: list[dict]) -> str:
        """
        Format ALL new signals from a run into ONE compact Telegram message.
        Groups by signal type for readability.
        """
        top4     = get_top4_departments()
        today    = datetime.now(timezone.utc).strftime("%-d %b %Y %H:%M UTC")

        jobs      = [s for s in signals if s.get("signal_type") in ("job_posting", "recruiter_posting")]
        hires     = [s for s in signals if s.get("signal_type") == "lateral_hire"]
        reg       = [s for s in signals if s.get("signal_type") == "regulatory_filing"]
        other     = [s for s in signals if s.get("signal_type") not in
                     ("job_posting","recruiter_posting","lateral_hire","regulatory_filing")]

        lines = [
            "⚖️ <b>ME Legal Jobs — New Signals</b>",
            f"📅 {today}",
            f"🖥 <a href='{self._dashboard_url}'>Open Dashboard</a>",
            "─" * 32,
            f"💼 {len(jobs)} job(s)  🚀 {len(hires)} hire(s)  🏛 {len(reg)} filing(s)",
            "",
        ]

        if jobs:
            lines.append("💼 <b>New Job Openings</b>")
            for s in jobs[:10]:
                loc   = s.get("location","ME")
                dept  = s.get("department","")
                de    = DEPT_EMOJI.get(dept, "⚖️")
                via   = f" · via {s['recruiter']}" if s.get("recruiter") else ""
                url   = s.get("url","#")
                title = s["title"][:65]
                lines.append(f"  {de} <a href='{url}'>{title}</a> 📍{loc}{via}")
            if len(jobs) > 10:
                lines.append(f"  <i>... and {len(jobs)-10} more</i>")
            lines.append("")

        if hires:
            lines.append("🚀 <b>Lateral Hire Signals</b>")
            for s in hires[:5]:
                loc = s.get("location","ME")
                lines.append(f"  • <a href='{s.get('url','#')}'>{s['title'][:70]}</a> 📍{loc}")
            lines.append("")

        if reg:
            lines.append("🏛 <b>Regulatory Filings</b>")
            for s in reg[:3]:
                lines.append(f"  • {s['title'][:80]}")
            lines.append("")

        if other:
            lines.append("📢 <b>Other Signals</b>")
            for s in other[:3]:
                e = SIGNAL_EMOJI.get(s.get("signal_type",""), "•")
                lines.append(f"  {e} {s['title'][:70]}")
            lines.append("")

        # Top 4 practice areas
        if top4:
            lines.append("─" * 32)
            lines.append("📊 <b>Top ME Practice Areas This Week</b>")
            for i, dept in enumerate(top4[:4]):
                d_name  = dept.get("department","")
                d_count = dept.get("signal_count", 0)
                de      = DEPT_EMOJI.get(d_name,"⚖️")
                medal   = MEDALS[i] if i < len(MEDALS) else f"{i+1}."
                lines.append(f"{medal} {de} {d_name} ({d_count} signals)")

        lines.append(f"\n🖥 <a href='{self._dashboard_url}'>Full Dashboard →</a>")
        return "\n".join(lines)

    def _format_digest(self, alerts: list, new_signals: list) -> str:
        top4     = get_top4_departments()
        today    = datetime.now(timezone.utc).strftime("%-d %B %Y")
        job_sigs = [s for s in new_signals if s.get("signal_type") in
                    ("job_posting","recruiter_posting")]
        hire_sigs= [s for s in new_signals if s.get("signal_type") == "lateral_hire"]

        lines = [
            "⚖️ <b>ME Legal Jobs Tracker — Weekly Digest</b>",
            f"Week ending {today}",
            f"🖥 <a href='{self._dashboard_url}'>Open Dashboard →</a>",
            "─" * 36,
            f"💼 {len(job_sigs)} job(s)  🚀 {len(hire_sigs)} hire(s)  📊 {len(alerts)} firm alert(s)",
            "",
        ]

        if top4:
            lines.append("📊 <b>Top 4 ME Practice Areas in Demand</b>")
            for i, dept in enumerate(top4[:4]):
                d_name  = dept.get("department","")
                d_count = dept.get("signal_count", 0)
                d_firms = dept.get("firm_count", 0)
                de      = DEPT_EMOJI.get(d_name,"⚖️")
                medal   = MEDALS[i] if i < len(MEDALS) else f"{i+1}."
                lines.append(f"{medal} {de} <b>{d_name}</b>  {d_count} signals · {d_firms} firm(s)")
            lines.append("")

        lines.append("─" * 36)
        for i, alert in enumerate(alerts[:10], 1):
            de  = DEPT_EMOJI.get(alert["department"],"⚖️")
            loc = alert.get("location","Middle East")
            lines += [
                f"{i}. 🏛 <b>{alert['firm_name']}</b>",
                f"   {de} {alert['department']} — 📍 {loc}",
                f"   Score: {alert['expansion_score']}  |  {alert['signal_count']} signal(s)",
            ]
            for sig in alert.get("signals",[])[:3]:
                e = SIGNAL_EMOJI.get(sig.get("signal_type",""), "•")
                lines.append(f"   {e} {sig['title'][:75]}")
            lines.append("")

        if job_sigs:
            lines.append("─" * 36)
            lines.append("💼 <b>Latest Associate Openings</b>")
            for sig in job_sigs[:8]:
                loc = sig.get("location","ME")
                r   = f" (via {sig['recruiter']})" if sig.get("recruiter") else ""
                de  = DEPT_EMOJI.get(sig.get("department",""),"⚖️")
                lines.append(
                    f"• {de} <a href='{sig.get('url','#')}'>{sig['title'][:65]}</a>  📍{loc}{r}"
                )

        lines.append(f"\n🖥 <a href='{self._dashboard_url}'>View full dashboard →</a>")
        return "\n".join(lines)

    # ── HTTP sender ────────────────────────────────────────────────────────

    def _send(self, text: str):
        if not self._token or not self._chat_id:
            logger.warning("Telegram credentials missing — skipping send")
            return
        # Split into ≤4096 char chunks if needed
        chunks = [text[i:i+4090] for i in range(0, len(text), 4090)]
        for chunk in chunks:
            try:
                resp = requests.post(
                    TELEGRAM_API.format(token=self._token),
                    json={
                        "chat_id":    self._chat_id,
                        "text":       chunk,
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
