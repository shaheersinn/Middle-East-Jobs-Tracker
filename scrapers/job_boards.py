"""
Middle East Job Boards Scraper
================================
Scrapes major ME-focused job boards for US law firm associate postings.

Boards:
  - Bayt.com       — largest Arabic/ME job board
  - NaukriGulf     — Gulf-focused board (legal section)
  - GulfTalent     — premium ME professional board
  - Indeed UAE/ME  — regional Indeed portals
  - LinkedIn Jobs  — public ME legal job search
  - Glassdoor ME   — salary + job listings

Signal type: job_posting
"""

import re
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

from scrapers.base import BaseScraper
from classifier.department import DepartmentClassifier

classifier = DepartmentClassifier()


class JobBoardsScraper(BaseScraper):
    name = "JobBoardsScraper"

    def fetch(self, firm: dict) -> list[dict]:
        signals = []
        signals.extend(self._scrape_bayt(firm))
        signals.extend(self._scrape_naukrigulf(firm))
        signals.extend(self._scrape_gulftalent(firm))
        signals.extend(self._scrape_indeed_uae(firm))
        signals.extend(self._scrape_linkedin_me(firm))
        return signals

    # ── Bayt.com ──────────────────────────────────────────────────────────

    def _scrape_bayt(self, firm: dict) -> list[dict]:
        signals = []
        queries = [
            f"{firm['short']} lawyer",
            f"{firm['short']} associate",
            f"{firm['short']} legal counsel",
        ]
        for q in queries[:2]:
            url = f"https://www.bayt.com/en/uae/jobs/{quote_plus(q.lower().replace(' ','-'))}-jobs/"
            resp = self._get(url)
            if not resp:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            for card in soup.find_all(
                ["li", "div"],
                attrs={"data-js-job": True},
            )[:15]:
                text = card.get_text(" ", strip=True)

                employer_tag = card.find(class_=re.compile(r"company|employer|organization", re.I))
                employer = employer_tag.get_text(strip=True) if employer_tag else ""
                if not self._matches_firm_name(employer + " " + text, firm):
                    continue

                title_tag = card.find(class_=re.compile(r"jb-title|job-title|title|position", re.I))
                title = title_tag.get_text(strip=True) if title_tag else text[:130]
                if not self._is_lawyer_role(title):
                    continue

                location = self._extract_location(text) or "UAE"

                link = card.find("a", href=True)
                job_url = ("https://www.bayt.com" + link["href"]) if link else url

                dept = classifier.top_department(f"{title} {text[:400]}")
                if not dept:
                    dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}

                signals.append(self._make_signal(
                    firm_id=firm["id"],
                    firm_name=firm["name"],
                    signal_type="job_posting",
                    title=f"[Bayt] {title}",
                    body=text[:800],
                    url=job_url,
                    department=dept["department"],
                    department_score=dept["score"] * self._seniority_w(title),
                    matched_keywords=dept["matched_keywords"],
                    location=location,
                    seniority=self._extract_seniority(title),
                    source="Bayt.com",
                ))
        self.logger.info(f"[{firm['short']}] Bayt: {len(signals)} job(s)")
        return signals

    # ── NaukriGulf ────────────────────────────────────────────────────────

    def _scrape_naukrigulf(self, firm: dict) -> list[dict]:
        signals = []
        query = quote_plus(f"{firm['short']} lawyer associate")
        url   = f"https://www.naukrigulf.com/jobs-in-uae?q={query}&l=Dubai&l=Abu+Dhabi"
        resp  = self._get(url)
        if not resp:
            return signals

        soup = BeautifulSoup(resp.text, "html.parser")
        for card in soup.find_all(
            ["div", "li"],
            class_=re.compile(r"job-listing|job-item|srp-tuple|result|job-card", re.I),
        )[:15]:
            text = card.get_text(" ", strip=True)
            if not self._is_lawyer_role(text):
                continue
            if not self._is_me_location(text) and not self._matches_firm_name(text, firm):
                continue

            title_tag = card.find(class_=re.compile(r"desig|title|job-title|role", re.I))
            title = title_tag.get_text(strip=True) if title_tag else text[:130]

            if not self._is_lawyer_role(title):
                continue

            link    = card.find("a", href=True)
            job_url = ("https://www.naukrigulf.com" + link["href"]) if link else url
            location = self._extract_location(text) or "Gulf"

            dept = classifier.top_department(f"{title} {text[:400]}")
            if not dept:
                dept = {"department": "Banking & Finance", "score": 1.0, "matched_keywords": []}

            signals.append(self._make_signal(
                firm_id=firm["id"],
                firm_name=firm["name"],
                signal_type="job_posting",
                title=f"[NaukriGulf] {title}",
                body=text[:800],
                url=job_url,
                department=dept["department"],
                department_score=dept["score"] * self._seniority_w(title),
                matched_keywords=dept["matched_keywords"],
                location=location,
                seniority=self._extract_seniority(title),
                source="NaukriGulf",
            ))

        self.logger.info(f"[{firm['short']}] NaukriGulf: {len(signals)} job(s)")
        return signals

    # ── GulfTalent ────────────────────────────────────────────────────────

    def _scrape_gulftalent(self, firm: dict) -> list[dict]:
        signals = []
        query   = quote_plus(f"lawyer {firm['short']}")
        url     = f"https://www.gulftalent.com/jobs?q={query}&country=ae"
        resp    = self._get(url)
        if not resp:
            return signals

        soup = BeautifulSoup(resp.text, "html.parser")
        for card in soup.find_all(
            ["div", "article"],
            class_=re.compile(r"job|listing|result|card|item", re.I),
        )[:15]:
            text = card.get_text(" ", strip=True)
            if not self._is_lawyer_role(text):
                continue
            if not self._matches_firm_name(text, firm):
                continue

            title_tag = card.find(["h2", "h3", "h4", "a"])
            title = title_tag.get_text(strip=True) if title_tag else text[:130]
            if not self._is_lawyer_role(title):
                continue

            link    = card.find("a", href=True)
            job_url = link["href"] if link and link["href"].startswith("http") else url
            location = self._extract_location(text) or "Gulf"

            dept = classifier.top_department(f"{title} {text[:400]}")
            if not dept:
                dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}

            signals.append(self._make_signal(
                firm_id=firm["id"],
                firm_name=firm["name"],
                signal_type="job_posting",
                title=f"[GulfTalent] {title}",
                body=text[:800],
                url=job_url,
                department=dept["department"],
                department_score=dept["score"] * self._seniority_w(title),
                matched_keywords=dept["matched_keywords"],
                location=location,
                seniority=self._extract_seniority(title),
                source="GulfTalent",
            ))

        self.logger.info(f"[{firm['short']}] GulfTalent: {len(signals)} job(s)")
        return signals

    # ── Indeed UAE ────────────────────────────────────────────────────────

    def _scrape_indeed_uae(self, firm: dict) -> list[dict]:
        signals = []
        queries = [
            f"{firm['short']} associate",
            f"{firm['short']} lawyer Dubai",
        ]
        for q in queries[:2]:
            url = (
                "https://ae.indeed.com/jobs"
                f"?q={quote_plus(q)}&l=Dubai&sort=date&radius=50"
            )
            resp = self._get(url)
            if not resp:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            for card in soup.find_all(
                "div",
                class_=re.compile(r"job_seen_beacon|tapItem|result|jobCard", re.I),
            )[:12]:
                text = card.get_text(" ", strip=True)

                company_tag = card.find(class_=re.compile(r"company|employer|companyName", re.I))
                company = company_tag.get_text(strip=True) if company_tag else ""
                if not self._matches_firm_name(company + " " + text, firm):
                    continue

                title_tag = card.find(["h2", "h3"], class_=re.compile(r"title|jobTitle", re.I))
                title = title_tag.get_text(strip=True) if title_tag else ""
                if not title or not self._is_lawyer_role(title):
                    continue

                location = self._extract_location(text) or "Dubai"

                dept = classifier.top_department(f"{title} {text[:400]}")
                if not dept:
                    dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}

                signals.append(self._make_signal(
                    firm_id=firm["id"],
                    firm_name=firm["name"],
                    signal_type="job_posting",
                    title=f"[Indeed UAE] {title}",
                    body=text[:800],
                    url=url,
                    department=dept["department"],
                    department_score=dept["score"] * self._seniority_w(title),
                    matched_keywords=dept["matched_keywords"],
                    location=location,
                    seniority=self._extract_seniority(title),
                    source="Indeed UAE",
                ))

        self.logger.info(f"[{firm['short']}] Indeed UAE: {len(signals)} job(s)")
        return signals

    # ── LinkedIn ME Jobs ──────────────────────────────────────────────────

    def _scrape_linkedin_me(self, firm: dict) -> list[dict]:
        signals = []
        slug    = firm.get("linkedin_slug", "")
        if not slug:
            return signals

        # LinkedIn public job search (no auth needed)
        keywords = quote_plus(f"{firm['short']} associate lawyer")
        url = (
            "https://www.linkedin.com/jobs/search/"
            f"?keywords={keywords}&location=United+Arab+Emirates"
            f"&f_TPR=r604800"  # last 7 days
        )
        resp = self._get(url, extra_headers={"Accept": "text/html"})
        if not resp:
            return signals

        soup = BeautifulSoup(resp.text, "html.parser")
        for card in soup.find_all(
            class_=re.compile(r"job-search-card|base-card|result-card", re.I),
        )[:15]:
            text = card.get_text(" ", strip=True)

            company_tag = card.find(
                class_=re.compile(r"company|employer|base-search-card__subtitle", re.I)
            )
            company = company_tag.get_text(strip=True) if company_tag else ""
            if not self._matches_firm_name(company + " " + text, firm):
                continue

            title_tag = card.find(
                class_=re.compile(r"title|job-search-card__title", re.I)
            )
            title = title_tag.get_text(strip=True) if title_tag else ""
            if not title or not self._is_lawyer_role(title):
                continue

            location_tag = card.find(
                class_=re.compile(r"location|job-search-card__location", re.I)
            )
            location = location_tag.get_text(strip=True) if location_tag else ""
            if location and not self._is_me_location(location):
                continue
            if not location:
                location = "UAE"

            dept = classifier.top_department(title)
            if not dept:
                dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}

            signals.append(self._make_signal(
                firm_id=firm["id"],
                firm_name=firm["name"],
                signal_type="job_posting",
                title=f"[LinkedIn] {title}",
                body=text[:600],
                url=url,
                department=dept["department"],
                department_score=dept["score"] * self._seniority_w(title),
                matched_keywords=dept["matched_keywords"],
                location=location,
                seniority=self._extract_seniority(title),
                source="LinkedIn",
            ))

        self.logger.info(f"[{firm['short']}] LinkedIn ME: {len(signals)} job(s)")
        return signals

    # ── Helpers ───────────────────────────────────────────────────────────

    def _matches_firm_name(self, text: str, firm: dict) -> bool:
        t = text.lower()
        candidates = [firm["short"], firm["name"]] + firm.get("alt_names", [])
        return any(c.lower() in t for c in candidates)

    def _seniority_w(self, title: str) -> float:
        t = title.lower()
        if "senior" in t or "counsel" in t:
            return 2.5
        if "associate" in t or "attorney" in t or "lawyer" in t:
            return 2.0
        if "trainee" in t:
            return 1.5
        return 1.8
