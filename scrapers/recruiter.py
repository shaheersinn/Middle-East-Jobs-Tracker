"""
ME Legal Recruiter Scraper
===========================
Scrapes specialist legal recruitment agencies that advertise
lawyer / associate roles in the Middle East on behalf of US law firms.

Agencies covered:
  - Kershaw Leonard          (kershawleonard.net)
  - Mackenzie Jones          (mackenziejones.com)
  - Michael Page Legal UAE   (michaelpage.ae)
  - Taylor Root              (taylorroot.com)
  - Robert Half Legal UAE    (roberthalf.ae)
  - Heidrick & Struggles     (heidrick.com)
  - Anton Murray Consulting  (antonmurray.com)
  - Charterhouse             (charterhouseme.ae)
  - Cooper Fitch             (cooperfitch.ae)
  - Guildhall                (guildhall.ae)

For each posting it also tries to identify which US firm is the end client.
Signal type: recruiter_posting
"""

import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

from scrapers.base import BaseScraper
from classifier.department import DepartmentClassifier
from firms import FIRMS, ME_LOCATIONS

classifier = DepartmentClassifier()

# ── Recruiter definitions ─────────────────────────────────────────────────

RECRUITERS = [
    {
        "id":   "kershaw_leonard",
        "name": "Kershaw Leonard",
        "base": "https://www.kershawleonard.net",
        "jobs_url": "https://www.kershawleonard.net/jobs/",
        "search_params": {"sector": "legal", "location": "middle east"},
        "card_selector": re.compile(r"job|listing|vacancy|role|position", re.I),
    },
    {
        "id":   "mackenzie_jones",
        "name": "Mackenzie Jones",
        "base": "https://www.mackenziejones.com",
        "jobs_url": "https://www.mackenziejones.com/jobs/",
        "search_params": {"sector": "legal"},
        "card_selector": re.compile(r"job|listing|vacancy|role", re.I),
    },
    {
        "id":   "michael_page_legal",
        "name": "Michael Page Legal UAE",
        "base": "https://www.michaelpage.ae",
        "jobs_url": "https://www.michaelpage.ae/jobs/legal",
        "search_params": {},
        "card_selector": re.compile(r"job|card|listing|result", re.I),
    },
    {
        "id":   "taylor_root",
        "name": "Taylor Root",
        "base": "https://www.taylorroot.com",
        "jobs_url": "https://www.taylorroot.com/jobs/",
        "search_params": {"location": "middle+east", "sector": "legal"},
        "card_selector": re.compile(r"job|listing|vacancy|role", re.I),
    },
    {
        "id":   "robert_half_legal",
        "name": "Robert Half Legal UAE",
        "base": "https://www.roberthalf.ae",
        "jobs_url": "https://www.roberthalf.ae/find-work/legal",
        "search_params": {},
        "card_selector": re.compile(r"job|listing|result|card", re.I),
    },
    {
        "id":   "anton_murray",
        "name": "Anton Murray Consulting",
        "base": "https://www.antonmurray.com",
        "jobs_url": "https://www.antonmurray.com/jobs/",
        "search_params": {"category": "legal"},
        "card_selector": re.compile(r"job|vacancy|role|listing", re.I),
    },
    {
        "id":   "charterhouse",
        "name": "Charterhouse ME",
        "base": "https://www.charterhouseme.ae",
        "jobs_url": "https://www.charterhouseme.ae/jobs/legal/",
        "search_params": {},
        "card_selector": re.compile(r"job|listing|vacancy|role", re.I),
    },
    {
        "id":   "cooper_fitch",
        "name": "Cooper Fitch",
        "base": "https://cooperfitch.ae",
        "jobs_url": "https://cooperfitch.ae/jobs/?sector=legal",
        "search_params": {},
        "card_selector": re.compile(r"job|listing|vacancy|role|card", re.I),
    },
    {
        "id":   "guildhall",
        "name": "Guildhall",
        "base": "https://www.guildhall.ae",
        "jobs_url": "https://www.guildhall.ae/legal-jobs/",
        "search_params": {},
        "card_selector": re.compile(r"job|vacancy|role|listing", re.I),
    },
    {
        "id":   "heidrick_me",
        "name": "Heidrick & Struggles ME",
        "base": "https://www.heidrick.com",
        "jobs_url": "https://www.heidrick.com/en/about/careers",
        "search_params": {"region": "middle-east", "function": "legal"},
        "card_selector": re.compile(r"job|listing|role|position", re.I),
    },
]

