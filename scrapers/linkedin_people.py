"""
LinkedIn People / Profile Scraper (new)
=========================================
Uses Google's indexed LinkedIn pages to find attorneys who recently
joined US firms' ME offices. No auth required — uses Google search
cache and LinkedIn public profiles.

Signal type: lateral_hire
"""

import re
from scrapers.base import BaseScraper
from classifier.department import DepartmentClassifier

classifier = DepartmentClassifier()

RECENTLY_JOINED_SIGNALS = [
    "joined", "newly appointed", "new associate", "new counsel",
    "recently joined", "started at", "pleased to announce",
]


class LinkedInPeopleScraper(BaseScraper):
    name = "LinkedInPeopleScraper"

    def fetch(self, firm: dict) -> list[dict]:
        signals = []

        cities = list(firm.get("me_offices", {}).keys())[:3]
        if not cities:
            return signals

        for city in cities:
            signals.extend(self._search_google_linkedin(firm, city))

        self.logger.info(f"[{firm['short']}] LinkedIn People: {len(signals)} signal(s)")
        return signals

    def _search_google_linkedin(self, firm: dict, city: str) -> list[dict]:
        """Search Google for cached LinkedIn profiles of new hires at firm in city."""
        signals = []
        query = (f'site:linkedin.com/in "{firm["short"]}" "{city}" '
                 '"associate" OR "counsel" OR "attorney"')
        encoded = query.replace(" ", "+").replace('"', '%22')
        url = f"https://www.google.com/search?q={encoded}&num=10&tbs=qdr:m"

        resp = self._get(url, extra_headers={
            "Accept": "text/html",
            "Referer": "https://www.google.com/",
        })
        if not resp:
            return signals

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")

        for result in soup.find_all("div", class_=re.compile(r"g|result|tF2Cxc", re.I))[:8]:
            text = result.get_text(" ", strip=True)
            if len(text) < 30:
                continue
            if not any(n.lower() in text.lower()
                       for n in [firm["short"], firm["name"]] + firm.get("alt_names", [])):
                continue
            if not self._is_lawyer_role(text):
                continue

            title_tag = result.find(["h3", "h2", "a"])
            title = title_tag.get_text(strip=True) if title_tag else text[:130]

            link = result.find("a", href=True)
            profile_url = link["href"] if link else ""
            if profile_url.startswith("/url?q="):
                from urllib.parse import parse_qs, urlparse
                qs = parse_qs(urlparse(profile_url).query)
                profile_url = qs.get("q", [""])[0]

            dept = classifier.top_department(f"{title} {text[:300]}")
            if not dept:
                dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}

            signals.append(self._make_signal(
                firm_id=firm["id"],
                firm_name=firm["name"],
                signal_type="lateral_hire",
                title=f"[LinkedIn] {title}",
                body=text[:800],
                url=profile_url or url,
                department=dept["department"],
                department_score=dept["score"] * 3.0,
                matched_keywords=dept["matched_keywords"],
                location=city,
                seniority=self._extract_seniority(title),
                source="LinkedIn (Google-indexed)",
            ))

        return signals
