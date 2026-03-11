"""
ME Legal Recruiter Scraper  (v2 — fixed)
=========================================
Key fixes vs v1:
  - Recruiter pages fetched ONCE globally and cached (not per-firm x 22)
  - Removed dead hosts: guildhall.ae (DNS fail), kershawleonard.net (SSL)
  - Added: Hays Legal ME, eFinancialCareers ME, Noor Staffing
  - verify=False handled by base._get() for SSL-problem hosts

Signal type: recruiter_posting
"""

import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from classifier.department import DepartmentClassifier

classifier = DepartmentClassifier()

RECRUITERS = [
    {"id": "michael_page_legal",  "name": "Michael Page Legal UAE",
     "base": "https://www.michaelpage.ae",
     "jobs_url": "https://www.michaelpage.ae/jobs/legal",
     "card_selector": re.compile(r"job|card|listing|result", re.I)},
    {"id": "taylor_root",  "name": "Taylor Root",
     "base": "https://www.taylorroot.com",
     "jobs_url": "https://www.taylorroot.com/jobs/",
     "params": {"location": "middle+east", "sector": "legal"},
     "card_selector": re.compile(r"job|listing|vacancy|role", re.I)},
    {"id": "robert_half_legal",  "name": "Robert Half Legal UAE",
     "base": "https://www.roberthalf.ae",
     "jobs_url": "https://www.roberthalf.ae/find-work/legal",
     "card_selector": re.compile(r"job|listing|result|card", re.I)},
    {"id": "anton_murray",  "name": "Anton Murray Consulting",
     "base": "https://www.antonmurray.com",
     "jobs_url": "https://www.antonmurray.com/jobs/",
     "params": {"category": "legal"},
     "card_selector": re.compile(r"job|vacancy|role|listing", re.I)},
    {"id": "charterhouse",  "name": "Charterhouse ME",
     "base": "https://www.charterhouseme.ae",
     "jobs_url": "https://www.charterhouseme.ae/jobs/",
     "card_selector": re.compile(r"job|listing|vacancy|role|card", re.I)},
    {"id": "cooper_fitch",  "name": "Cooper Fitch",
     "base": "https://cooperfitch.ae",
     "jobs_url": "https://cooperfitch.ae/jobs/",
     "params": {"sector": "legal"},
     "card_selector": re.compile(r"job|listing|vacancy|role|card", re.I)},
    {"id": "mackenzie_jones",  "name": "Mackenzie Jones",
     "base": "https://www.mackenziejones.com",
     "jobs_url": "https://www.mackenziejones.com/jobs/",
     "card_selector": re.compile(r"job|listing|vacancy|role", re.I)},
    {"id": "hays_legal",  "name": "Hays Legal ME",
     "base": "https://www.hays.ae",
     "jobs_url": "https://www.hays.ae/jobs/legal",
     "card_selector": re.compile(r"job|card|listing|result|vacancy", re.I)},
    {"id": "efinancial_legal",  "name": "eFinancialCareers ME",
     "base": "https://www.efinancialcareers.ae",
     "jobs_url": "https://www.efinancialcareers.ae/jobs/Legal/in-United-Arab-Emirates",
     "card_selector": re.compile(r"job|card|listing|result", re.I)},
]

_RECRUITER_CACHE: dict = {}
_CACHE_POPULATED = False


class RecruiterScraper(BaseScraper):
    """Scrapes ME legal recruiters ONCE per process (cached). fetch(firm) matches."""
    name = "RecruiterScraper"

    def fetch(self, firm: dict) -> list[dict]:
        global _CACHE_POPULATED
        if not _CACHE_POPULATED:
            self._populate_cache()
            _CACHE_POPULATED = True

        signals = []
        for rec_id, postings in _RECRUITER_CACHE.items():
            rec_name = next((r["name"] for r in RECRUITERS if r["id"] == rec_id), rec_id)
            for p in postings:
                if self._matches_firm(p["_raw"], firm):
                    signals.append(self._to_signal(p, firm, rec_name))

        self.logger.info(f"[{firm['short']}] Recruiter (cache): {len(signals)} posting(s)")
        return signals

    def _populate_cache(self):
        global _RECRUITER_CACHE
        for rec in RECRUITERS:
            try:
                postings = self._scrape_one(rec)
                _RECRUITER_CACHE[rec["id"]] = postings
                self.logger.info(f"Recruiter cache: {rec['name']} -> {len(postings)} posting(s)")
            except Exception as e:
                self.logger.warning(f"Recruiter {rec['name']} error: {e}")
                _RECRUITER_CACHE[rec["id"]] = []

    def _scrape_one(self, rec: dict) -> list:
        resp = self._get(rec["jobs_url"], params=rec.get("params") or {})
        if not resp:
            return []

        soup  = BeautifulSoup(resp.text, "html.parser")
        cards = soup.find_all(["div", "li", "article"], class_=rec["card_selector"])
        if not cards:
            cards = soup.find_all(["div", "li"],
                                  class_=re.compile(r"job|vacancy|role|listing|card|item", re.I))

        results = []
        for card in cards[:50]:
            text = card.get_text(" ", strip=True)
            if len(text) < 30 or not self._is_lawyer_role(text):
                continue
            if not self._is_me_location(text):
                continue

            title_tag = card.find(["h2", "h3", "h4", "strong", "a"])
            title = title_tag.get_text(strip=True) if title_tag else text[:130]
            link  = card.find("a", href=True)
            job_url = (link["href"] if link and link["href"].startswith("http")
                       else urljoin(rec["base"], link["href"]) if link else rec["jobs_url"])

            location  = self._extract_location(text) or "Middle East"
            seniority = self._extract_seniority(title)
            dept = classifier.top_department(f"{title} {text[:400]}")
            if not dept:
                dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}

            results.append({
                "title": title, "body": text[:900], "url": job_url,
                "location": location, "seniority": seniority,
                "department": dept["department"], "department_score": dept["score"],
                "matched_keywords": dept["matched_keywords"],
                "_raw": text.lower(),
            })
        return results

    def _matches_firm(self, raw: str, firm: dict) -> bool:
        candidates = [firm["short"], firm["name"]] + firm.get("alt_names", [])
        return any(c.lower() in raw for c in candidates)

    def _to_signal(self, p: dict, firm: dict, rec_name: str) -> dict:
        return self._make_signal(
            firm_id=firm["id"], firm_name=firm["name"],
            signal_type="recruiter_posting",
            title=f"[{rec_name}] {p['title']}",
            body=p["body"], url=p["url"],
            department=p["department"],
            department_score=p["department_score"] * 2.5,
            matched_keywords=p["matched_keywords"],
            location=p["location"], seniority=p["seniority"],
            source="Recruiter", recruiter=rec_name,
        )
