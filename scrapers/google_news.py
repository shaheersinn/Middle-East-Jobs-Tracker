"""
Google News Scraper (new)
==========================
Uses Google News RSS (no API key needed) to find recent coverage of
US law firm hiring / job openings in the Middle East.

Google News RSS is highly reliable and doesn't block GitHub Actions runners.

Signal types: press_release | lateral_hire | job_posting
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

MAX_AGE_DAYS = 10

HIRE_KEYWORDS = [
    "hire", "hires", "hired", "join", "joins", "appoint", "appoints",
    "lateral", "new associate", "new counsel", "welcome",
]

JOB_KEYWORDS = [
    "vacancy", "opening", "opportunity", "associate position",
    "lawyer position", "job opening", "recruiting", "seeking"
]


class GoogleNewsScraper(BaseScraper):
    name = "GoogleNewsScraper"

    def fetch(self, firm: dict) -> list[dict]:
        if not HAS_FEEDPARSER:
            return []

        signals = []
        queries = [
            f'"{firm["short"]}" lawyer "Middle East"',
            f'"{firm["short"]}" associate Dubai OR "Abu Dhabi" OR Qatar',
            f'"{firm["short"]}" hire Dubai',
        ]

        cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)

        for q in queries[:3]:
            encoded = q.replace(" ", "+").replace('"', '%22')
            url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"

            try:
                parsed = feedparser.parse(url)
            except Exception as e:
                self.logger.debug(f"Google News RSS error: {e}")
                continue

            for entry in parsed.entries[:15]:
                title   = getattr(entry, "title", "") or ""
                summary = getattr(entry, "summary", "") or ""
                link    = getattr(entry, "link", "") or ""
                full    = f"{title} {summary}"

                # Age check
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    except Exception:
                        pass
                if published and published < cutoff:
                    continue

                if not self._is_me_location(full):
                    continue

                is_hire = any(kw in full.lower() for kw in HIRE_KEYWORDS)
                is_job  = any(kw in full.lower() for kw in JOB_KEYWORDS)

                if not is_hire and not is_job:
                    continue

                signal_type = "lateral_hire" if is_hire else "job_posting"
                weight = 3.0 if is_hire else 2.0

                dept = classifier.top_department(full[:500])
                if not dept:
                    dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}

                signals.append(self._make_signal(
                    firm_id=firm["id"],
                    firm_name=firm["name"],
                    signal_type=signal_type,
                    title=f"[Google News] {title}",
                    body=summary[:900],
                    url=link,
                    department=dept["department"],
                    department_score=dept["score"] * weight,
                    matched_keywords=dept["matched_keywords"],
                    location=self._extract_location(full) or "Middle East",
                    source="Google News",
                    published_date=published.isoformat() if published else None,
                ))

        self.logger.info(f"[{firm['short']}] Google News: {len(signals)} item(s)")
        return signals
