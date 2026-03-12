"""
ME Legal Jobs Tracker -- main entry point  (v4.2)

v4.2 Changes:
  - FIXED: training job git failure -- binary .pyc rebase conflict
    (git ls-files | grep pyc | xargs git rm --cached)
  - FIXED: git pull --rebase -X ours now also covers training step
  - NEW: ATSScraper (slot 2) -- Greenhouse / Lever / Workday public JSON APIs
    Covers 23 of 24 tracked firms; CF-proof since these are public REST endpoints
    Greenhouse: Gibson Dunn, Jones Day, Milbank, Simpson Thacher, S&C, K&S,
                Mayer Brown, Paul Hastings, O'Melveny, Skadden
    Lever:      Greenberg Traurig, McDermott, Morgan Lewis
    Workday:    Latham, Kirkland, White & Case, Baker McKenzie, DLA Piper,
                Norton Rose, Hogan Lovells, Reed Smith, Dentons, Squire Patton,
                A&O Shearman
  - IMPROVED: Full browser fingerprint headers in BaseScraper (Sec-Fetch-* headers)
  - IMPROVED: JSON_HEADERS constant for ATS API calls (CORS-mode headers)

Run modes:
  python main.py             -- full collect -> analyse -> dashboard -> 1 Telegram alert
  python main.py --digest    -- send weekly digest from existing DB
  python main.py --dashboard -- regenerate dashboard only
  python main.py --train     -- run evolution engine only (no scraping)
  python main.py --firm X    -- single firm
  python main.py --list-firms
"""
import argparse, logging, sys
from datetime import datetime, timezone

from config import Config
from firms import FIRMS, FIRMS_BY_ID
from database.db import Database
from scrapers.jobs import JobsScraper
from scrapers.ats import ATSScraper
from scrapers.job_boards import JobBoardsScraper
from scrapers.recruiter import RecruiterScraper
from scrapers.press import PressScraper
from scrapers.chambers import ChambersScraper
from scrapers.rss import RSSFeedScraper
from scrapers.website import WebsiteScraper
from scrapers.google_news import GoogleNewsScraper
from scrapers.law360_me import Law360MEScraper
from scrapers.linkedin_people import LinkedInPeopleScraper
from scrapers.regulatory_registry import RegulatoryRegistryScraper
from scrapers.legal_media import LegalMediaScraper
from scrapers.alsp import ALSPScraper
from analysis.signals import ExpansionAnalyzer
from alerts.notifier import Notifier
from dashboard.generator import DashboardGenerator
from learning.evolution import run_evolution, load_weights, apply_learned_weights_to_signal
from scrapers.base import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("tracker.log")],
)
logger = logging.getLogger("main")

# 13 scrapers — ordered by signal quality (fastest/highest confidence first)
SCRAPER_CLASSES = [
    JobsScraper,               # 1  Firm careers pages — HTML scrape (may be blocked by CF)
    ATSScraper,                # 2  Greenhouse / Lever / Workday public JSON APIs — CF-proof
    RecruiterScraper,          # 3  24 ME legal recruiters (global cache)
    RegulatoryRegistryScraper, # 4  DIFC/ADGM/QFC registries — 3-6mo lead time
    LegalMediaScraper,         # 5  The Oath / LexisNexis ME / The Lawyer
    Law360MEScraper,           # 6  Law360 + ALM RSS
    GoogleNewsScraper,         # 7  Google News RSS
    JobBoardsScraper,          # 8  14 boards: Bayt/GulfTalent/Jameson/Indeed×3/etc
    ALSPScraper,               # 9  LOD / Axiom / Peerpoint contract pipeline
    PressScraper,              # 10 Firm news + IFLR / Arabian Business
    ChambersScraper,           # 11 Chambers Global + Legal 500 ME
    RSSFeedScraper,            # 12 17 RSS feeds
    LinkedInPeopleScraper,     # 13 Google-indexed LinkedIn profiles
    WebsiteScraper,            # 14 ME office page change detection
]

# Only these types trigger an instant queued alert
ALERT_SIGNAL_TYPES = {
    "job_posting", "recruiter_posting",
    "regulatory_filing", "lateral_hire", "contract_role",
}


