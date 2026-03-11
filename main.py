"""
ME Legal Jobs Tracker — main entry point.

Tracks US law firm associate job postings in Middle East offices.
Scrapes firm careers pages, ME job boards, and specialist legal recruiters.

Run modes:
  python main.py                   → full collection + analysis + digest
  python main.py --digest          → send weekly digest from existing DB only
  python main.py --dashboard       → regenerate dashboard from existing data
  python main.py --firm latham     → run for a single firm (testing)
  python main.py --list-firms      → print all tracked firms

Scrapers (per firm):
  JobsScraper       — firm careers pages (ME-filtered, associate-only)
  JobBoardsScraper  — Bayt, NaukriGulf, GulfTalent, Indeed UAE, LinkedIn ME
  RecruiterScraper  — Kershaw Leonard, Michael Page, Taylor Root, et al.
  PressScraper      — firm news + IFLR / The Lawyer MEA
  ChambersScraper   — Chambers Global ME + Legal 500 ME
  RSSFeedScraper    — ME legal media RSS feeds
  WebsiteScraper    — ME office page change detection
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
from analysis.signals import ExpansionAnalyzer
from alerts.notifier import Notifier
from dashboard.generator import DashboardGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("tracker.log"),
    ],
)
logger = logging.getLogger("main")

# Ordered scraper classes (run in this order per firm)
SCRAPER_CLASSES = [
    JobsScraper,       # Firm careers pages — highest confidence
    RecruiterScraper,  # ME recruiter agencies
    JobBoardsScraper,  # Bayt / NaukriGulf / GulfTalent / Indeed UAE / LinkedIn
    PressScraper,      # Firm news + legal media
    ChambersScraper,   # Rankings
    RSSFeedScraper,    # RSS aggregation
    WebsiteScraper,    # Website change detection
]


def run(firms_to_run: list | None = None, digest_only: bool = False):
    logger.info("=" * 70)
    logger.info(
        f"ME Legal Jobs Tracker  —  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    logger.info(f"Scrapers: {len(SCRAPER_CLASSES)}  |  Firms: {len(firms_to_run or FIRMS)}")
    logger.info("=" * 70)

    config    = Config()
    db        = Database(config.DB_PATH)
    notifier  = Notifier(config)
    analyzer  = ExpansionAnalyzer(db)
    dashboard = DashboardGenerator(db)

    target_firms = firms_to_run or FIRMS

    if digest_only:
        logger.info("Digest-only mode — skipping scraping")
        _send_digest(db, analyzer, notifier, dashboard)
        db.close()
        return

    # ── Collection phase ──────────────────────────────────────────────────

    # Build scrapers; WebsiteScraper needs per-firm hash state
    static_scrapers = [cls() for cls in SCRAPER_CLASSES if cls is not WebsiteScraper]

    all_new_signals: list[dict] = []

    for firm in target_firms:
        logger.info(f"\n{'─' * 55}")
        logger.info(f"Processing: {firm['name']}")

        # Website scraper gets pre-loaded hashes from DB
        web_scraper = WebsiteScraper(known_hashes=db.get_website_hashes(firm["id"]))

        for scraper in static_scrapers + [web_scraper]:
            try:
                fetched   = scraper.fetch(firm)
                new_count = 0
                for signal in fetched:
                    if db.is_new_signal(signal):
                        db.save_signal(signal)
                        all_new_signals.append(signal)
                        new_count += 1

                        # Instant alert for jobs
                        if (
                            signal["signal_type"] in ("job_posting", "recruiter_posting")
                            and config.INSTANT_ALERT_ON_NEW_JOB
                        ):
                            notifier.send_instant_alert(signal)

                logger.info(
                    f"  {scraper.name:<32} {len(fetched):>3} signals  ({new_count} new)"
                )
            except Exception as e:
                logger.error(
                    f"  {scraper.name} failed for {firm['short']}: {e}", exc_info=True
                )

        # Persist updated website hashes
        for url, h in web_scraper._known_hashes.items():
            db.save_website_hash(firm["id"], url, h)

    logger.info(f"\nTotal new signals this run: {len(all_new_signals)}")

    # ── Analysis phase ────────────────────────────────────────────────────

    weekly_signals   = db.get_signals_this_week()
    expansion_alerts = analyzer.analyze(weekly_signals)

    for alert in expansion_alerts:
        db.save_weekly_score(
            firm_id=alert["firm_id"],
            firm_name=alert["firm_name"],
            department=alert["department"],
            location=alert.get("location", ""),
            score=alert["expansion_score"],
            signal_count=alert["signal_count"],
            breakdown=alert["signal_breakdown"],
        )

    logger.info(f"Expansion alerts: {len(expansion_alerts)}")

    # ── Notifications + dashboard ─────────────────────────────────────────
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
    parser.add_argument("--digest",     action="store_true", help="Send digest from DB only")
    parser.add_argument("--dashboard",  action="store_true", help="Regenerate dashboard only")
    parser.add_argument("--firm",       type=str, help="Single firm ID (e.g. latham)")
    parser.add_argument("--list-firms", action="store_true", help="List all tracked firm IDs")
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

    target = None
    if args.firm:
        firm = FIRMS_BY_ID.get(args.firm)
        if not firm:
            logger.error(
                f"Unknown firm ID: '{args.firm}'. "
                f"Run --list-firms to see available IDs."
            )
            sys.exit(1)
        target = [firm]

    run(firms_to_run=target, digest_only=args.digest)
