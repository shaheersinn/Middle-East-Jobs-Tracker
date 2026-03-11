"""
ME Legal Jobs Tracker — main entry point  (v2)

CHANGES v2:
  - 10 scrapers (added GoogleNewsScraper, Law360MEScraper, LinkedInPeopleScraper)
  - Self-training evolution engine runs after every collection cycle
  - Learning weights applied to every signal in real-time
  - Circuit breaker report printed at end of each run
  - Dashboard URL fixed to https://middle-east-jobs-tracker.vercel.app/

Run modes:
  python main.py                   — full collect + analyse + dashboard
  python main.py --digest          — weekly digest from existing DB
  python main.py --dashboard       — regenerate dashboard only
  python main.py --train           — run evolution engine only
  python main.py --firm latham     — single firm (testing)
  python main.py --list-firms      — print all firm IDs
"""

import argparse
import logging
import sys
from datetime import datetime, timezone

from config import Config
from firms import FIRMS, FIRMS_BY_ID
from database.db import Database
from scrapers.jobs import JobsScraper
from scrapers.job_boards import JobBoardsScraper
from scrapers.recruiter import RecruiterScraper
from scrapers.press import PressScraper
from scrapers.chambers import ChambersScraper
from scrapers.rss import RSSFeedScraper
from scrapers.website import WebsiteScraper
from scrapers.google_news import GoogleNewsScraper
from scrapers.law360_me import Law360MEScraper
from scrapers.linkedin_people import LinkedInPeopleScraper
from analysis.signals import ExpansionAnalyzer
from alerts.notifier import Notifier
from dashboard.generator import DashboardGenerator
from learning.evolution import run_evolution, load_weights, apply_learned_weights_to_signal
from scrapers.base import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("tracker.log"),
    ],
)
logger = logging.getLogger("main")

# Ordered scraper classes
SCRAPER_CLASSES = [
    JobsScraper,            # 1. Firm careers pages
    RecruiterScraper,       # 2. ME recruiter agencies (cached globally)
    JobBoardsScraper,       # 3. Bayt / Indeed UAE / LinkedIn / Glassdoor / Laimoon
    GoogleNewsScraper,      # 4. Google News RSS (reliable on GH Actions)
    Law360MEScraper,        # 5. Law360 + ALM RSS feeds
    PressScraper,           # 6. Firm news + IFLR / Arabian Business
    ChambersScraper,        # 7. Chambers Global ME + Legal 500 ME
    RSSFeedScraper,         # 8. 17 RSS feeds
    LinkedInPeopleScraper,  # 9. LinkedIn people (Google-indexed)
    WebsiteScraper,         # 10. ME office page change detection
]


