"""
Chambers & Legal 500 ME Scraper
=================================
Monitors Chambers Global (Middle East) and Legal 500 Middle East rankings
for US firms — detecting new band entries, rising rankings and
newly ranked associates/counsel in ME practices.

Sources:
  - chambers.com/guide/middle-east
  - legal500.com/geography/middle-east/

Signal type: ranking
"""

import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from scrapers.base import BaseScraper
from classifier.department import DepartmentClassifier

classifier = DepartmentClassifier()

CHAMBERS_ME_BASE  = "https://chambers.com"
LEGAL500_ME_BASE  = "https://www.legal500.com"

# ME practice areas recognised by Chambers / Legal 500
ME_PRACTICE_PATHS_CHAMBERS = [
    "/guide/middle-east/",
    "/guide/uae/",
    "/guide/qatar/",
    "/guide/saudi-arabia/",
    "/guide/bahrain/",
]

ME_PRACTICE_PATHS_L500 = [
    "/geography/middle-east/",
    "/geography/uae/",
    "/geography/qatar/",
    "/geography/saudi-arabia/",
]


class ChambersScraper(BaseScraper):
    name = "ChambersScraper"

    def fetch(self, firm: dict) -> list[dict]:
        signals = []
        signals.extend(self._scrape_chambers_me(firm))
        signals.extend(self._scrape_legal500_me(firm))
        return signals

    # ── Chambers Global ME ────────────────────────────────────────────────

    def _scrape_chambers_me(self, firm: dict) -> list[dict]:
        signals = []
        firm_names = [firm["short"], firm["name"]] + firm.get("alt_names", [])

        for path in ME_PRACTICE_PATHS_CHAMBERS:
            url  = CHAMBERS_ME_BASE + path
            resp = self._get(url)
            if not resp:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            # Look for firm mentions with band / ranking context
            items = soup.find_all(
                ["div", "article", "section", "li"],
                class_=re.compile(r"firm|ranking|band|result|item|card", re.I),
            )[:40]

            for item in items:
                text = item.get_text(" ", strip=True)
                if not any(n.lower() in text.lower() for n in firm_names):
                    continue

                title_tag = item.find(["h2", "h3", "h4", "a", "strong"])
                title = title_tag.get_text(strip=True) if title_tag else text[:130]

                band = self._extract_band(text)
                link = item.find("a", href=True)
                item_url = (
                    CHAMBERS_ME_BASE + link["href"] if link and not link["href"].startswith("http")
                    else link["href"] if link
                    else url
                )

                dept = classifier.top_department(f"{title} {text[:400]}")
                if not dept:
                    dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}

                label = f"Chambers ME{' ' + band if band else ''}"
                signals.append(self._make_signal(
                    firm_id=firm["id"],
                    firm_name=firm["name"],
                    signal_type="ranking",
                    title=f"[Chambers ME] {title}",
                    body=f"{label} — {text[:700]}",
                    url=item_url,
                    department=dept["department"],
                    department_score=dept["score"] * 3.0,
                    matched_keywords=dept["matched_keywords"],
                    location=self._extract_location(text) or "Middle East",
                    source="Chambers Global ME",
                ))

        self.logger.info(f"[{firm['short']}] Chambers ME: {len(signals)} ranking(s)")
        return signals

    # ── Legal 500 ME ──────────────────────────────────────────────────────

    def _scrape_legal500_me(self, firm: dict) -> list[dict]:
        signals = []
        firm_names = [firm["short"], firm["name"]] + firm.get("alt_names", [])

        for path in ME_PRACTICE_PATHS_L500:
            url  = LEGAL500_ME_BASE + path
            resp = self._get(url)
            if not resp:
                continue

            soup  = BeautifulSoup(resp.text, "html.parser")
            items = soup.find_all(
                ["div", "article", "li"],
                class_=re.compile(r"firm|ranking|tier|result|card|item", re.I),
            )[:40]

            for item in items:
                text = item.get_text(" ", strip=True)
                if not any(n.lower() in text.lower() for n in firm_names):
                    continue

                title_tag = item.find(["h2", "h3", "h4", "a"])
                title = title_tag.get_text(strip=True) if title_tag else text[:130]

                tier = self._extract_tier(text)
                link = item.find("a", href=True)
                item_url = (
                    LEGAL500_ME_BASE + link["href"] if link and not link["href"].startswith("http")
                    else link["href"] if link
                    else url
                )

                dept = classifier.top_department(f"{title} {text[:400]}")
                if not dept:
                    dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}

                label = f"Legal 500 ME{' ' + tier if tier else ''}"
                signals.append(self._make_signal(
                    firm_id=firm["id"],
                    firm_name=firm["name"],
                    signal_type="ranking",
                    title=f"[Legal 500 ME] {title}",
                    body=f"{label} — {text[:700]}",
                    url=item_url,
                    department=dept["department"],
                    department_score=dept["score"] * 3.0,
                    matched_keywords=dept["matched_keywords"],
                    location=self._extract_location(text) or "Middle East",
                    source="Legal 500 ME",
                ))

        self.logger.info(f"[{firm['short']}] Legal 500 ME: {len(signals)} ranking(s)")
        return signals

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _extract_band(text: str) -> str:
        m = re.search(r"band\s*([1-6])", text, re.I)
        return f"Band {m.group(1)}" if m else ""

    @staticmethod
    def _extract_tier(text: str) -> str:
        m = re.search(r"tier\s*([1-5])", text, re.I)
        return f"Tier {m.group(1)}" if m else ""
