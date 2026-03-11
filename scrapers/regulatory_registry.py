"""
Regulatory Registry Scraper (NEW)
===================================
Scrapes government/regulatory registries that give 3-6 month advance warning
of US firm ME expansion — before any job postings appear.

Sources:
  - DIFC Public Register (difc.ae) — new law firm registrations
  - ADGM Registration Authority (adgm.com) — new branch/SPV licenses
  - QFC Authority (qfc.qa) — Qatar Financial Centre firm licenses

Signal type: regulatory_filing (weight: 4.5 — highest signal value)
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from scrapers.base import BaseScraper
from classifier.department import DepartmentClassifier

classifier = DepartmentClassifier()

REGISTRIES = [
    {
        "id":   "difc",
        "name": "DIFC Public Register",
        "url":  "https://www.difc.ae/public-register/",
        "base": "https://www.difc.ae",
        "row_sel": re.compile(r"register|row|entry|listing|result|firm", re.I),
    },
    {
        "id":   "adgm",
        "name": "ADGM Registration Authority",
        "url":  "https://www.adgm.com/public-registers",
        "base": "https://www.adgm.com",
        "row_sel": re.compile(r"register|row|entry|listing|result|firm|company", re.I),
    },
    {
        "id":   "qfc",
        "name": "QFC Authority",
        "url":  "https://qfc.qa/en/regulations/regulated-entities",
        "base": "https://qfc.qa",
        "row_sel": re.compile(r"register|row|entity|listing|result|firm", re.I),
    },
]

LEGAL_INDICATORS = [
    "law", "legal", "solicitor", "attorney", "llp", "llc",
    "advocates", "barristers", "counsel",
]


class RegulatoryRegistryScraper(BaseScraper):
    name = "RegulatoryRegistryScraper"

    def fetch(self, firm: dict) -> list[dict]:
        signals = []
        firm_names = [firm["short"], firm["name"]] + firm.get("alt_names", [])

        for reg in REGISTRIES:
            resp = self._get(reg["url"])
            if not resp:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")

            # Search page text for firm name mentions
            page_text = soup.get_text(" ", strip=True)
            for name in firm_names:
                if name.lower() in page_text.lower():
                    # Find the specific element containing the match
                    rows = soup.find_all(["tr","div","li"],
                                         class_=reg["row_sel"])
                    for row in rows[:100]:
                        row_text = row.get_text(" ", strip=True)
                        if name.lower() not in row_text.lower():
                            continue
                        is_legal = any(kw in row_text.lower()
                                       for kw in LEGAL_INDICATORS)
                        if not is_legal:
                            continue
                        dept = classifier.top_department(row_text)
                        if not dept:
                            dept = {"department": "Corporate / M&A",
                                    "score": 1.0, "matched_keywords": []}

                        location_map = {
                            "difc": "Dubai", "adgm": "Abu Dhabi",
                            "qfc":  "Qatar",
                        }
                        signals.append(self._make_signal(
                            firm_id=firm["id"], firm_name=firm["name"],
                            signal_type="regulatory_filing",
                            title=f"[{reg['name']}] {name} — new registration",
                            body=row_text[:900],
                            url=reg["url"],
                            department=dept["department"],
                            department_score=dept["score"] * 4.5,
                            matched_keywords=dept["matched_keywords"],
                            location=location_map.get(reg["id"], "Middle East"),
                            source=reg["name"],
                        ))
                    break  # only match once per registry per firm name

        self.logger.info(f"[{firm['short']}] Regulatory: {len(signals)} filing(s)")
        return signals
