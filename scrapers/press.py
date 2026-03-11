"""
Press / News Scraper  (v2 — dead hosts removed)
================================================
FIXED: Removed thelawyermea.com (DNS fail) and legalbusinessworld.com (timeout)
ADDED: Law.com International, Gulf News Business, AGBI (Arabian Gulf Business Insight)

Signal type: press_release | lateral_hire
"""

import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from scrapers.base import BaseScraper
from classifier.department import DepartmentClassifier

classifier = DepartmentClassifier()

# Dead domains removed: thelawyermea.com, legalbusinessworld.com
LEGAL_MEDIA = [
    {
        "name": "IFLR Middle East",
        "url":  "https://www.iflr.com/middle-east",
        "card": re.compile(r"article|post|item|card|entry", re.I),
    },
    {
        "name": "Arabian Business Legal",
        "url":  "https://www.arabianbusiness.com/industries/legal",
        "card": re.compile(r"article|card|item|post", re.I),
    },
    {
        "name": "Law.com International",
        "url":  "https://www.law.com/international-edition/",
        "card": re.compile(r"article|card|item|story|result", re.I),
    },
    {
        "name": "Gulf News Business",
        "url":  "https://gulfnews.com/business",
        "card": re.compile(r"article|card|item|story|result", re.I),
    },
    {
        "name": "AGBI Legal",
        "url":  "https://agbi.com/legal/",
        "card": re.compile(r"article|card|item|post|entry", re.I),
    },
]

HIRE_KEYWORDS = [
    "hire", "hires", "hired", "join", "joins", "joined", "appoint",
    "appointed", "lateral", "move", "welcome", "new partner", "new associate",
    "new counsel", "new office", "expand",
]

ME_HIRE_SIGNALS = [
    "dubai", "abu dhabi", "riyadh", "doha", "manama", "kuwait", "muscat",
    "difc", "adgm", "qfc", "middle east", "gulf", "uae", "ksa", "saudi",
]


class PressScraper(BaseScraper):
    name = "PressScraper"

    def fetch(self, firm: dict) -> list[dict]:
        signals = []
        signals.extend(self._scrape_firm_news(firm))
        signals.extend(self._scrape_legal_media(firm))
        return signals

    def _scrape_firm_news(self, firm: dict) -> list[dict]:
        news_url = firm.get("news_url", "")
        if not news_url:
            return []

        resp = self._get(news_url)
        if not resp:
            return []

        soup    = BeautifulSoup(resp.text, "html.parser")
        signals = []

        for article in soup.find_all(["article","div","li"],
                                     class_=re.compile(r"post|news|press|article|item|entry", re.I))[:20]:
            text = article.get_text(" ", strip=True)
            if len(text) < 50:
                continue

            is_hire = any(kw in text.lower() for kw in HIRE_KEYWORDS)
            is_me   = any(loc in text.lower() for loc in ME_HIRE_SIGNALS)
            is_lawyer = self._is_lawyer_role(text)

            if not (is_hire and is_me):
                continue

            title_tag = article.find(["h1","h2","h3","h4"])
            title = title_tag.get_text(strip=True) if title_tag else text[:140]
            link  = article.find("a", href=True)
            url   = (link["href"] if link and link["href"].startswith("http")
                     else urljoin(firm.get("news_url",""), link["href"]) if link else news_url)

            dept = classifier.top_department(f"{title} {text[:500]}")
            if not dept:
                dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}

            signal_type = "lateral_hire" if is_lawyer else "press_release"
            weight = 3.0 if is_lawyer and is_hire else 1.5

            signals.append(self._make_signal(
                firm_id=firm["id"], firm_name=firm["name"],
                signal_type=signal_type,
                title=f"[Firm News] {title}", body=text[:900], url=url,
                department=dept["department"],
                department_score=dept["score"] * weight,
                matched_keywords=dept["matched_keywords"],
                location=self._extract_location(text) or "Middle East",
                source="Firm News",
            ))

        self.logger.info(f"[{firm['short']}] Firm news: {len(signals)} item(s)")
        return signals

    def _scrape_legal_media(self, firm: dict) -> list[dict]:
        signals = []
        firm_names = [firm["short"], firm["name"]] + firm.get("alt_names", [])

        for media in LEGAL_MEDIA:
            resp = self._get(media["url"])
            if not resp:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            for article in soup.find_all(["article","div","li"],
                                          class_=media["card"])[:20]:
                text = article.get_text(" ", strip=True)
                if len(text) < 50:
                    continue
                if not any(n.lower() in text.lower() for n in firm_names):
                    continue
                if not any(loc in text.lower() for loc in ME_HIRE_SIGNALS):
                    continue
                is_hire = any(kw in text.lower() for kw in HIRE_KEYWORDS)
                if not is_hire:
                    continue

                title_tag = article.find(["h1","h2","h3","h4"])
                title = title_tag.get_text(strip=True) if title_tag else text[:140]
                link  = article.find("a", href=True)
                url   = (link["href"] if link and link["href"].startswith("http")
                         else urljoin(media["url"], link["href"]) if link else media["url"])

                dept = classifier.top_department(f"{title} {text[:500]}")
                if not dept:
                    dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}

                signals.append(self._make_signal(
                    firm_id=firm["id"], firm_name=firm["name"],
                    signal_type="lateral_hire" if self._is_lawyer_role(text) else "press_release",
                    title=f"[{media['name']}] {title}", body=text[:900], url=url,
                    department=dept["department"],
                    department_score=dept["score"] * 2.5,
                    matched_keywords=dept["matched_keywords"],
                    location=self._extract_location(text) or "Middle East",
                    source=media["name"],
                ))

        self.logger.info(f"[{firm['short']}] Legal media: {len(signals)} item(s)")
        return signals
