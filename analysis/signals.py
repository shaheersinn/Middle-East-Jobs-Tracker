"""
Signal Analyzer
================
Aggregates raw signals into firm-level hiring / expansion scores.

Scoring methodology:
  - Each signal carries a department_score (weight × dept match)
  - Signals are bucketed by (firm, department, location)
  - Weekly score = sum of department_scores in the last 7 days
  - Spike detection uses z-score over a 4-week rolling baseline

Signal type weights:
  recruiter_posting  4.0  (recruiter is paid to fill the role — high confidence)
  lateral_hire       3.5  (confirmed person movement)
  ranking            3.0  (independent validation of ME presence)
  job_posting        2.5  (firm is actively hiring)
  press_release      2.0  (firm announcement)
  website_snapshot   2.0  (practice page change)
"""

import logging
import statistics
from collections import defaultdict
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("analysis.signals")

SIGNAL_WEIGHTS = {
    "recruiter_posting": 4.0,
    "lateral_hire":      3.5,
    "ranking":           3.0,
    "job_posting":       2.5,
    "website_snapshot":  2.0,
    "press_release":     2.0,
}


class ExpansionAnalyzer:
    def __init__(self, db):
        self._db = db

    def analyze(self, weekly_signals: list[dict]) -> list[dict]:
        """
        Group signals by (firm, department, location) and produce
        ranked expansion alerts.
        """
        groups = defaultdict(list)
        for sig in weekly_signals:
            key = (sig["firm_id"], sig.get("department", ""), sig.get("location", ""))
            groups[key].append(sig)

        alerts = []
        for (firm_id, dept, location), sigs in groups.items():
            score = self._compute_score(sigs)
            if score < 2.0:
                continue

            breakdown = self._breakdown(sigs)
            alerts.append({
                "firm_id":        firm_id,
                "firm_name":      sigs[0]["firm_name"],
                "department":     dept,
                "location":       location,
                "expansion_score": round(score, 2),
                "signal_count":   len(sigs),
                "signal_breakdown": breakdown,
                "signals":        sigs,
            })

        alerts.sort(key=lambda a: a["expansion_score"], reverse=True)
        logger.info(f"Produced {len(alerts)} expansion alert(s)")
        return alerts

    def _compute_score(self, signals: list[dict]) -> float:
        total = 0.0
        for sig in signals:
            type_weight = SIGNAL_WEIGHTS.get(sig.get("signal_type", ""), 1.0)
            dept_score  = float(sig.get("department_score", 1.0))
            total += type_weight * dept_score
        return total

    def _breakdown(self, signals: list[dict]) -> dict:
        counts: dict[str, int] = defaultdict(int)
        for sig in signals:
            counts[sig.get("signal_type", "unknown")] += 1
        return dict(counts)

    def detect_website_changes(self, signals: list[dict]) -> list[dict]:
        return [s for s in signals if s.get("signal_type") == "website_snapshot"]

    def top_jobs(self, signals: list[dict], limit: int = 20) -> list[dict]:
        """Return most recent / highest-scored job / recruiter signals."""
        job_sigs = [
            s for s in signals
            if s.get("signal_type") in ("job_posting", "recruiter_posting")
        ]
        job_sigs.sort(key=lambda s: s.get("department_score", 0), reverse=True)
        return job_sigs[:limit]
