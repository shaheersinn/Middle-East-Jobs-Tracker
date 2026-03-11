"""
RSS Feed Scraper
=================
Pulls RSS/Atom feeds from ME legal media, legal news aggregators
and firm news feeds, filtering for associate job postings and
ME expansion signals involving tracked US firms.

Signal types: press_release | job_posting | lateral_hire
"""

import re
from datetime import datetime, timezone, timedelta

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False

from scrapers.base import BaseScraper
from classifier.department import DepartmentClassifier

classifier = DepartmentClassifier()

# Maximum age of RSS entries to accept (days)
MAX_ENTRY_AGE_DAYS = 14

# RSS feeds indexed
RSS_FEEDS = [
    # ME legal media
    {"name": "The Lawyer MEA",    "url": "https://www.thelawyermea.com/feed/"},
    {"name": "IFLR ME",           "url": "https://www.iflr.com/rss/middle-east"},
    {"name": "Legal Business",    "url": "https://www.legalbusiness.co.uk/feed/"},
    {"name": "Law.com Int'l",     "url": "https://www.law.com/international-edition/?rss"},
    {"name": "Global Legal Post", "url": "https://www.globallegalpost.com/feed/"},
    {"name": "Lexology ME",       "url": "https://www.lexology.com/rss/regionalupdates?region=middle-east"},
    # Firm-specific RSS (auto-generated where available)
    {"name": "Latham News",       "url": "https://www.lw.com/en/rss/news"},
    {"name": "White & Case News", "url": "https://www.whitecase.com/news/feed"},
    {"name": "Baker McKenzie",    "url": "https://www.bakermckenzie.com/en/rss/insight"},
    {"name": "DLA Piper News",    "url": "https://www.dlapiper.com/en/insights/rss"},
    {"name": "NRF News",          "url": "https://www.nortonrosefulbright.com/en/rss/knowledge"},
    {"name": "Dentons News",      "url": "https://www.dentons.com/en/rss/insights"},
    {"name": "Hogan Lovells",     "url": "https://www.hoganlovells.com/en/rss/news"},
    {"name": "Jones Day",         "url": "https://www.jonesday.com/en/rss/news"},
    # Job-related RSS
    {"name": "Indeed UAE Jobs",   "url": "https://ae.indeed.com/rss?q=law+associate&l=Dubai&sort=date"},
    {"name": "Bayt Legal RSS",    "url": "https://www.bayt.com/en/rss/jobs/legal/uae/"},
]

# Signals to look for in RSS entry text
JOB_SIGNALS = [
    "associate", "lawyer", "counsel", "attorney", "solicitor", "hiring",
    "vacancy", "opportunity", "career", "opening", "recruit", "join our team",
]

HIRE_SIGNALS = [
    "hire", "hires", "hired", "appoint", "appoints", "lateral", "joins",
    "welcomed", "new partner", "new associate", "new counsel",
]


class RSSFeedScraper(BaseScraper):
    name = "RSSFeedScraper"

    def fetch(self, firm: dict) -> list[dict]:
        if not HAS_FEEDPARSER:
            self.logger.warning("feedparser not installed — skipping RSS")
            return []

        signals = []
        firm_names = [firm["short"], firm["name"]] + firm.get("alt_names", [])
        cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_ENTRY_AGE_DAYS)

        for feed_def in RSS_FEEDS:
            try:
                parsed = feedparser.parse(feed_def["url"])
            except Exception as e:
                self.logger.debug(f"RSS parse error {feed_def['name']}: {e}")
                continue

            for entry in parsed.entries[:30]:
                title = getattr(entry, "title", "") or ""
                summary = getattr(entry, "summary", "") or ""
                link  = getattr(entry, "link", "") or ""
                full_text = f"{title} {summary}"

                # Age filter
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        import time as _t
                        published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    except Exception:
                        pass
                if published and published < cutoff:
                    continue

                # Firm match
                if not any(n.lower() in full_text.lower() for n in firm_names):
                    continue

                # ME location filter
                if not self._is_me_location(full_text):
                    continue

                # Determine signal type
                is_job  = any(kw in full_text.lower() for kw in JOB_SIGNALS)
                is_hire = any(kw in full_text.lower() for kw in HIRE_SIGNALS)

                if not is_job and not is_hire:
                    continue

                signal_type = "lateral_hire" if is_hire else "job_posting" if is_job else "press_release"

                dept = classifier.top_department(full_text[:500])
                if not dept:
                    dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}

                weight = 3.0 if is_hire else 2.0 if is_job else 1.5

                signals.append(self._make_signal(
                    firm_id=firm["id"],
                    firm_name=firm["name"],
                    signal_type=signal_type,
                    title=f"[{feed_def['name']}] {title}",
                    body=summary[:900],
                    url=link,
                    department=dept["department"],
                    department_score=dept["score"] * weight,
                    matched_keywords=dept["matched_keywords"],
                    location=self._extract_location(full_text) or "Middle East",
                    source=feed_def["name"],
                    published_date=published.isoformat() if published else None,
                ))

        self.logger.info(f"[{firm['short']}] RSS: {len(signals)} item(s)")
        return signals
