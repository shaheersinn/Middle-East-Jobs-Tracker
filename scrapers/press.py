"""
Press / News Scraper
=====================
Scrapes firm news pages and legal media for press releases about:
  - New associate / lawyer hires in ME offices
  - New ME office openings or expansions
  - Lateral partner moves to ME

Sources:
  - Firm news pages
  - The Lawyer (thelawyermea.com)
  - Legal Business World (legalbusinessworld.com)
  - Arabian Business
  - IFLR Middle East
  - Chambers Global ME news

Signal type: press_release | lateral_hire
"""

import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from scrapers.base import BaseScraper
from classifier.department import DepartmentClassifier

classifier = DepartmentClassifier()

# ME-focused legal media
LEGAL_MEDIA = [
    {
        "name": "The Lawyer MEA",
        "url":  "https://www.thelawyermea.com/news/",
        "card": re.compile(r"post|article|news-item|entry", re.I),
    },
    {
        "name": "IFLR Middle East",
        "url":  "https://www.iflr.com/middle-east",
        "card": re.compile(r"article|post|item|card|entry", re.I),
    },
    {
        "name": "Legal Business World ME",
        "url":  "https://www.legalbusinessworld.com/middle-east/",
        "card": re.compile(r"post|article|item", re.I),
    },
    {
        "name": "Arabian Business Legal",
        "url":  "https://www.arabianbusiness.com/industries/legal",
        "card": re.compile(r"article|card|item|post", re.I),
    },
    {
        "name": "Chambers Global ME",
        "url":  "https://chambers.com/articles/middle-east",
        "card": re.compile(r"article|card|item|post", re.I),
    },
]

# Keywords signalling a hire or move
HIRE_KEYWORDS = [
    "hire", "hires", "hired", "join", "joins", "joined", "appoint",
    "appoints", "appointed", "welcome", "lateral", "move", "moves",
    "expand", "expansion", "new associate", "new lawyer", "new counsel",
    "new partner", "promoted", "promotion", "open", "opens", "opening",
]

# ME expansion signals in text
ME_EXPANSION_SIGNALS = [
    "middle east", "dubai", "abu dhabi", "difc", "adgm", "doha", "qatar",
    "riyadh", "bahrain", "gulf", "gcc",
]


class PressScraper(BaseScraper):
    name = "PressScraper"

    def fetch(self, firm: dict) -> list[dict]:
        signals = []
        signals.extend(self._scrape_firm_news(firm))
        signals.extend(self._scrape_legal_media(firm))
        return signals

    # ── Firm news page ────────────────────────────────────────────────────

    def _scrape_firm_news(self, firm: dict) -> list[dict]:
        signals = []
        url = firm.get("news_url", "")
        if not url:
            return signals

        resp = self._get(url)
        if not resp:
            return signals

        soup = BeautifulSoup(resp.text, "html.parser")
        articles = soup.find_all(
            ["article", "div", "li"],
            class_=re.compile(r"post|news|article|insight|update|item", re.I),
        )[:30]

        for art in articles:
            text = art.get_text(" ", strip=True)
            if len(text) < 50:
                continue

            # Only care about ME-related items
            if not self._is_me_location(text.lower()):
                continue

            # Detect hire/move type
            is_hire = any(kw in text.lower() for kw in HIRE_KEYWORDS)

            title_tag = art.find(["h2", "h3", "h4", "a", "strong"])
            title = title_tag.get_text(strip=True) if title_tag else text[:150]

            link  = art.find("a", href=True)
            art_url = link["href"] if link else url
            if art_url.startswith("/"):
                from urllib.parse import urlparse
                base = "{u.scheme}://{u.netloc}".format(u=urlparse(url))
                art_url = base + art_url

            signal_type = "lateral_hire" if is_hire else "press_release"

            dept = classifier.top_department(f"{title} {text[:400]}")
            if not dept:
                dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}

            signals.append(self._make_signal(
                firm_id=firm["id"],
                firm_name=firm["name"],
                signal_type=signal_type,
                title=f"[{firm['short']} News] {title}",
                body=text[:900],
                url=art_url,
                department=dept["department"],
                department_score=dept["score"] * (3.0 if is_hire else 1.5),
                matched_keywords=dept["matched_keywords"],
                location=self._extract_location(text) or "Middle East",
                source="Firm News",
            ))

        self.logger.info(f"[{firm['short']}] Firm news: {len(signals)} item(s)")
        return signals

    # ── Legal media ───────────────────────────────────────────────────────

    def _scrape_legal_media(self, firm: dict) -> list[dict]:
        signals = []
        for media in LEGAL_MEDIA:
            try:
                found = self._scrape_one_media(media, firm)
                signals.extend(found)
            except Exception as e:
                self.logger.debug(f"{media['name']} scrape error: {e}")

        self.logger.info(f"[{firm['short']}] Legal media: {len(signals)} item(s)")
        return signals

    def _scrape_one_media(self, media: dict, firm: dict) -> list[dict]:
        signals = []
        resp = self._get(media["url"])
        if not resp:
            return signals

        soup     = BeautifulSoup(resp.text, "html.parser")
        articles = soup.find_all(
            ["article", "div", "li"],
            class_=media["card"],
        )[:25]

        firm_names = [firm["short"], firm["name"]] + firm.get("alt_names", [])

        for art in articles:
            text = art.get_text(" ", strip=True)
            if len(text) < 50:
                continue

            # Must mention the firm
            if not any(n.lower() in text.lower() for n in firm_names):
                continue

            # Must mention ME location
            if not self._is_me_location(text):
                continue

            title_tag = art.find(["h2", "h3", "h4", "a", "strong"])
            title = title_tag.get_text(strip=True) if title_tag else text[:150]

            link = art.find("a", href=True)
            art_url = (
                link["href"] if link and link["href"].startswith("http")
                else urljoin(media["url"], link["href"]) if link
                else media["url"]
            )

            is_hire = any(kw in text.lower() for kw in HIRE_KEYWORDS)
            signal_type = "lateral_hire" if is_hire else "press_release"

            dept = classifier.top_department(f"{title} {text[:400]}")
            if not dept:
                dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}

            signals.append(self._make_signal(
                firm_id=firm["id"],
                firm_name=firm["name"],
                signal_type=signal_type,
                title=f"[{media['name']}] {title}",
                body=text[:900],
                url=art_url,
                department=dept["department"],
                department_score=dept["score"] * (3.0 if is_hire else 1.5),
                matched_keywords=dept["matched_keywords"],
                location=self._extract_location(text) or "Middle East",
                source=media["name"],
            ))

        return signals
