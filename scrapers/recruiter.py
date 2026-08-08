"""
ME Legal Recruiter Scraper  (v3 — massively expanded)
=======================================================
Fixed: Removed dead hosts (guildhall, kershawleonard)
Added 20+ new ME-specialist legal recruiters including:
  - Major, Lindsey & Africa (world's largest legal recruiter)
  - Marsden (75+ ME partner moves tracked in 2025)
  - MRA Search, Clark Burnell, SSQ, Beacon Legal, Pennell Hart
  - Aquis Search (opened Dubai 2024), Seeker Group, EMEA Legal
  - Lateral Link, Robert Walters AE, Hays Legal ME

Recruiter pages fetched ONCE globally and cached (not per-firm × 22).
"""
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from classifier.department import DepartmentClassifier

classifier = DepartmentClassifier()

RECRUITERS = [
    # ── Elite transatlantic / global ──────────────────────────────────────
    {"id": "mla",       "name": "Major, Lindsey & Africa",
     "jobs_url": "https://www.mlaglobal.com/en/jobs",
     "base": "https://www.mlaglobal.com",
     "params": {"location": "Middle East", "practice": "all"},
     "card": re.compile(r"job|listing|card|vacancy|result|position", re.I)},
    {"id": "marsden",   "name": "Marsden Legal Search",
     "jobs_url": "https://www.marsden.co.uk/jobs/",
     "base": "https://www.marsden.co.uk",
     "params": {"location": "Dubai", "type": "law-firm"},
     "card": re.compile(r"job|vacancy|role|listing|card", re.I)},
    {"id": "lateral_link", "name": "Lateral Link",
     "jobs_url": "https://laterallink.com/jobs/",
     "base": "https://laterallink.com",
     "params": {"location": "middle-east"},
     "card": re.compile(r"job|listing|card|vacancy|position", re.I)},
    # ── GCC Specialists ───────────────────────────────────────────────────
    {"id": "taylor_root", "name": "Taylor Root",
     "jobs_url": "https://www.taylorroot.com/jobs/",
     "base": "https://www.taylorroot.com",
     "params": {"location": "middle+east", "sector": "legal"},
     "card": re.compile(r"job|listing|vacancy|role", re.I)},
    {"id": "mra_search", "name": "MRA Search",
     "jobs_url": "https://mrasearch.com/jobs/",
     "base": "https://mrasearch.com",
     "params": {"region": "middle-east"},
     "card": re.compile(r"job|vacancy|role|listing|card", re.I)},
    {"id": "clark_burnell", "name": "Clark Burnell",
     "jobs_url": "https://www.clarkburnell.com/jobs/",
     "base": "https://www.clarkburnell.com",
     "card": re.compile(r"job|vacancy|role|listing|card", re.I)},
    {"id": "ssq",       "name": "SSQ Legal",
     "jobs_url": "https://www.ssq.com/middle-east/",
     "base": "https://www.ssq.com",
     "card": re.compile(r"job|vacancy|role|listing|card|mandate", re.I)},
    {"id": "beacon_legal", "name": "Beacon Legal",
     "jobs_url": "https://beacon-legal.ae/jobs/",
     "base": "https://beacon-legal.ae",
     "card": re.compile(r"job|vacancy|role|listing|card", re.I)},
    {"id": "pennell_hart", "name": "Pennell Hart",
     "jobs_url": "https://pennellhart.com/jobs/",
     "base": "https://pennellhart.com",
     "card": re.compile(r"job|vacancy|role|listing|card", re.I)},
    {"id": "emea_legal", "name": "EMEA Legal",
     "jobs_url": "https://emea.legal/jobs/",
     "base": "https://emea.legal",
     "card": re.compile(r"job|vacancy|role|listing|card", re.I)},
    {"id": "aquis_search", "name": "Aquis Search",
     "jobs_url": "https://www.aquissearch.com/jobs/",
     "base": "https://www.aquissearch.com",
     "card": re.compile(r"job|vacancy|role|listing|card", re.I)},
    {"id": "seeker_group", "name": "Seeker Group",
     "jobs_url": "https://seekergroup.ae/jobs/",
     "base": "https://seekergroup.ae",
     "card": re.compile(r"job|vacancy|role|listing|card", re.I)},
    {"id": "mukadam",   "name": "Mukadam Legal",
     "jobs_url": "https://mukadamlegal.com/jobs/",
     "base": "https://mukadamlegal.com",
     "card": re.compile(r"job|vacancy|role|listing|card", re.I)},
    # ── Large generalists with strong ME desks ────────────────────────────
    {"id": "michael_page", "name": "Michael Page Legal UAE",
     "jobs_url": "https://www.michaelpage.ae/jobs/legal",
     "base": "https://www.michaelpage.ae",
     "card": re.compile(r"job|card|listing|result", re.I)},
    {"id": "robert_half", "name": "Robert Half Legal UAE",
     "jobs_url": "https://www.roberthalf.ae/find-work/legal",
     "base": "https://www.roberthalf.ae",
     "card": re.compile(r"job|listing|result|card", re.I)},
    {"id": "robert_walters", "name": "Robert Walters AE",
     "jobs_url": "https://www.robertwalters.ae/expertise/legal.html",
     "base": "https://www.robertwalters.ae",
     "card": re.compile(r"job|listing|card|vacancy|result", re.I)},
    {"id": "hays_legal", "name": "Hays Legal ME",
     "jobs_url": "https://www.hays.ae/jobs/legal",
     "base": "https://www.hays.ae",
     "card": re.compile(r"job|card|listing|result|vacancy", re.I)},
    {"id": "charterhouse", "name": "Charterhouse ME",
     "jobs_url": "https://www.charterhouseme.ae/jobs/",
     "base": "https://www.charterhouseme.ae",
     "card": re.compile(r"job|listing|vacancy|role|card", re.I)},
    {"id": "cooper_fitch", "name": "Cooper Fitch",
     "jobs_url": "https://cooperfitch.ae/jobs/",
     "base": "https://cooperfitch.ae",
     "params": {"sector": "legal"},
     "card": re.compile(r"job|listing|vacancy|role|card", re.I)},
    {"id": "mackenzie_jones", "name": "Mackenzie Jones",
     "jobs_url": "https://www.mackenziejones.com/jobs/",
     "base": "https://www.mackenziejones.com",
     "card": re.compile(r"job|listing|vacancy|role", re.I)},
    {"id": "anton_murray", "name": "Anton Murray Consulting",
     "jobs_url": "https://www.antonmurray.com/jobs/",
     "base": "https://www.antonmurray.com",
     "params": {"category": "legal"},
     "card": re.compile(r"job|vacancy|role|listing", re.I)},
]

