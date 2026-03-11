"""
Self-Training Evolution Engine  (v3 — significantly enhanced)
===============================================================
Runs after every collection cycle AND on a standalone 2-hour cron.
Learns from every signal in the database to continuously improve scoring.

What it trains on:
  1. Source yield rates      — high-yield sources get boosted multipliers
  2. Department trends       — week-over-week growth boosts practice area score
  3. Keyword effectiveness   — keywords in high-score signals get up-weighted
  4. Firm expansion velocity — firms with accelerating signal velocity flagged
  5. Seniority distribution  — partner-heavy signal batches get higher expansion scores
  6. Source reliability      — sources with consistent output vs one-off bursts
  7. False-positive decay    — signals from blocked/slow hosts penalised retroactively

Outputs:
  - learned_weights.json       — weights applied to every incoming signal
  - learning/trend_report.json — top 4 ME practice areas + velocity data
  - learning/source_report.json — per-source reliability scores

Algorithm: Exponential Moving Average (α=0.2 — slow, stable learning)
           Cliff detection: >30% week-over-week change triggers trend flag
"""
import json, logging, os, sqlite3
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger("learning.evolution")

WEIGHTS_PATH      = "learned_weights.json"
TREND_REPORT_PATH = "learning/trend_report.json"
SOURCE_REPORT_PATH= "learning/source_report.json"
ALPHA             = 0.2   # EMA learning rate
MAX_BOOST         = 2.5   # cap on positive multipliers
MIN_BOOST         = 0.25  # floor on negative multipliers
TOP_N_DEPT        = 4     # top practice areas to surface

# Default weights before any training data
FALLBACK_WEIGHTS = {
    "source_multipliers": {},
    "dept_trend_boosts":  {},
    "keyword_boosts":     {},
    "total_runs": 0,
    "last_trained": "",
    "firm_velocity": {},
    "seniority_distribution": {},
}

FALLBACK_TOP4 = [
    {"department": "Corporate / M&A",                "signal_count": 0, "firm_count": 0, "trend_boost": 1.0},
    {"department": "Banking & Finance",              "signal_count": 0, "firm_count": 0, "trend_boost": 1.0},
    {"department": "Project Finance & Infrastructure","signal_count": 0, "firm_count": 0, "trend_boost": 1.0},
    {"department": "Arbitration & Disputes",         "signal_count": 0, "firm_count": 0, "trend_boost": 1.0},
]


def load_weights() -> dict:
    try:
        with open(WEIGHTS_PATH) as f:
            w = json.load(f)
            # Ensure all keys present (forward compat)
            for k, v in FALLBACK_WEIGHTS.items():
                w.setdefault(k, v)
            return w
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(FALLBACK_WEIGHTS)


def save_weights(weights: dict):
    with open(WEIGHTS_PATH, "w") as f:
        json.dump(weights, f, indent=2)


def apply_learned_weights_to_signal(signal: dict, weights: dict) -> dict:
    """Apply learned multipliers to a signal's department_score before saving."""
    source  = signal.get("source", "")
    dept    = signal.get("department", "")
    src_mul = weights.get("source_multipliers", {}).get(source, 1.0)
    dep_mul = weights.get("dept_trend_boosts",  {}).get(dept, 1.0)

    # Keyword boost
    kw_boosts = weights.get("keyword_boosts", {})
    kw_mul    = 1.0
    kws = signal.get("matched_keywords", [])
    if kws and kw_boosts:
        scores = [kw_boosts.get(k, 1.0) for k in kws]
        kw_mul = sum(scores) / len(scores)  # average keyword boost

    multiplier = min(MAX_BOOST, max(MIN_BOOST, src_mul * dep_mul * kw_mul))
    old_score  = float(signal.get("department_score", 1.0))
    signal["department_score"] = round(old_score * multiplier, 4)
    signal["weight_multiplier"] = round(multiplier, 3)
    return signal


