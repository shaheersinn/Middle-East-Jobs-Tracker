"""
Website Change Detector
========================
Snapshots each firm's ME office pages and people/team pages,
flagging changes that indicate new hires, new practice launches
or associate-level additions.

Signal type: website_snapshot | lateral_hire
"""

import re
import hashlib
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from classifier.department import DepartmentClassifier

classifier = DepartmentClassifier()

# Paths to check on the ME office site
ME_PAGE_PATTERNS = [
    "/en/locations/middle-east/{city}",
    "/en/offices/{city}",
    "/offices/{city}",
    "/locations/{city}",
    "/en/people?office={city}",
    "/our-people?location={city}",
    "/attorneys?office={city}",
    "/lawyers?office=middle-east",
]


class WebsiteScraper(BaseScraper):
    name = "WebsiteScraper"

    def __init__(self, known_hashes: dict = None):
        super().__init__()
        self._known_hashes = known_hashes or {}

    def fetch(self, firm: dict) -> list[dict]:
        signals = []
        base = firm["website"].rstrip("/")

        for city, city_url in firm.get("me_offices", {}).items():
            # Office home page
            resp = self._get(city_url)
            if resp:
                sig = self._check_page(resp.text, city_url, firm, city)
                if sig:
                    signals.append(sig)

            # Team/people page variations
            for path_tmpl in [
                "/en/people",
                "/people",
                "/attorneys",
                "/lawyers",
                "/our-team",
            ]:
                team_url = f"{city_url.rstrip('/')}{path_tmpl}"
                if team_url == city_url:
                    continue
                resp2 = self._get(team_url)
                if resp2:
                    sig = self._check_page(resp2.text, team_url, firm, city)
                    if sig:
                        signals.append(sig)
                    break  # one team page per city is enough

        self.logger.info(f"[{firm['short']}] Website: {len(signals)} change(s)")
        return signals

    def _check_page(self, html: str, url: str, firm: dict, city: str) -> dict | None:
        soup       = BeautifulSoup(html, "html.parser")
        page_text  = soup.get_text(" ", strip=True)
        page_hash  = hashlib.sha256(page_text.encode()).hexdigest()[:20]

        old_hash   = self._known_hashes.get(url)
        self._known_hashes[url] = page_hash

        if old_hash is None or old_hash == page_hash:
            return None  # No change (or first run)

        # Page changed — look for lawyer-related content
        if not any(kw in page_text.lower() for kw in ["associate", "attorney", "lawyer", "counsel", "join"]):
            return None

        dept = classifier.top_department(page_text[:600])
        if not dept:
            dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}

        return self._make_signal(
            firm_id=firm["id"],
            firm_name=firm["name"],
            signal_type="website_snapshot",
            title=f"[{firm['short']} {city}] Website changed — lawyer content detected",
            body=page_text[:1000],
            url=url,
            department=dept["department"],
            department_score=dept["score"] * 2.5,
            matched_keywords=dept["matched_keywords"],
            location=city,
            source="Website Monitor",
        )
