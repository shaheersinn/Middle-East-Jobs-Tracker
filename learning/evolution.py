"""
Self-Training Evolution Engine  (v4 — 12 training dimensions)
==============================================================
Runs after every collection cycle AND on a standalone 2-hour cron.
Learns from every signal in the database to continuously improve scoring.

Training dimensions (12 total):
  1.  Source yield rates         — high-yield sources get boosted multipliers
  2.  Department trends          — week-over-week growth boosts practice area score
  3.  Keyword effectiveness      — keywords in high-score signals get up-weighted
  4.  Firm expansion velocity    — firms with accelerating signal velocity flagged
  5.  Seniority distribution     — partner-heavy signal batches higher expansion score
  6.  Source reliability         — consistent sources vs one-off bursts
  7.  False-positive decay       — blocked/slow-host signals penalised retroactively
  8.  Geographic hotspot         — ME cities heating up get geo-boost multiplier
  9.  Cross-source deduplication — same job from multiple sources = higher confidence
 10.  Time-pattern analysis      — learn which days/hours produce highest quality
 11.  Cross-firm correlation     — when firm A hires in dept X, peer firms follow
 12.  Prediction accuracy        — compare past expansion predictions vs. reality

Outputs:
  - learned_weights.json        — weights applied to every incoming signal
  - learning/trend_report.json  — top 4 ME practice areas + velocity data
  - learning/source_report.json — per-source reliability scores
  - learning/geo_report.json    — geographic hotspot heatmap
  - learning/accuracy_report.json — model self-assessment

Algorithm: Exponential Moving Average (α=0.2 — slow, stable learning)
           Cliff detection: >30% week-over-week change triggers trend flag
"""
import json, logging, os, sqlite3
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger("learning.evolution")

WEIGHTS_PATH        = "learned_weights.json"
TREND_REPORT_PATH   = "learning/trend_report.json"
SOURCE_REPORT_PATH  = "learning/source_report.json"
GEO_REPORT_PATH     = "learning/geo_report.json"
ACCURACY_REPORT_PATH= "learning/accuracy_report.json"
ALPHA               = 0.2   # EMA learning rate
MAX_BOOST           = 2.5   # cap on positive multipliers
MIN_BOOST           = 0.25  # floor on negative multipliers
TOP_N_DEPT          = 4     # top practice areas to surface
NEW_DEPT_TREND      = 2.0   # trend value for brand-new depts (last_week=0, this_week>0);
                             # must exceed the DEPT_BOOST_THRESHOLD below to trigger a boost

# Default weights before any training data
FALLBACK_WEIGHTS = {
    "source_multipliers":   {},
    "dept_trend_boosts":    {},
    "keyword_boosts":       {},
    "geo_boosts":           {},
    "cross_firm_boosts":    {},
    "total_runs":           0,
    "last_trained":         "",
    "firm_velocity":        {},
    "seniority_distribution": {},
    "time_patterns":        {},
    "dedup_confidence":     {},
}