_RECRUITER_CACHE: dict = {}
_CACHE_POPULATED = False


class RecruiterScraper(BaseScraper):
    """Scrapes ME legal recruiters ONCE per process (module-level cache)."""
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
        total = 0
        for rec in RECRUITERS:
            try:
                postings = self._scrape_one(rec)
                _RECRUITER_CACHE[rec["id"]] = postings
                total += len(postings)
            except Exception as e:
                self.logger.warning(f"Recruiter {rec['name']} error: {e}")
                _RECRUITER_CACHE[rec["id"]] = []
        self.logger.info(f"Recruiter cache populated: {total} total posting(s) across {len(RECRUITERS)} agencies")

    def _scrape_one(self, rec: dict) -> list:
        resp = self._get(rec["jobs_url"], params=rec.get("params") or {})
        if not resp:
            return []
        soup  = BeautifulSoup(resp.text, "html.parser")
        cards = soup.find_all(["div","li","article"], class_=rec["card"])
        if not cards:
            cards = soup.find_all(["div","li"], class_=re.compile(r"job|vacancy|role|listing|card|item", re.I))
        results = []
        for card in cards[:60]:
            text = card.get_text(" ", strip=True)
            if len(text) < 30: continue
            if not self._is_lawyer_role(text): continue
            if not self._is_me_location(text): continue
            title_tag = card.find(["h2","h3","h4","strong","a"])
            title = title_tag.get_text(strip=True) if title_tag else text[:130]
            link  = card.find("a", href=True)
            url   = (link["href"] if link and link["href"].startswith("http")
                     else urljoin(rec["base"], link["href"]) if link else rec["jobs_url"])
            dept = classifier.top_department(f"{title} {text[:400]}")
            if not dept:
                dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}
            results.append({
                "title": title, "body": text[:900], "url": url,
                "location": self._extract_location(text) or "Middle East",
                "seniority": self._extract_seniority(title),
                "department": dept["department"], "department_score": dept["score"],
                "matched_keywords": dept["matched_keywords"],
                "_raw": text.lower(),
            })
        return results

    def _matches_firm(self, raw: str, firm: dict) -> bool:
        return any(c.lower() in raw for c in
                   [firm["short"], firm["name"]] + firm.get("alt_names", []))

    def _to_signal(self, p: dict, firm: dict, rec_name: str) -> dict:
        return self._make_signal(
            firm_id=firm["id"], firm_name=firm["name"],
            signal_type="recruiter_posting",
            title=f"[{rec_name}] {p['title']}", body=p["body"], url=p["url"],
            department=p["department"],
            department_score=p["department_score"] * 2.5,
            matched_keywords=p["matched_keywords"],
            location=p["location"], seniority=p["seniority"],
            source="Recruiter", recruiter=rec_name,
        )
