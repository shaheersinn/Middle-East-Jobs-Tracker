"""
ATS (Applicant Tracking System) Scraper
=========================================
Hits public JSON APIs from Greenhouse, Lever, and Workday — these are
designed for public consumption and cannot block GitHub Actions runners.
This bypasses Cloudflare/WAF that blocks the HTML career pages.

APIs used:
  Greenhouse: https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
  Lever:      https://api.lever.co/v0/postings/{slug}?mode=json
  Workday:    https://{tenant}.wd5.myworkdayjobs.com/wday/cxs/en-US/{jobsite}/jobs (POST)

Signal type: job_posting  (same as JobsScraper, weight 2.5)
"""
import logging, json
from typing import Optional

import requests

from scrapers.base import BaseScraper, JSON_HEADERS, USER_AGENTS
from classifier.department import DepartmentClassifier

logger     = logging.getLogger("ATSScraper")
classifier = DepartmentClassifier()

# ── ATS platform mappings ─────────────────────────────────────────────────────
# Format: firm_id → (platform, identifier)
ATS_MAP = {
    # Greenhouse — public REST API, returns all jobs as JSON
    "gibson_dunn":      ("greenhouse", "gibsondunn"),
    "jones_day":        ("greenhouse", "jonesday"),
    "milbank":          ("greenhouse", "milbank"),
    "simpson_thacher":  ("greenhouse", "simpsonthachers"),
    "sullivan_cromwell":("greenhouse", "sullivancromwell"),
    "king_spalding":    ("greenhouse", "kingspalding"),
    "mayer_brown":      ("greenhouse", "mayerbrown"),
    "paul_hastings":    ("greenhouse", "paulhastings"),
    "omelveny":         ("greenhouse", "omelveny"),
    "skadden":          ("greenhouse", "skadden"),

    # Lever — public REST API, returns postings as JSON
    "greenberg_traurig":("lever",      "greenbergtraurig"),
    "mcdermott":        ("lever",      "mcdermottllp"),
    "morgan_lewis":     ("lever",      "morganlewis"),

    # Workday — POST to SOAP-like JSON API
    # tenant: Workday subdomain; jobsite: the named job site in their system
    "latham":           ("workday",    ("lathamwatkins",   "LathamWatkinsCareers")),
    "kirkland":         ("workday",    ("kirkland",         "KirklandEllisCareers")),
    "white_case":       ("workday",    ("whitecase",        "WhiteCaseCareers")),
    "baker_mckenzie":   ("workday",    ("bakermckenzie",    "BakerMcKenzieCareers")),
    "dla_piper":        ("workday",    ("dlapiper",         "DLAPiperCareers")),
    "norton_rose":      ("workday",    ("nortonrosefulbright", "NortonRoseFulbrightCareers")),
    "hogan_lovells":    ("workday",    ("hoganlovells",     "HoganLovellsCareers")),
    "reed_smith":       ("workday",    ("reedsmith",        "ReedSmithCareers")),
    "dentons":          ("workday",    ("dentons",          "DentonsCareers")),
    "squire_patton":    ("workday",    ("squirepattonboggs","SquirePattonBoggsCareers")),
    "shearman":         ("workday",    ("aoshearman",       "AOShearmanCareers")),
}

ME_KEYWORDS = [
    "dubai", "abu dhabi", "riyadh", "doha", "manama", "muscat",
    "kuwait", "sharjah", "uae", "saudi", "qatar", "bahrain", "oman",
    "middle east", "difc", "adgm", "qfc", "gcc", "gulf",
]


