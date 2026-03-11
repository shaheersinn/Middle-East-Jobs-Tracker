"""
ALSP / Contract Platforms Scraper  (NEW v3)
============================================
Tracks Alternative Legal Service Providers placing interim lawyers at
US firms in the ME. ALSP postings predict permanent lateral hires 4-12
weeks ahead — firms trial associates via contract before offering full-time.

Sources:
  - LOD (Lawyers On Demand) — lodlaw.com — Dubai + Abu Dhabi
  - Axiom Law ME — axiomlaw.com — contract lawyers on major ME projects
  - Peerpoint (A&O Shearman) — peerpoint.legal — senior freelance pool
  - Flex Legal — flexlegal.co.uk — expanding to UAE/GCC
  - Hays Legal ME — hays.ae/jobs/legal — contract legal roles

Signal type: contract_role (weight: 2.2) — interim to permanent pipeline
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from scrapers.base import BaseScraper
from classifier.department import DepartmentClassifier

classifier = DepartmentClassifier()

ALSP_SOURCES = [
    {
        "id":   "lod",
        "name": "LOD (Lawyers On Demand)",
        "url":  "https://www.lodlaw.com/current-opportunities",
        "base": "https://www.lodlaw.com",
        "card": re.compile(r"job|opportunity|role|listing|card|vacancy", re.I),
    },
    {
        "id":   "axiom",
        "name": "Axiom Law ME",
        "url":  "https://www.axiomlaw.com/legal-talent",
        "base": "https://www.axiomlaw.com",
        "card": re.compile(r"job|role|opportunity|card|listing", re.I),
    },
    {
        "id":   "peerpoint",
        "name": "Peerpoint",
        "url":  "https://peerpoint.legal/opportunities",
        "base": "https://peerpoint.legal",
        "card": re.compile(r"job|role|opportunity|mandate|card", re.I),
    },
    {
        "id":   "flex_legal",
        "name": "Flex Legal",
        "url":  "https://flexlegal.co.uk/jobs/",
        "base": "https://flexlegal.co.uk",
        "card": re.compile(r"job|role|opportunity|card|listing|vacancy", re.I),
    },
]

ME_LOCS = [
    "dubai", "abu dhabi", "riyadh", "doha", "bahrain", "manama",
    "kuwait", "muscat", "difc", "adgm", "middle east", "gulf",
    "uae", "ksa", "saudi", "qatar", "oman",
]


class ALSPScraper(BaseScraper):
    name = "ALSPScraper"

    def fetch(self, firm: dict) -> list[dict]:
        signals  = []
        firm_names = [firm["short"], firm["name"]] + firm.get("alt_names", [])

        for src in ALSP_SOURCES:
            resp = self._get(src["url"])
            if not resp:
                continue
            soup  = BeautifulSoup(resp.text, "html.parser")
            cards = soup.find_all(["div","li","article"], class_=src["card"])[:30]

            for card in cards:
                text = card.get_text(" ", strip=True)
                if len(text) < 30:
                    continue
                is_me     = any(loc in text.lower() for loc in ME_LOCS)
                is_lawyer = self._is_lawyer_role(text)
                # Match firm name OR accept any ME legal role (ALSP feeds are sparse)
                is_firm   = any(n.lower() in text.lower() for n in firm_names)
                if not (is_me and is_lawyer):
                    continue
                # Only firm-specific signals unless it's LOD (which is always ME legal)
                if not is_firm and src["id"] not in ("lod", "axiom"):
                    continue

                title_tag = card.find(["h2","h3","h4","strong","a"])
                title     = title_tag.get_text(strip=True) if title_tag else text[:130]
                link      = card.find("a", href=True)
                url       = (link["href"] if link and link["href"].startswith("http")
                             else urljoin(src["base"], link["href"]) if link else src["url"])

                dept = classifier.top_department(f"{title} {text[:400]}")
                if not dept:
                    dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}

                signals.append(self._make_signal(
                    firm_id=firm["id"], firm_name=firm["name"],
                    signal_type="contract_role",
                    title=f"[{src['name']}] {title}",
                    body=text[:900], url=url,
                    department=dept["department"],
                    department_score=dept["score"] * 2.2,
                    matched_keywords=dept["matched_keywords"],
                    location=self._extract_location(text) or "Middle East",
                    seniority=self._extract_seniority(title),
                    source=src["name"],
                ))

        self.logger.info(f"[{firm['short']}] ALSP: {len(signals)} role(s)")
        return signals