FALLBACK_TOP4 = [
    {"department": "Corporate / M&A",                 "signal_count": 0, "firm_count": 0, "trend_boost": 1.0},
    {"department": "Banking & Finance",               "signal_count": 0, "firm_count": 0, "trend_boost": 1.0},
    {"department": "Project Finance & Infrastructure","signal_count": 0, "firm_count": 0, "trend_boost": 1.0},
    {"department": "Arbitration & Disputes",          "signal_count": 0, "firm_count": 0, "trend_boost": 1.0},
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
    """Apply ALL learned multipliers to a signal's department_score before saving."""
    source  = signal.get("source", "")
    dept    = signal.get("department", "")
    loc     = signal.get("location", "")
    firm_id = signal.get("firm_id", "")
    title   = signal.get("title", "").lower()[:40]

    # Core multipliers
    src_mul   = weights.get("source_multipliers", {}).get(source, 1.0)
    dep_mul   = weights.get("dept_trend_boosts",  {}).get(dept, 1.0)

    # Keyword boost (average of matched keywords)
    kw_boosts = weights.get("keyword_boosts", {})
    kw_mul    = 1.0
    kws = signal.get("matched_keywords", [])
    if kws and kw_boosts:
        scores = [kw_boosts.get(k, 1.0) for k in kws]
        kw_mul = sum(scores) / len(scores)

    # Geographic hotspot boost (Dim 8)
    geo_mul   = weights.get("geo_boosts", {}).get(loc, 1.0)

    # Cross-firm dept correlation boost (Dim 11)
    xf_mul    = weights.get("cross_firm_boosts", {}).get(dept, 1.0)

    # Multi-source deduplication confidence boost (Dim 9)
    dedup_key = f"{firm_id}:{title}"
    dd_mul    = weights.get("dedup_confidence", {}).get(dedup_key, 1.0)

    # Time-pattern boost (Dim 10): mid-week signals (Tue–Thu) get a quality boost.
    # SQLite strftime('%w') convention: 0=Sun, 1=Mon, …, 6=Sat.
    # Python weekday(): 0=Mon, …, 6=Sun → convert via (weekday + 1) % 7.
    time_mul  = 1.0
    time_patterns = weights.get("time_patterns", {})
    if time_patterns:
        sqlite_dow = str((datetime.now().weekday() + 1) % 7)  # 0=Sun, 1=Mon, …, 6=Sat
        time_mul = time_patterns.get(sqlite_dow, 1.0)

    # Firm velocity boost (Dim 4): signals from accelerating firms get a small lift
    firm_mul  = 1.0
    firm_velocity = weights.get("firm_velocity", {})
    if firm_velocity and firm_id in firm_velocity:
        status = firm_velocity[firm_id].get("status", "stable")
        if status == "accelerating":
            firm_mul = 1.10
        elif status == "decelerating":
            firm_mul = 0.95

    multiplier = min(MAX_BOOST, max(MIN_BOOST,
        src_mul * dep_mul * kw_mul * geo_mul * xf_mul * dd_mul * time_mul * firm_mul))
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
    logger.info("Self-Training Evolution Engine v4 — starting")
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

        # ── 6+7. Trend + source reports ────────────────────────────────────
        _generate_trend_report(cursor, weights)
        _generate_source_report(cursor, weights)

        # ── 8. Geographic hotspot detection (NEW) ─────────────────────────
        _train_geo_hotspots(cursor, weights)

        # ── 9. Cross-source deduplication confidence (NEW) ────────────────
        _train_dedup_confidence(cursor, weights)

        # ── 10. Time-pattern analysis (NEW) ───────────────────────────────
        _train_time_patterns(cursor, weights)

        # ── 11. Cross-firm hiring correlation (NEW) ───────────────────────
        _train_cross_firm_correlation(cursor, weights)

        # ── 12. Prediction accuracy self-assessment (NEW) ─────────────────
        _train_prediction_accuracy(cursor, weights)

        # Update metadata
        weights["total_runs"]   = weights.get("total_runs", 0) + 1
        weights["last_trained"] = datetime.now(timezone.utc).isoformat()

        save_weights(weights)
        conn.close()

        logger.info(f"Self-Training v4 — complete (run #{weights['total_runs']})")
        logger.info(f"  Source multipliers:  {len(weights['source_multipliers'])}")
        logger.info(f"  Dept trend boosts:   {len(weights['dept_trend_boosts'])}")
        logger.info(f"  Keyword boosts:      {len(weights['keyword_boosts'])}")
        logger.info(f"  Geo boosts:          {len(weights.get('geo_boosts', {}))}")
        logger.info(f"  Cross-firm boosts:   {len(weights.get('cross_firm_boosts', {}))}")
        logger.info(f"  Partner signal ratio:{weights.get('partner_signal_ratio', 0):.1%}")

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
            # New department with no history — treat as a meaningful new trend signal;
            # use NEW_DEPT_TREND so it clearly exceeds the > 1.30 boost threshold below.
            trend = 1.0 if this_week == 0 else NEW_DEPT_TREND
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


# ═══════════════════════════════════════════════════════════════════
# NEW TRAINING DIMENSIONS (v4)
# ═══════════════════════════════════════════════════════════════════

def _train_geo_hotspots(cursor, weights: dict):
    """
    Dim 8: Detect which ME cities are heating up.
    Cities with accelerating signal volume get a geo_boost multiplier
    that inflates expansion scores for that location.
    """
    try:
        cursor.execute("""
            SELECT location,
                   SUM(CASE WHEN created_at > datetime('now', '-7 days')  THEN 1 ELSE 0 END) as this_week,
                   SUM(CASE WHEN created_at > datetime('now', '-14 days')
                             AND created_at <= datetime('now', '-7 days') THEN 1 ELSE 0 END) as last_week,
                   COUNT(*) as total_30d
            FROM signals
            WHERE created_at > datetime('now', '-30 days')
              AND location IS NOT NULL AND location != ''
            GROUP BY location
            HAVING total_30d >= 2
            ORDER BY total_30d DESC
        """)
        rows = cursor.fetchall()
    except Exception:
        return

    geo_boosts = weights.setdefault("geo_boosts", {})
    geo_report = []

    for row in rows:
        city  = row["location"]
        tw    = row["this_week"] or 0
        lw    = row["last_week"] or 0
        total = row["total_30d"] or 1
        # Heat score: combines absolute volume and week-over-week acceleration
        heat  = (tw / max(lw, 1)) if lw > 0 else (1.0 + tw * 0.1)
        new_boost = max(MIN_BOOST, min(MAX_BOOST, heat))
        old_boost = geo_boosts.get(city, 1.0)
        geo_boosts[city] = round(old_boost * (1 - ALPHA) + new_boost * ALPHA, 4)
        geo_report.append({
            "city": city, "this_week": tw, "last_week": lw,
            "total_30d": total, "boost": geo_boosts[city],
            "trend": "↑ heating" if tw > lw else ("→ stable" if tw == lw else "↓ cooling"),
        })

    geo_report.sort(key=lambda x: -x["boost"])
    Path("learning").mkdir(exist_ok=True)
    with open(GEO_REPORT_PATH, "w") as f:
        json.dump({
            "cities": geo_report,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }, f, indent=2)

    logger.info(f"  Geo hotspots: {len(geo_boosts)} cities tracked")


def _train_dedup_confidence(cursor, weights: dict):
    """
    Dim 9: When the same job title appears from multiple sources for the
    same firm in the same week, that's higher confidence than a single sighting.
    Build a dedup_confidence map: (firm_id, title_stub) → source_count.
    Used downstream to boost expansion scores for multi-source corroboration.
    """
    try:
        cursor.execute("""
            SELECT firm_id, LOWER(SUBSTR(title, 1, 40)) as title_stub,
                   COUNT(DISTINCT source) as source_count,
                   MAX(department_score) as max_score
            FROM signals
            WHERE created_at > datetime('now', '-14 days')
              AND title IS NOT NULL AND title != ''
            GROUP BY firm_id, title_stub
            HAVING source_count >= 2
        """)
        rows = cursor.fetchall()
    except Exception:
        return

    dedup = weights.setdefault("dedup_confidence", {})
    for row in rows:
        key = f"{row['firm_id']}:{row['title_stub']}"
        # More sources = higher confidence multiplier (capped at 1.5×)
        boost = min(1.5, 1.0 + (row["source_count"] - 1) * 0.15)
        dedup[key] = round(boost, 3)

    logger.info(f"  Dedup confidence: {len(dedup)} multi-source signals found")


def _train_time_patterns(cursor, weights: dict):
    """
    Dim 10: Learn which days of the week produce the highest-quality signals.
    Firms post jobs on Tues/Wed/Thurs; recruiters fire Mon/Tue.
    Weights signals that arrive mid-week more heavily than Fri/weekend.
    """
    try:
        cursor.execute("""
            SELECT strftime('%w', created_at) as dow,
                   AVG(department_score) as avg_score,
                   COUNT(*) as cnt
            FROM signals
            WHERE created_at > datetime('now', '-60 days')
            GROUP BY dow
            HAVING cnt >= 5
        """)
        rows = cursor.fetchall()
    except Exception:
        return

    if not rows:
        return

    all_avg = sum(r["avg_score"] for r in rows) / len(rows) if rows else 1.0
    day_patterns = {}
    for row in rows:
        dow  = int(row["dow"])  # 0=Sun … 6=Sat
        rel  = (row["avg_score"] or 1.0) / (all_avg or 1.0)
        day_patterns[dow] = round(max(MIN_BOOST, min(MAX_BOOST, rel)), 4)

    weights["time_patterns"] = day_patterns
    logger.info(f"  Time patterns: trained on {len(day_patterns)} day-of-week buckets")


def _train_cross_firm_correlation(cursor, weights: dict):
    """
    Dim 11: Cross-firm hiring correlation.
    When multiple firms post in the same dept in the same week, that practice area
    is genuinely hot — boost the dept score for ALL firms in that dept.
    Also: if a peer firm at similar AmLaw rank just opened a role, that's a signal
    that the role type is in demand across the peer group.
    """
    try:
        cursor.execute("""
            SELECT department,
                   COUNT(DISTINCT firm_id) as firm_count,
                   COUNT(*) as signal_count,
                   SUM(CASE WHEN signal_type IN ('recruiter_posting','lateral_hire') THEN 1 ELSE 0 END) as high_conf
            FROM signals
            WHERE created_at > datetime('now', '-7 days')
              AND department IS NOT NULL AND department != ''
            GROUP BY department
            HAVING firm_count >= 3
            ORDER BY firm_count DESC
        """)
        rows = cursor.fetchall()
    except Exception:
        return

    cross_boosts = weights.setdefault("cross_firm_boosts", {})
    for row in rows:
        dept        = row["department"]
        firm_count  = row["firm_count"] or 1
        # 3+ firms posting in same dept same week → market-wide demand signal
        # Each additional firm adds a 5% boost, capped at 1.5×
        boost = min(1.5, 1.0 + (firm_count - 2) * 0.08)
        old   = cross_boosts.get(dept, 1.0)
        cross_boosts[dept] = round(old * (1 - ALPHA) + boost * ALPHA, 4)

    logger.info(f"  Cross-firm correlation: {len(cross_boosts)} dept boosts updated")


def _train_prediction_accuracy(cursor, weights: dict):
    """
    Dim 12: Model self-assessment.
    Compares expansion alerts sent 4+ weeks ago against subsequent signal volume.
    If a high-score alert was followed by more signals from that firm/dept, the
    prediction was accurate — boost that dept's source weights.
    If not followed up, slightly decay the dept_trend_boost.
    """
    try:
        cursor.execute("""
            SELECT firm_id, department, score, created_at
            FROM weekly_scores
            WHERE created_at < datetime('now', '-28 days')
              AND score > 10
            ORDER BY created_at DESC
            LIMIT 50
        """)
        past_alerts = cursor.fetchall()
    except Exception:
        return  # Table may not exist yet — fine

    if not past_alerts:
        return

    dept_boosts   = weights.setdefault("dept_trend_boosts", {})
    accuracy_log  = []

    for alert in past_alerts:
        try:
            firm_id = alert["firm_id"]
            dept    = alert["department"]
            sent_at = alert["created_at"]

            # Did signals actually follow?
            cursor.execute("""
                SELECT COUNT(*) as follow_up
                FROM signals
                WHERE firm_id = ?
                  AND department = ?
                  AND created_at > ?
                  AND created_at < datetime(?, '+21 days')
            """, (firm_id, dept, sent_at, sent_at))
            result     = cursor.fetchone()
            follow_up  = result["follow_up"] if result else 0
            accurate   = follow_up >= 2  # 2+ follow-up signals = prediction confirmed

            # EMA-nudge the dept boost based on accuracy
            old_boost  = dept_boosts.get(dept, 1.0)
            adjustment = 1.05 if accurate else 0.97
            dept_boosts[dept] = round(
                max(MIN_BOOST, min(MAX_BOOST, old_boost * adjustment)), 4
            )
            accuracy_log.append({
                "firm_id": firm_id, "department": dept,
                "follow_up_signals": follow_up, "accurate": accurate,
                "dept_boost": dept_boosts[dept],
            })
        except Exception:
            continue

    if accuracy_log:
        correct = sum(1 for x in accuracy_log if x["accurate"])
        accuracy_pct = correct / len(accuracy_log)
        weights["prediction_accuracy"] = round(accuracy_pct, 3)

        Path("learning").mkdir(exist_ok=True)
        with open(ACCURACY_REPORT_PATH, "w") as f:
            json.dump({
                "total_assessed": len(accuracy_log),
                "accurate": correct,
                "accuracy_pct": accuracy_pct,
                "details": accuracy_log[:20],
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }, f, indent=2)

        logger.info(
            f"  Prediction accuracy: {accuracy_pct:.1%} "
            f"({correct}/{len(accuracy_log)} alerts confirmed)"
        )