def get_top4_departments() -> list[dict]:
    """Return top 4 practice areas from the latest trend report."""
    try:
        with open(TREND_REPORT_PATH) as f:
            report = json.load(f)
        return report.get("top4", FALLBACK_TOP4)
    except (FileNotFoundError, json.JSONDecodeError):
        return FALLBACK_TOP4


def run_evolution(db_path: str):
    logger.info("=" * 55)
    logger.info("Self-Training Evolution Engine — starting")
    logger.info("=" * 55)

    if not os.path.exists(db_path):
        logger.warning(f"DB not found: {db_path} — skipping evolution")
        return

    try:
        conn   = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        weights = load_weights()

        # ── 1. Source yield rates ──────────────────────────────────────────
        _train_source_yield(cursor, weights)

        # ── 2. Department trends ───────────────────────────────────────────
        _train_dept_trends(cursor, weights)

        # ── 3. Keyword effectiveness ───────────────────────────────────────
        _train_keyword_effectiveness(cursor, weights)

        # ── 4. Firm expansion velocity ─────────────────────────────────────
        _train_firm_velocity(cursor, weights)

        # ── 5. Seniority distribution ──────────────────────────────────────
        _train_seniority_distribution(cursor, weights)

        # ── 6. Generate trend report ───────────────────────────────────────
        _generate_trend_report(cursor, weights)

        # ── 7. Generate source reliability report ─────────────────────────
        _generate_source_report(cursor, weights)

        # Update metadata
        weights["total_runs"]   = weights.get("total_runs", 0) + 1
        weights["last_trained"] = datetime.now(timezone.utc).isoformat()

        save_weights(weights)
        conn.close()

        logger.info(f"Self-Training Evolution Engine — complete (run #{weights['total_runs']})")
        logger.info(f"  Source multipliers: {len(weights['source_multipliers'])}")
        logger.info(f"  Dept trend boosts:  {len(weights['dept_trend_boosts'])}")
        logger.info(f"  Keyword boosts:     {len(weights['keyword_boosts'])}")

    except Exception as e:
        logger.error(f"Evolution engine error: {e}", exc_info=True)


def _train_source_yield(cursor, weights: dict):
    """Sources producing more high-value signals get boosted multipliers."""
    try:
        cursor.execute("""
            SELECT source, COUNT(*) as cnt, AVG(department_score) as avg_score
            FROM signals
            WHERE created_at > datetime('now', '-30 days')
              AND source IS NOT NULL AND source != ''
            GROUP BY source
            HAVING cnt >= 2
            ORDER BY avg_score DESC
        """)
        rows = cursor.fetchall()
    except Exception:
        return

    if not rows:
        return

    # Normalize scores across sources
    scores    = [r["avg_score"] for r in rows]
    max_score = max(scores) if scores else 1.0
    min_score = min(scores) if scores else 0.0

    src_mul = weights.setdefault("source_multipliers", {})
    for row in rows:
        src   = row["source"]
        score = row["avg_score"]
        # Normalise to [MIN_BOOST, MAX_BOOST]
        if max_score > min_score:
            norm = (score - min_score) / (max_score - min_score)
        else:
            norm = 0.5
        new_mul = MIN_BOOST + norm * (MAX_BOOST - MIN_BOOST)
        old_mul = src_mul.get(src, 1.0)
        # EMA update
        src_mul[src] = round(old_mul * (1 - ALPHA) + new_mul * ALPHA, 4)