def run(firms_to_run=None, digest_only=False):
    config   = Config()
    db       = Database(config.DB_PATH)
    notifier = Notifier(config)
    analyzer = ExpansionAnalyzer(db)
    dashboard= DashboardGenerator(db)
    weights  = load_weights()

    target_firms = firms_to_run or FIRMS

    logger.info("=" * 70)
    logger.info(f"ME Legal Jobs Tracker  —  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    logger.info(f"Scrapers: {len(SCRAPER_CLASSES)}  |  Firms: {len(target_firms)}")
    logger.info(f"Self-training run #{weights.get('total_runs',0) + 1}")
    logger.info("=" * 70)

    if digest_only:
        logger.info("Digest-only mode — skipping scraping")
        _send_digest(db, analyzer, notifier, dashboard)
        db.close()
        return

    # ── Collection phase ──────────────────────────────────────────────────
    static_scrapers = [cls() for cls in SCRAPER_CLASSES if cls is not WebsiteScraper]
    all_new_signals = []

    for firm in target_firms:
        logger.info(f"\n{'─' * 55}")
        logger.info(f"Processing: {firm['name']}")

        web_scraper = WebsiteScraper(known_hashes=db.get_website_hashes(firm["id"]))

        for scraper in static_scrapers + [web_scraper]:
            try:
                fetched   = scraper.fetch(firm)
                new_count = 0

                for signal in fetched:
                    # Apply learned weights before saving
                    signal = apply_learned_weights_to_signal(signal, weights)

                    if db.is_new_signal(signal):
                        db.save_signal(signal)
                        all_new_signals.append(signal)
                        new_count += 1

                        if (signal["signal_type"] in ("job_posting", "recruiter_posting")
                                and config.INSTANT_ALERT_ON_NEW_JOB):
                            notifier.send_instant_alert(signal)

                logger.info(f"  {scraper.name:<35} {len(fetched):>3} signals  ({new_count} new)")

            except Exception as e:
                logger.error(f"  {scraper.name} failed for {firm['short']}: {e}", exc_info=True)

        for url, h in web_scraper._known_hashes.items():
            db.save_website_hash(firm["id"], url, h)

    logger.info(f"\nTotal new signals this run: {len(all_new_signals)}")

    # ── Circuit breaker report ────────────────────────────────────────────
    cb = BaseScraper.get_circuit_breaker_report()
    if cb:
        logger.info(f"Circuit breaker: {cb}")

    # ── Self-training evolution ───────────────────────────────────────────
    if config.ENABLE_SELF_TRAINING:
        logger.info("\nRunning self-training evolution...")
        run_evolution(config.DB_PATH)
        # Reload weights for analysis scoring
        weights = load_weights()

    # ── Analysis + notifications ──────────────────────────────────────────
    weekly_signals   = db.get_signals_this_week()
    expansion_alerts = analyzer.analyze(weekly_signals)

    for alert in expansion_alerts:
        db.save_weekly_score(
            firm_id=alert["firm_id"],
            firm_name=alert["firm_name"],
            department=alert["department"],
            location=alert.get("location",""),
            score=alert["expansion_score"],
            signal_count=alert["signal_count"],
            breakdown=alert["signal_breakdown"],
        )

    logger.info(f"Expansion alerts: {len(expansion_alerts)}")
    _send_digest(db, analyzer, notifier, dashboard, new_signals=all_new_signals)
    db.close()
    logger.info("\nDone.\n")


def _send_digest(db, analyzer, notifier, dashboard, new_signals=None):
    weekly_signals   = db.get_signals_this_week()
    expansion_alerts = analyzer.analyze(weekly_signals)
    new_alerts = [
        a for a in expansion_alerts
        if not db.was_alert_sent(a["firm_id"], a["department"])
    ]
    notifier.send_combined_digest(new_alerts, [], new_signals=new_signals or [])
    for a in new_alerts:
        db.mark_alert_sent(a["firm_id"], a["department"], a["expansion_score"])
    dashboard.generate()
    logger.info(f"Digest: {len(new_alerts)} new alert(s)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="ME Legal Jobs Tracker — US BigLaw associate jobs in the Middle East"
    )
    parser.add_argument("--digest",     action="store_true")
    parser.add_argument("--dashboard",  action="store_true")
    parser.add_argument("--train",      action="store_true", help="Run self-training only")
    parser.add_argument("--firm",       type=str)
    parser.add_argument("--list-firms", action="store_true")
    args = parser.parse_args()

    if args.list_firms:
        print("\nTracked US firms:\n")
        for f in FIRMS:
            offices = ", ".join(f.get("me_offices", {}).keys())
            print(f"  {f['id']:<22} {f['short']:<28} ME offices: {offices}")
        sys.exit(0)

    if args.dashboard:
        config = Config()
        db = Database(config.DB_PATH)
        DashboardGenerator(db).generate()
        db.close()
        sys.exit(0)

    if args.train:
        config = Config()
        run_evolution(config.DB_PATH)
        sys.exit(0)

    target = None
    if args.firm:
        firm = FIRMS_BY_ID.get(args.firm)
        if not firm:
            logger.error(f"Unknown firm ID: '{args.firm}'. Run --list-firms to see available IDs.")
            sys.exit(1)
        target = [firm]

    run(firms_to_run=target, digest_only=args.digest)
