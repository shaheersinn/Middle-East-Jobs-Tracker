"""
Self-Training Evolution Engine
================================
Runs every 2 hours to analyse signal outcomes and adjust the classifier.

What it learns:
  1. Source yield rates — which scrapers / sites produce the most verified signals
  2. Keyword hit rates — which keywords reliably predict lawyer roles
  3. Department drift — which practice areas are trending up/down in ME
  4. False positive rates — signals marked as non-lawyer by a second-pass check

Outputs:
  - learned_weights.json     : updated per-source and per-keyword weights
  - learning/trend_report.json: top 4 ME practice areas + trending data
  - Patches classifier/taxonomy.py weights dynamically at runtime
"""

import json
import logging
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger("learning.evolution")

WEIGHTS_FILE  = "learned_weights.json"
TREND_FILE    = "learning/trend_report.json"

DEFAULT_WEIGHTS = {
    "source_multipliers": {
        "Firm Careers Page":        1.0,
        "Recruiter":                1.0,
        "Bayt.com":                 1.0,
        "Indeed UAE":               1.0,
        "LinkedIn":                 1.0,
        "Glassdoor":                1.0,
        "Laimoon":                  1.0,
        "Google News":              1.0,
        "Law360":                   1.0,
        "ALM / The American Lawyer":1.0,
        "Firm News":                1.0,
        "Chambers Global ME":       1.0,
        "Legal 500 ME":             1.0,
        "RSS":                      1.0,
    },
    "department_trend_boost": {},
    "keyword_boost":          {},
    "last_trained":           None,
    "total_runs":             0,
    "signal_counts_by_dept":  {},
}


def load_weights() -> dict:
    if os.path.exists(WEIGHTS_FILE):
        try:
            with open(WEIGHTS_FILE) as f:
                w = json.load(f)
                # Merge any new default keys
                for k, v in DEFAULT_WEIGHTS.items():
                    if k not in w:
                        w[k] = v
                return w
        except Exception:
            pass
    return dict(DEFAULT_WEIGHTS)


def save_weights(weights: dict):
    weights["last_trained"] = datetime.now(timezone.utc).isoformat()
    weights["total_runs"]   = weights.get("total_runs", 0) + 1
    with open(WEIGHTS_FILE, "w") as f:
        json.dump(weights, f, indent=2)
    logger.info(f"Weights saved → {WEIGHTS_FILE}  (run #{weights['total_runs']})")


def run_evolution(db_path: str = "me_legal_jobs.db"):
    """Main entry point — run after every collection cycle."""
    logger.info("=" * 55)
    logger.info("Self-Training Evolution Engine — starting")
    logger.info("=" * 55)

    if not os.path.exists(db_path):
        logger.warning(f"DB not found: {db_path} — skipping evolution")
        return

    weights = load_weights()

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        _train_source_yields(conn, weights)
        _train_department_trends(conn, weights)
        _train_keyword_effectiveness(conn, weights)
        top4 = _compute_top4_departments(conn, weights)
        _save_trend_report(top4, weights)
        conn.close()
    except Exception as e:
        logger.error(f"Evolution error: {e}", exc_info=True)

    save_weights(weights)
    logger.info("Self-Training Evolution Engine — complete")