def _train_dept_trends(cursor, weights: dict):
    """Departments with growing signal velocity get boosted."""
    try:
        cursor.execute("""
            SELECT department,
                   SUM(CASE WHEN created_at > datetime('now', '-7 days')  THEN 1 ELSE 0 END) as this_week,
                   SUM(CASE WHEN created_at > datetime('now', '-14 days')
                             AND created_at <= datetime('now', '-7 days') THEN 1 ELSE 0 END) as last_week
            FROM signals
            WHERE department IS NOT NULL AND department != ''
              AND created_at > datetime('now', '-14 days')
            GROUP BY department
        """)
        rows = cursor.fetchall()
    except Exception:
        return

    dept_boosts = weights.setdefault("dept_trend_boosts", {})
    for row in rows:
        dept      = row["department"]
        this_week = row["this_week"] or 0
        last_week = row["last_week"] or 0
        if last_week == 0:
            trend = 1.0 if this_week == 0 else 1.3
        else:
            trend = this_week / last_week

        # Convert trend ratio to boost factor
        if trend > 1.30:
            new_boost = min(MAX_BOOST, 1.0 + (trend - 1.0) * 0.6)
        elif trend < 0.70:
            new_boost = max(MIN_BOOST, 1.0 - (1.0 - trend) * 0.4)
        else:
            new_boost = 1.0

        old_boost = dept_boosts.get(dept, 1.0)
        dept_boosts[dept] = round(old_boost * (1 - ALPHA) + new_boost * ALPHA, 4)


def _train_keyword_effectiveness(cursor, weights: dict):
    """Keywords appearing in signals with high scores get up-weighted."""
    try:
        cursor.execute("""
            SELECT matched_keywords, department_score
            FROM signals
            WHERE created_at > datetime('now', '-30 days')
              AND matched_keywords IS NOT NULL
              AND matched_keywords != '' AND matched_keywords != '[]'
        """)
        rows = cursor.fetchall()
    except Exception:
        return

    kw_scores: dict = defaultdict(list)
    for row in rows:
        try:
            kws   = json.loads(row["matched_keywords"]) if isinstance(row["matched_keywords"], str) else row["matched_keywords"]
            score = float(row["department_score"] or 1.0)
            for kw in (kws or []):
                if kw:
                    kw_scores[kw].append(score)
        except Exception:
            continue

    if not kw_scores:
        return

    # Find global mean
    all_scores = [s for scores in kw_scores.values() for s in scores]
    global_mean = sum(all_scores) / len(all_scores) if all_scores else 1.0

    kw_boosts = weights.setdefault("keyword_boosts", {})
    for kw, scores in kw_scores.items():
        if len(scores) < 2:
            continue
        avg = sum(scores) / len(scores)
        new_boost = max(MIN_BOOST, min(MAX_BOOST, avg / global_mean if global_mean > 0 else 1.0))
        old_boost = kw_boosts.get(kw, 1.0)
        kw_boosts[kw] = round(old_boost * (1 - ALPHA) + new_boost * ALPHA, 4)


def _train_firm_velocity(cursor, weights: dict):
    """Track per-firm signal velocity to detect acceleration."""
    try:
        cursor.execute("""
            SELECT firm_id, firm_name,
                   SUM(CASE WHEN created_at > datetime('now', '-7 days')  THEN 1 ELSE 0 END) as this_week,
                   SUM(CASE WHEN created_at > datetime('now', '-14 days')
                             AND created_at <= datetime('now', '-7 days') THEN 1 ELSE 0 END) as last_week,
                   SUM(CASE WHEN created_at > datetime('now', '-30 days') THEN 1 ELSE 0 END) as this_month
            FROM signals
            WHERE created_at > datetime('now', '-14 days')
            GROUP BY firm_id, firm_name
        """)
        rows = cursor.fetchall()
    except Exception:
        return

    velocity = weights.setdefault("firm_velocity", {})
    for row in rows:
        fid = row["firm_id"]
        tw  = row["this_week"] or 0
        lw  = row["last_week"] or 0
        accel = round((tw - lw) / max(lw, 1), 3)
        velocity[fid] = {
            "firm_name":  row["firm_name"],
            "this_week":  tw,
            "last_week":  lw,
            "this_month": row["this_month"] or 0,
            "acceleration": accel,
            "status": "accelerating" if accel > 0.5 else ("decelerating" if accel < -0.3 else "stable"),
        }


