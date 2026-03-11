"""
Law360 / ALM International Scraper (new)
==========================================
Monitors Law360 and ALM's international coverage for ME-related
US firm hiring announcements and job postings.

Law360 allows unauthenticated access to some articles and their
Google-indexed content is accessible via RSS.

Signal types: lateral_hire | press_release
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

MAX_AGE_DAYS = 14

LAW360_FEEDS = [
    "https://www.law360.com/rss/articles?section=international",
    "https://www.law360.com/rss/articles?section=mergers-acquisitions",
    "https://www.law360.com/rss/articles?section=banking",
    "https://www.law360.com/rss/articles?section=energy",
    "https://www.law360.com/rss/articles?section=project-finance",
]

ALM_FEEDS = [
    "https://www.americanlawyer.com/rss",
    "https://www.law.com/international-edition/?rss",
]

HIRE_SIGNALS = [
    "joins", "hired", "lateral", "appoints", "appointed", "welcomed",
    "new partner", "new associate", "new counsel", "expands",
]


class Law360MEScraper(BaseScraper):
    name = "Law360MEScraper"

    def fetch(self, firm: dict) -> list[dict]:
        if not HAS_FEEDPARSER:
            return []

        signals = []
        firm_names = [firm["short"], firm["name"]] + firm.get("alt_names", [])
        cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)

        for feed_url in LAW360_FEEDS + ALM_FEEDS:
            try:
                parsed = feedparser.parse(feed_url)
            except Exception:
                continue

            for entry in parsed.entries[:20]:
                title   = getattr(entry, "title", "") or ""
                summary = getattr(entry, "summary", "") or ""
                link    = getattr(entry, "link", "") or ""
                full    = f"{title} {summary}"

                # Firm match
                if not any(n.lower() in full.lower() for n in firm_names):
                    continue

                # ME location
                if not self._is_me_location(full):
                    continue

                # Age filter
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    except Exception:
                        pass
                if published and published < cutoff:
                    continue

                is_hire = any(kw in full.lower() for kw in HIRE_SIGNALS)
                signal_type = "lateral_hire" if is_hire else "press_release"
                weight = 3.5 if is_hire else 1.5

                dept = classifier.top_department(full[:500])
                if not dept:
                    dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}

                source = "Law360" if "law360" in feed_url else "ALM / The American Lawyer"
                signals.append(self._make_signal(
                    firm_id=firm["id"],
                    firm_name=firm["name"],
                    signal_type=signal_type,
                    title=f"[{source}] {title}",
                    body=summary[:900],
                    url=link,
                    department=dept["department"],
                    department_score=dept["score"] * weight,
                    matched_keywords=dept["matched_keywords"],
                    location=self._extract_location(full) or "Middle East",
                    source=source,
                    published_date=published.isoformat() if published else None,
                ))

        self.logger.info(f"[{firm['short']}] Law360/ALM ME: {len(signals)} item(s)")
        return signals