class ATSScraper(BaseScraper):
    """Scrape firm job postings via public ATS JSON APIs."""

    name = "ATSScraper"

    def fetch(self, firm: dict) -> list[dict]:
        fid = firm["id"]
        if fid not in ATS_MAP:
            return []
        platform, identifier = ATS_MAP[fid]
        try:
            if platform == "greenhouse":
                return self._greenhouse(firm, identifier)
            if platform == "lever":
                return self._lever(firm, identifier)
            if platform == "workday":
                tenant, jobsite = identifier
                return self._workday(firm, tenant, jobsite)
        except Exception as e:
            logger.debug(f"[{firm['short']}] ATS error ({platform}): {e}")
        return []

    # ── Greenhouse ────────────────────────────────────────────────────────

    def _greenhouse(self, firm: dict, slug: str) -> list[dict]:
        url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
        data = self._fetch_json(url)
        if not data:
            return []
        jobs = data.get("jobs", [])
        results = []
        for job in jobs:
            title     = job.get("title", "")
            locations = " ".join(o.get("name", "") for o in job.get("offices", []))
            text      = f"{title} {locations} {job.get('content', '')[:400]}"
            if not self._is_me_location(text):
                continue
            if not self._is_lawyer_role(title):
                continue
            location = self._extract_location(text)
            dept     = classifier.top_department(text) or {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}
            results.append(self._make_signal(
                firm_id=firm["id"], firm_name=firm["name"],
                signal_type="job_posting",
                title=f"[{firm['short']}] {title}",
                body=text[:900],
                url=job.get("absolute_url", ""),
                department=dept["department"],
                department_score=dept["score"] * 2.0,
                matched_keywords=dept["matched_keywords"],
                location=location or next(iter(firm.get("me_offices", {})), ""),
                seniority=self._extract_seniority(title),
                source="Greenhouse ATS",
            ))
        logger.info(f"[{firm['short']}] Greenhouse: {len(results)} ME role(s)")
        return results

    # ── Lever ─────────────────────────────────────────────────────────────

    def _lever(self, firm: dict, slug: str) -> list[dict]:
        url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
        data = self._fetch_json(url)
        if not data or not isinstance(data, list):
            return []
        results = []
        for job in data:
            title    = job.get("text", "")
            cats     = job.get("categories", {})
            location = cats.get("location", "") or cats.get("allLocations", "")
            if isinstance(location, list):
                location = " ".join(location)
            text = f"{title} {location} {job.get('descriptionPlain', '')[:400]}"
            if not self._is_me_location(text):
                continue
            if not self._is_lawyer_role(title):
                continue
            loc  = self._extract_location(text)
            dept = classifier.top_department(text) or {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}
            results.append(self._make_signal(
                firm_id=firm["id"], firm_name=firm["name"],
                signal_type="job_posting",
                title=f"[{firm['short']}] {title}",
                body=text[:900],
                url=job.get("hostedUrl", ""),
                department=dept["department"],
                department_score=dept["score"] * 2.0,
                matched_keywords=dept["matched_keywords"],
                location=loc or next(iter(firm.get("me_offices", {})), ""),
                seniority=self._extract_seniority(title),
                source="Lever ATS",
            ))
        logger.info(f"[{firm['short']}] Lever: {len(results)} ME role(s)")
        return results

    # ── Workday ───────────────────────────────────────────────────────────

    def _workday(self, firm: dict, tenant: str, jobsite: str) -> list[dict]:
        """
        Workday exposes a CXS (Candidate Experience) JSON API via POST.
        We search for "associate" roles in ME locations.
        """
        base_url = f"https://{tenant}.wd5.myworkdayjobs.com"
        api_url  = f"{base_url}/wday/cxs/en-US/{jobsite}/jobs"
        # Try several tenants (wd1..wd5) since different accounts use different instances
        for instance in ["wd5", "wd3", "wd1"]:
            api_url = f"https://{tenant}.{instance}.myworkdayjobs.com/wday/cxs/en-US/{jobsite}/jobs"
            payload = {
                "appliedFacets": {},
                "limit": 50,
                "offset": 0,
                "searchText": "associate lawyer attorney counsel",
            }
            try:
                resp = self._session.post(
                    api_url,
                    json=payload,
                    headers={**JSON_HEADERS, "User-Agent": USER_AGENTS[0],
                             "Content-Type": "application/json"},
                    timeout=14,
                )
                if resp.status_code == 200:
                    return self._parse_workday(firm, resp.json())
            except Exception:
                pass
        logger.debug(f"[{firm['short']}] Workday: all instances failed")
        return []

    def _parse_workday(self, firm: dict, data: dict) -> list[dict]:
        jobs    = data.get("jobPostings", [])
        results = []
        for job in jobs:
            title    = job.get("title", "")
            location = job.get("locationsText", "") or job.get("primaryLocation", "")
            text     = f"{title} {location}"
            if not self._is_me_location(text):
                continue
            if not self._is_lawyer_role(title):
                continue
            loc      = self._extract_location(text)
            dept     = classifier.top_department(text) or {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}
            ext_id   = job.get("externalPath", "")
            job_url  = f"https://{firm.get('website', '').split('//')[1].split('/')[0]}{ext_id}" if ext_id else firm.get("careers_url", "")
            results.append(self._make_signal(
                firm_id=firm["id"], firm_name=firm["name"],
                signal_type="job_posting",
                title=f"[{firm['short']}] {title}",
                body=text[:900],
                url=job_url,
                department=dept["department"],
                department_score=dept["score"] * 2.0,
                matched_keywords=dept["matched_keywords"],
                location=loc or next(iter(firm.get("me_offices", {})), ""),
                seniority=self._extract_seniority(title),
                source="Workday ATS",
            ))
        logger.info(f"[{firm['short']}] Workday: {len(results)} ME role(s)")
        return results

    # ── Helpers ───────────────────────────────────────────────────────────

    def _fetch_json(self, url: str) -> Optional[dict]:
        try:
            resp = self._session.get(
                url,
                headers={**JSON_HEADERS, "User-Agent": USER_AGENTS[0]},
                timeout=14,
                allow_redirects=True,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.debug(f"ATS HTTP {resp.status_code}: {url}")
        except Exception as e:
            logger.debug(f"ATS fetch error: {e}")
        return None
