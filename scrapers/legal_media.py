"""
ME Legal Media Scraper  (NEW v3)
==================================
Scrapes regional legal intelligence sources that surface lateral moves
and practice area launches 2-8 weeks BEFORE job postings appear.

Sources:
  - The Oath Magazine (theoath-me.com) — premier ME law journal; Movers & Shakers
  - LexisNexis Middle East (lexismiddleeast.com) — regulatory + law firm press releases
  - The Lawyer (thelawyer.com) — deepest ME law firm coverage; partner moves
  - Gulf News Legal (gulfnews.com/business/legal) — commercial law firm news

Signal type: lateral_hire (weight 3.5) | press_release (weight 2.0)
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from scrapers.base import BaseScraper
from classifier.department import DepartmentClassifier

classifier = DepartmentClassifier()

LEGAL_MEDIA = [
    {
        "id":       "oath",
        "name":     "The Oath Magazine",
        "url":      "https://www.theoath-me.com/news/",
        "movers":   "https://www.theoath-me.com/movers-and-shakers/",
        "base":     "https://www.theoath-me.com",
        "card":     re.compile(r"post|entry|article|news-item|card", re.I),
        "hire_weight": 4.0,   # Movers & Shakers = very high confidence
    },
    {
        "id":       "lexis_me",
        "name":     "LexisNexis Middle East",
        "url":      "https://www.lexismiddleeast.com/news",
        "base":     "https://www.lexismiddleeast.com",
        "card":     re.compile(r"article|post|news|entry|item|card", re.I),
        "hire_weight": 2.5,
    },
    {
        "id":       "thelawyer",
        "name":     "The Lawyer",
        "url":      "https://www.thelawyer.com/section/international/middle-east/",
        "base":     "https://www.thelawyer.com",
        "card":     re.compile(r"article|post|card|entry|story|result", re.I),
        "hire_weight": 3.5,
    },
    {
        "id":       "agbi",
        "name":     "AGBI Legal",
        "url":      "https://agbi.com/legal/",
        "base":     "https://agbi.com",
        "card":     re.compile(r"article|post|card|entry|item", re.I),
        "hire_weight": 2.5,
    },
    {
        "id":       "gulf_news_legal",
        "name":     "Gulf News Legal",
        "url":      "https://gulfnews.com/business/legal",
        "base":     "https://gulfnews.com",
        "card":     re.compile(r"article|card|story|item|result", re.I),
        "hire_weight": 2.0,
    },
]

HIRE_KEYWORDS = [
    "hire", "hires", "hired", "appoint", "appointed", "join", "joins",
    "joined", "lateral", "move", "moves", "partner", "associate",
    "counsel", "welcome", "new office", "expand", "expansion",
    "launch", "launches", "new practice",
]

ME_LOCS = [
    "dubai", "abu dhabi", "riyadh", "doha", "manama", "kuwait city",
    "muscat", "difc", "adgm", "qfc", "middle east", "gulf", "uae",
    "ksa", "saudi", "bahrain", "oman", "qatar",
]


class LegalMediaScraper(BaseScraper):
    name = "LegalMediaScraper"

    def fetch(self, firm: dict) -> list[dict]:
        signals = []
        firm_names = [firm["short"], firm["name"]] + firm.get("alt_names", [])

        for media in LEGAL_MEDIA:
            # Main news page
            signals.extend(self._scrape_page(
                media["url"], firm, firm_names, media, media["hire_weight"]
            ))
            # Movers & Shakers page (higher weight) if available
            if media.get("movers"):
                signals.extend(self._scrape_page(
                    media["movers"], firm, firm_names, media, media["hire_weight"] + 0.5
                ))

        self.logger.info(f"[{firm['short']}] LegalMedia: {len(signals)} signal(s)")
        return signals

    def _scrape_page(self, url, firm, firm_names, media, weight) -> list[dict]:
        resp = self._get(url)
        if not resp:
            return []
        soup    = BeautifulSoup(resp.text, "html.parser")
        signals = []

        articles = soup.find_all(["article","div","li"], class_=media["card"])[:25]
        if not articles:
            # fallback: all <article> tags
            articles = soup.find_all("article")[:25]

        for article in articles:
            text = article.get_text(" ", strip=True)
            if len(text) < 60:
                continue
            # Must mention the firm
            if not any(n.lower() in text.lower() for n in firm_names):
                continue
            # Must mention ME location
            if not any(loc in text.lower() for loc in ME_LOCS):
                continue

            is_hire   = any(kw in text.lower() for kw in HIRE_KEYWORDS)
            is_lawyer = self._is_lawyer_role(text)

            title_tag = article.find(["h1","h2","h3","h4"])
            title     = title_tag.get_text(strip=True) if title_tag else text[:140]
            link      = article.find("a", href=True)
            art_url   = (link["href"] if link and link["href"].startswith("http")
                         else urljoin(media["base"], link["href"]) if link else url)

            dept = classifier.top_department(f"{title} {text[:500]}")
            if not dept:
                dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}

            signal_type = "lateral_hire" if (is_hire and is_lawyer) else "press_release"
            signals.append(self._make_signal(
                firm_id=firm["id"], firm_name=firm["name"],
                signal_type=signal_type,
                title=f"[{media['name']}] {title}",
                body=text[:900], url=art_url,
                department=dept["department"],
                department_score=dept["score"] * (weight if is_hire else weight * 0.5),
                matched_keywords=dept["matched_keywords"],
                location=self._extract_location(text) or "Middle East",
                source=media["name"],
            ))
        return signals