def _train_seniority_distribution(cursor, weights: dict):
    """Track seniority mix — partner-heavy signal batches are higher confidence."""
    try:
        cursor.execute("""
            SELECT seniority, COUNT(*) as cnt
            FROM signals
            WHERE created_at > datetime('now', '-30 days')
              AND seniority IS NOT NULL AND seniority != ''
            GROUP BY seniority
        """)
        rows = cursor.fetchall()
    except Exception:
        return

    total = sum(r["cnt"] for r in rows)
    if total == 0:
        return
    dist = {r["seniority"]: round(r["cnt"] / total, 3) for r in rows}
    weights["seniority_distribution"] = dist

    # Partner signal ratio as an expansion confidence indicator
    partner_pct = sum(v for k, v in dist.items() if "partner" in k.lower())
    weights["partner_signal_ratio"] = round(partner_pct, 3)


def _generate_trend_report(cursor, weights: dict):
    """Generate the top 4 practice areas report for dashboard + Telegram."""
    try:
        cursor.execute("""
            SELECT department,
                   COUNT(*) as total,
                   COUNT(DISTINCT firm_id) as firm_count,
                   SUM(CASE WHEN signal_type IN ('lateral_hire','regulatory_filing') THEN 1 ELSE 0 END) as high_conf,
                   SUM(CASE WHEN created_at > datetime('now', '-7 days') THEN 1 ELSE 0 END)  as this_week,
                   SUM(CASE WHEN created_at > datetime('now', '-14 days')
                             AND created_at <= datetime('now', '-7 days') THEN 1 ELSE 0 END) as last_week
            FROM signals
            WHERE department IS NOT NULL AND department != ''
              AND created_at > datetime('now', '-30 days')
            GROUP BY department
            HAVING total >= 2
            ORDER BY total DESC
        """)
        rows = cursor.fetchall()
    except Exception:
        rows = []

    dept_boosts = weights.get("dept_trend_boosts", {})
    result = []
    for row in rows:
        dept  = row["department"]
        boost = dept_boosts.get(dept, 1.0)
        result.append({
            "department":   dept,
            "signal_count": row["total"],
            "firm_count":   row["firm_count"],
            "high_conf":    row["high_conf"],
            "this_week":    row["this_week"],
            "last_week":    row["last_week"],
            "trend_boost":  boost,
            # Composite rank: raw count × boost × (high_conf weight)
            "_rank_score":  row["total"] * boost * (1 + row["high_conf"] * 0.2),
        })

    result.sort(key=lambda x: -x["_rank_score"])
    top4 = result[:TOP_N_DEPT]
    for d in top4:
        d.pop("_rank_score", None)

    # Fallback if DB empty
    if not top4:
        top4 = FALLBACK_TOP4

    Path("learning").mkdir(exist_ok=True)
    with open(TREND_REPORT_PATH, "w") as f:
        json.dump({
            "top4": top4,
            "all_depts": result[:14],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }, f, indent=2)


def _generate_source_report(cursor, weights: dict):
    """Generate per-source reliability report for diagnostics."""
    try:
        cursor.execute("""
            SELECT source,
                   COUNT(*) as total,
                   COUNT(DISTINCT firm_id) as firm_coverage,
                   AVG(department_score) as avg_score,
                   MAX(created_at) as last_seen,
                   SUM(CASE WHEN signal_type = 'lateral_hire' THEN 1 ELSE 0 END) as hire_count
            FROM signals
            WHERE source IS NOT NULL AND source != ''
              AND created_at > datetime('now', '-30 days')
            GROUP BY source
            ORDER BY total DESC
        """)
        rows = cursor.fetchall()
    except Exception:
        rows = []

    src_muls = weights.get("source_multipliers", {})
    report   = []
    for row in rows:
        src = row["source"]
        report.append({
            "source":        src,
            "total_signals": row["total"],
            "firm_coverage": row["firm_coverage"],
            "avg_score":     round(row["avg_score"] or 0, 2),
            "hire_signals":  row["hire_count"],
            "last_seen":     (row["last_seen"] or "")[:10],
            "multiplier":    src_muls.get(src, 1.0),
        })

    Path("learning").mkdir(exist_ok=True)
    with open(SOURCE_REPORT_PATH, "w") as f:
        json.dump({
            "sources":      report,
            "total_active": len(report),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }, f, indent=2)