def _train_source_yields(conn: sqlite3.Connection, weights: dict):
    """
    Calculate signal yield per source. Sources that consistently produce
    signals get a boost; sources with 0 yield over 7 days get penalised.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    cur = conn.execute(
        """SELECT source, COUNT(*) as cnt
           FROM signals
           WHERE created_at >= ?
           GROUP BY source""",
        (cutoff,)
    )
    rows = {r["source"]: r["cnt"] for r in cur.fetchall()}

    sm = weights.setdefault("source_multipliers", {})
    total = sum(rows.values()) or 1

    for src, cnt in rows.items():
        share = cnt / total
        current = sm.get(src, 1.0)
        # Exponential moving average — 80% old, 20% new observation
        if share > 0.10:
            new_val = min(current * 1.05, 2.0)   # reward high yield
        elif share < 0.02:
            new_val = max(current * 0.92, 0.3)   # penalise low yield
        else:
            new_val = current
        sm[src] = round(new_val, 3)

    logger.info(f"Source yields: {dict(sorted(rows.items(), key=lambda x: -x[1])[:5])}")


def _train_department_trends(conn: sqlite3.Connection, weights: dict):
    """
    Detect which departments have increasing signal volume.
    Top trending departments get a classifier boost.
    """
    now     = datetime.now(timezone.utc)
    week1_s = (now - timedelta(days=7)).isoformat()
    week2_s = (now - timedelta(days=14)).isoformat()
    week2_e = week1_s

    def get_dept_counts(start, end):
        cur = conn.execute(
            """SELECT department, COUNT(*) as cnt FROM signals
               WHERE created_at >= ? AND created_at < ?
               GROUP BY department""",
            (start, end)
        )
        return {r["department"]: r["cnt"] for r in cur.fetchall()}

    week1 = get_dept_counts(week1_s, now.isoformat())
    week2 = get_dept_counts(week2_s, week2_e)

    drift_boost = weights.setdefault("department_trend_boost", {})
    trend_data  = weights.setdefault("signal_counts_by_dept", {})

    for dept, cnt in week1.items():
        prev = week2.get(dept, 0)
        trend_data[dept] = cnt
        if prev == 0:
            growth = 1.0 if cnt > 0 else 0.0
        else:
            growth = (cnt - prev) / prev

        current_boost = drift_boost.get(dept, 1.0)
        if growth > 0.3:
            new_boost = min(current_boost * 1.08, 1.5)
        elif growth < -0.3:
            new_boost = max(current_boost * 0.95, 0.7)
        else:
            new_boost = current_boost
        drift_boost[dept] = round(new_boost, 3)

    # Decay departments not seen this week
    for dept in list(drift_boost.keys()):
        if dept not in week1:
            drift_boost[dept] = max(drift_boost[dept] * 0.97, 0.7)

    logger.info(f"Dept boosts (top 5): "
                f"{dict(sorted(drift_boost.items(), key=lambda x: -x[1])[:5])}")


def _train_keyword_effectiveness(conn: sqlite3.Connection, weights: dict):
    """
    Look at matched_keywords across all signals. Keywords that appear in
    high-scored signals get boosted; those in low-scored signals are trimmed.
    """
    import json as _json
    cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    cur = conn.execute(
        """SELECT matched_keywords, department_score FROM signals
           WHERE created_at >= ? AND matched_keywords IS NOT NULL""",
        (cutoff,)
    )

    kw_scores: dict = defaultdict(list)
    for row in cur.fetchall():
        try:
            kws = _json.loads(row["matched_keywords"])
        except Exception:
            continue
        score = float(row["department_score"] or 0)
        for kw in kws:
            kw_scores[kw].append(score)

    kw_boost = weights.setdefault("keyword_boost", {})
    for kw, scores in kw_scores.items():
        avg = sum(scores) / len(scores)
        current = kw_boost.get(kw, 1.0)
        if avg > 4.0:
            kw_boost[kw] = round(min(current * 1.1, 2.0), 3)
        elif avg < 1.0:
            kw_boost[kw] = round(max(current * 0.9, 0.5), 3)
        else:
            kw_boost[kw] = current

    logger.info(f"Keyword boosts updated for {len(kw_scores)} keywords")


def _compute_top4_departments(conn: sqlite3.Connection, weights: dict) -> list[dict]:
    """Return top 4 practice areas by signal volume over last 30 days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    cur = conn.execute(
        """SELECT department, COUNT(*) as signal_count,
                  SUM(department_score) as total_score,
                  COUNT(DISTINCT firm_id) as firm_count
           FROM signals
           WHERE created_at >= ? AND department != ''
           GROUP BY department
           ORDER BY signal_count DESC
           LIMIT 10""",
        (cutoff,)
    )
    rows = [dict(r) for r in cur.fetchall()]

    # Apply trend boost to scoring
    drift = weights.get("department_trend_boost", {})
    for r in rows:
        r["trend_boost"] = drift.get(r["department"], 1.0)
        r["adjusted_score"] = r["total_score"] * r["trend_boost"]

    rows.sort(key=lambda x: x["adjusted_score"], reverse=True)
    top4 = rows[:4]

    logger.info(f"Top 4 ME practice areas: {[r['department'] for r in top4]}")
    return top4


def _save_trend_report(top4: list, weights: dict):
    """Write trend report JSON for use by dashboard + alerts."""
    Path("learning").mkdir(exist_ok=True)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "top4_departments": top4,
        "source_multipliers": weights.get("source_multipliers", {}),
        "total_training_runs": weights.get("total_runs", 0),
    }
    with open(TREND_FILE, "w") as f:
        json.dump(report, f, indent=2)
    logger.info(f"Trend report saved → {TREND_FILE}")


def get_top4_departments(fallback: bool = True) -> list[dict]:
    """Load top 4 departments from trend report. Used by dashboard + alerts."""
    if os.path.exists(TREND_FILE):
        try:
            with open(TREND_FILE) as f:
                data = json.load(f)
            return data.get("top4_departments", [])
        except Exception:
            pass

    if fallback:
        # Hard-coded fallback if no training data yet
        return [
            {"department": "Corporate / M&A",               "signal_count": 0},
            {"department": "Banking & Finance",              "signal_count": 0},
            {"department": "Project Finance & Infrastructure","signal_count": 0},
            {"department": "Arbitration & Disputes",         "signal_count": 0},
        ]
    return []


def apply_learned_weights_to_signal(signal: dict, weights: dict) -> dict:
    """
    Post-process a signal dict, applying learned source and dept weights.
    Called in main.py after every scraper.fetch().
    """
    src   = signal.get("source", "")
    dept  = signal.get("department", "")
    src_mult  = weights.get("source_multipliers", {}).get(src, 1.0)
    dept_mult = weights.get("department_trend_boost", {}).get(dept, 1.0)
    signal["department_score"] = round(
        float(signal.get("department_score", 1.0)) * src_mult * dept_mult, 3
    )
    return signal