# All firm name fragments for client matching
FIRM_FRAGMENTS = []
for f in FIRMS:
    FIRM_FRAGMENTS.append((f["id"], f["short"]))
    for alt in f.get("alt_names", []):
        FIRM_FRAGMENTS.append((f["id"], alt))


class RecruiterScraper(BaseScraper):
    """
    Aggregates legal associate job listings from ME specialist recruiters.
    Runs independently (not per-firm) and attributes postings to the
    matching US firm where the client can be identified.
    """

    name = "RecruiterScraper"

    def fetch(self, firm: dict) -> list[dict]:
        """
        This scraper is firm-agnostic — it scans all recruiters for any
        mention of the target firm, returning matching postings.
        """
        signals = []
        for rec in RECRUITERS:
            try:
                postings = self._scrape_recruiter(rec)
                for p in postings:
                    # Match back to firm
                    if self._matches_firm(p["_raw_text"], firm):
                        p.pop("_raw_text", None)
                        signals.append(p)
            except Exception as e:
                self.logger.warning(f"Recruiter {rec['name']} error: {e}")
        self.logger.info(f"[{firm['short']}] Recruiter: {len(signals)} posting(s)")
        return signals

    # ── Recruiter scraping ────────────────────────────────────────────────

    def _scrape_recruiter(self, rec: dict) -> list[dict]:
        """Fetch and parse one recruiter's jobs page."""
        resp = self._get(rec["jobs_url"], params=rec.get("search_params") or {})
        if not resp:
            return []

        soup  = BeautifulSoup(resp.text, "html.parser")
        cards = soup.find_all(
            ["div", "li", "article", "section"],
            class_=rec["card_selector"],
        )

        if not cards:
            # Broad fallback
            cards = soup.find_all(
                ["div", "li"],
                class_=re.compile(r"job|vacancy|role|listing|card|item", re.I),
            )

        raw_postings = []
        for card in cards[:40]:
            text = card.get_text(separator=" ", strip=True)
            if len(text) < 30:
                continue

            # Must be a lawyer role
            if not self._is_lawyer_role(text):
                continue

            # Must be ME location
            if not self._is_me_location(text):
                continue

            title_tag = card.find(["h2", "h3", "h4", "strong", "a"])
            title = title_tag.get_text(strip=True) if title_tag else text[:130]

            # Resolve job URL
            job_url = rec["jobs_url"]
            link    = card.find("a", href=True)
            if link:
                href = link["href"]
                job_url = href if href.startswith("http") else urljoin(rec["base"], href)

            location  = self._extract_location(text) or "Middle East"
            seniority = self._extract_seniority(title)

            dept = classifier.top_department(f"{title} {text[:500]}")
            if not dept:
                dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}

            raw_postings.append({
                "title":            title,
                "body":             text[:1000],
                "url":              job_url,
                "location":         location,
                "seniority":        seniority,
                "department":       dept["department"],
                "department_score": dept["score"],
                "matched_keywords": dept["matched_keywords"],
                "recruiter":        rec["name"],
                "_raw_text":        text.lower(),
            })

        return raw_postings

    # ── Client firm matching ──────────────────────────────────────────────

    def _matches_firm(self, raw_text: str, firm: dict) -> bool:
        """
        Return True if the raw text of a posting mentions the target firm.
        Checks short name, full name and all alt_names.
        """
        candidates = [firm["short"], firm["name"]] + firm.get("alt_names", [])
        for name in candidates:
            if name.lower() in raw_text:
                return True
        return False

    # ── Signal builder adapter ────────────────────────────────────────────

    def _to_signal(self, posting: dict, firm: dict) -> dict:
        return self._make_signal(
            firm_id=firm["id"],
            firm_name=firm["name"],
            signal_type="recruiter_posting",
            title=f"[{posting['recruiter']}] {posting['title']}",
            body=posting["body"],
            url=posting["url"],
            department=posting["department"],
            department_score=posting["department_score"] * 2.0,  # recruiter postings weighted higher
            matched_keywords=posting["matched_keywords"],
            location=posting["location"],
            seniority=posting["seniority"],
            source="Recruiter",
            recruiter=posting["recruiter"],
        )