def run(firms_to_run=None, digest_only=False):
    config    = Config()
    db        = Database(config.DB_PATH)
    notifier  = Notifier(config)
    analyzer  = ExpansionAnalyzer(db)
    dashboard = DashboardGenerator(db)
    weights   = load_weights()

    target_firms = [f for f in (firms_to_run or FIRMS) if "careers_url" in f or "me_offices" in f]

    logger.info("=" * 70)
    logger.info(f"ME Legal Jobs Tracker  —  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    logger.info(f"Scrapers: {len(SCRAPER_CLASSES)} (incl. ATS: Greenhouse/Lever/Workday)  |  Firms: {len(target_firms)}")
    logger.info(f"Self-training run #{weights.get('total_runs', 0) + 1}  |  Active sources: {len(weights.get('source_multipliers', {}))}")
    logger.info("=" * 70)

    if digest_only:
        logger.info("Digest-only mode — skipping scraping")
        _send_digest(db, analyzer, notifier, dashboard)
        db.close()
        return

    # ── Collection phase ──────────────────────────────────────────────────
    static_scrapers   = [cls() for cls in SCRAPER_CLASSES if cls is not WebsiteScraper]
    all_new_signals: list[dict] = []

    for firm in target_firms:
        logger.info(f"\n{'─' * 55}")
        logger.info(f"Processing: {firm['name']}  [{', '.join(firm.get('me_offices', {}).keys())}]")
        web_scraper = WebsiteScraper(known_hashes=db.get_website_hashes(firm["id"]))

        for scraper in static_scrapers + [web_scraper]:
            try:
                fetched   = scraper.fetch(firm)
                new_count = 0
                for signal in fetched:
                    signal = apply_learned_weights_to_signal(signal, weights)
                    if db.is_new_signal(signal):
                        db.save_signal(signal)
                        all_new_signals.append(signal)
                        new_count += 1
                        if signal["signal_type"] in ALERT_SIGNAL_TYPES:
                            notifier.queue_instant_alert(signal)
                logger.info(f"  {scraper.name:<40} {len(fetched):>3} signals  ({new_count} new)")
            except Exception as e:
                logger.error(f"  {scraper.name} failed for {firm['short']}: {e}", exc_info=True)

        for url, h in web_scraper._known_hashes.items():
            db.save_website_hash(firm["id"], url, h)

    logger.info(f"\nTotal new signals this run: {len(all_new_signals)}")

    # Circuit breaker summary
    cb = BaseScraper.get_circuit_breaker_report()
    if cb:
        logger.info(f"Circuit breaker trips: {cb}")

    # ── Self-training ──────────────────────────────────────────────────────
    if config.ENABLE_SELF_TRAINING:
        logger.info("\nRunning self-training evolution engine...")
        run_evolution(config.DB_PATH)
        weights = load_weights()
        logger.info(f"  Training complete — run #{weights.get('total_runs', 0)}")
        logger.info(f"  Source multipliers: {len(weights.get('source_multipliers', {}))}")
        logger.info(f"  Partner signal ratio: {weights.get('partner_signal_ratio', 0):.1%}")

    # ── Analysis ──────────────────────────────────────────────────────────
    weekly_signals   = db.get_signals_this_week()
    expansion_alerts = analyzer.analyze(weekly_signals)
    for alert in expansion_alerts:
        db.save_weekly_score(
            firm_id=alert["firm_id"], firm_name=alert["firm_name"],
            department=alert["department"], location=alert.get("location", ""),
            score=alert["expansion_score"], signal_count=alert["signal_count"],
            breakdown=alert["signal_breakdown"],
        )
    logger.info(f"Expansion alerts this week: {len(expansion_alerts)}")

    # ── ONE Telegram message per run ──────────────────────────────────────
    # FIXED: was calling flush_instant_alerts() + send_combined_digest() = 2 messages
    # Now: pass queued signals directly into the digest so everything goes in ONE send
    notifier.flush_and_digest(
        db=db,
        analyzer=analyzer,
        new_signals=all_new_signals,
    )

    # ── Regenerate dashboard ───────────────────────────────────────────────
    dashboard.generate()
    logger.info("Dashboard regenerated → docs/index.html")
    db.close()
    logger.info("\nDone.\n")


def _send_digest(db, analyzer, notifier, dashboard, new_signals=None):
    """Weekly digest mode — sends combined message and regenerates dashboard."""
    weekly_signals   = db.get_signals_this_week()
    expansion_alerts = analyzer.analyze(weekly_signals)
    new_alerts = [a for a in expansion_alerts
                  if not db.was_alert_sent(a["firm_id"], a["department"])]
    notifier.send_combined_digest(new_alerts, [], new_signals=new_signals or [])
    for a in new_alerts:
        db.mark_alert_sent(a["firm_id"], a["department"], a["expansion_score"])
    dashboard.generate()
    logger.info(f"Digest: {len(new_alerts)} new alert(s) sent")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ME Legal Jobs Tracker v3")
    parser.add_argument("--digest",     action="store_true", help="Send digest from DB")
    parser.add_argument("--dashboard",  action="store_true", help="Regenerate dashboard")
    parser.add_argument("--train",      action="store_true", help="Run self-training only")
    parser.add_argument("--firm",       type=str,            help="Single firm ID")
    parser.add_argument("--list-firms", action="store_true", help="List all firm IDs")
    args = parser.parse_args()

    if args.list_firms:
        import sys; sys.path.insert(0, ".")
        from firms import FIRMS
        print("\nTracked US firms:\n")
        for f in [x for x in FIRMS if "careers_url" in x]:
            print(f"  {f['id']:<22} {f['short']:<32} offices: {', '.join(f.get('me_offices',{}).keys())}")
        sys.exit(0)

    if args.dashboard:
        cfg = Config(); db = Database(cfg.DB_PATH)
        DashboardGenerator(db).generate(); db.close(); sys.exit(0)

    if args.train:
        run_evolution(Config().DB_PATH); sys.exit(0)

    target = None
    if args.firm:
        firm = FIRMS_BY_ID.get(args.firm)
        if not firm:
            logger.error(f"Unknown firm: '{args.firm}'. Run --list-firms."); sys.exit(1)
        target = [firm]

    run(firms_to_run=target, digest_only=args.digest)
