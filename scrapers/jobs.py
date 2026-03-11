"""
Firm Careers Page Scraper
==========================
Scrapes each US firm's own careers/jobs pages, filtering for:
  1. Roles located in Middle East offices (Dubai, Abu Dhabi, Qatar, etc.)
  2. Lawyer / associate seniority only (no paralegals, support staff, etc.)

Sources scraped per firm:
  - Global careers page
  - ME office-specific career pages
  - /careers/lawyers, /careers/attorneys variants

Signal type: job_posting
"""

import re
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from classifier.department import DepartmentClassifier

classifier = DepartmentClassifier()

# Seniority multipliers for scoring
SENIORITY_WEIGHTS = {
    "partner":          3.5,
    "counsel":          2.5,
    "senior counsel":   2.5,
    "of counsel":       2.5,
    "senior associate": 2.2,
    "mid-level":        2.0,
    "associate":        2.0,
    "attorney":         1.8,
    "lawyer":           1.8,
    "solicitor":        1.8,
    "trainee":          1.5,
    "legal trainee":    1.5,
}

# Extra path patterns to try on firm websites
CAREER_PATH_VARIANTS = [
    "/careers",
    "/en/careers",
    "/en-us/careers",
    "/careers/lawyers",
    "/careers/attorneys",
    "/careers/associates",
    "/careers/professionals",
    "/careers/legal-professionals",
    "/about-us/careers",
    "/join-us",
    "/careers/opportunities",
    "/careers/open-positions",
]


class JobsScraper(BaseScraper):
    name = "JobsScraper"

    def fetch(self, firm: dict) -> list[dict]:
        signals = []
        signals.extend(self._scrape_careers_page(firm))
        signals.extend(self._scrape_me_office_pages(firm))
        return signals

    # ── Firm global / ME careers pages ───────────────────────────────────

    def _scrape_careers_page(self, firm: dict) -> list[dict]:
        signals   = []
        base      = firm["website"].rstrip("/")
        tried     = set()

        # Build URL list: configured URL first, then variants
        urls_to_try = []
        if firm.get("careers_url"):
            urls_to_try.append(firm["careers_url"])
        for path in CAREER_PATH_VARIANTS:
            candidate = base + path
            if candidate not in urls_to_try:
                urls_to_try.append(candidate)

        for url in urls_to_try:
            if url in tried:
                continue
            tried.add(url)

            resp = self._get(url)
            if not resp:
                continue

            found = self._parse_jobs_page(resp.text, url, firm)
            signals.extend(found)

            if found:
                break  # found jobs on this URL — no need to try more variants

        self.logger.info(f"[{firm['short']}] Careers page: {len(signals)} job(s)")
        return signals

    def _scrape_me_office_pages(self, firm: dict) -> list[dict]:
        """Scrape office-specific pages listed in firm['me_offices']."""
        signals = []
        for city, url in firm.get("me_offices", {}).items():
            resp = self._get(url)
            if not resp:
                continue
            # Look for a jobs/careers section on the office page
            soup = BeautifulSoup(resp.text, "html.parser")
            # Check if page references jobs
            page_text = soup.get_text(" ", strip=True)
            if not any(w in page_text.lower() for w in ["vacancies", "job", "career", "opening", "hiring", "associate"]):
                continue
            found = self._parse_jobs_page(resp.text, url, firm, default_location=city)
            signals.extend(found)

        self.logger.info(f"[{firm['short']}] ME office pages: {len(signals)} job(s)")
        return signals

    # ── Parser ────────────────────────────────────────────────────────────

    def _parse_jobs_page(
        self,
        html: str,
        page_url: str,
        firm: dict,
        default_location: str = "",
    ) -> list[dict]:
        """Parse job cards from a careers HTML page."""
        signals = []
        soup    = BeautifulSoup(html, "html.parser")

        # Find job cards using common class patterns
        cards = soup.find_all(
            ["div", "li", "article", "tr"],
            class_=re.compile(
                r"job|posting|position|opening|opportunity|career|vacancy|listing|role",
                re.I,
            ),
        )

        # Fallback: search all anchor tags that look like job links
        if not cards:
            cards = soup.find_all("a", href=re.compile(r"job|career|vacanc|position|role", re.I))

        cards = cards[:50]  # process at most 50 per page

        for card in cards:
            text = card.get_text(separator=" ", strip=True)
            if len(text) < 30:
                continue

            # Extract title
            title_tag = card.find(["h2", "h3", "h4", "strong", "a"])
            title = title_tag.get_text(strip=True) if title_tag else text[:140]
            if len(title) < 5:
                continue

            # ── Associate / lawyer filter ──────────────────────────────
            if not self._is_lawyer_role(title):
                # Try wider text in case seniority is in description
                if not self._is_lawyer_role(text[:200]):
                    continue

            # ── ME location filter ─────────────────────────────────────
            location = self._extract_location(title + " " + text) or default_location
            if not location:
                # If we still have no location, check firm's known ME cities
                known_cities = list(firm.get("me_offices", {}).keys())
                if known_cities:
                    location = known_cities[0]
                else:
                    continue  # can't confirm ME location — skip

            seniority = self._extract_seniority(title)
            weight    = self._seniority_weight(title)

            dept = classifier.top_department(f"{title} {text[:400]}")
            if not dept:
                dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}

            # Build job URL if card is an anchor
            job_url = page_url
            if card.name == "a" and card.get("href"):
                href = card["href"]
                if href.startswith("http"):
                    job_url = href
                elif href.startswith("/"):
                    from urllib.parse import urlparse
                    base = "{u.scheme}://{u.netloc}".format(u=urlparse(page_url))
                    job_url = base + href

            signals.append(self._make_signal(
                firm_id=firm["id"],
                firm_name=firm["name"],
                signal_type="job_posting",
                title=f"[{firm['short']}] {title}",
                body=text[:900],
                url=job_url,
                department=dept["department"],
                department_score=dept["score"] * weight,
                matched_keywords=dept["matched_keywords"],
                location=location,
                seniority=seniority,
                source="Firm Careers Page",
            ))

        return signals

    # ── Helpers ───────────────────────────────────────────────────────────

    def _seniority_weight(self, title: str) -> float:
        t = title.lower()
        for kw, w in SENIORITY_WEIGHTS.items():
            if kw in t:
                return w
        return 1.5  # default for unclassified lawyer roles
