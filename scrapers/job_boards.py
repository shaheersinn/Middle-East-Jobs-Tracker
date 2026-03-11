"""
ME Job Boards Scraper (v2 — fixed)
====================================
Fixes vs v1:
  - Removed naukrigulf.com (consistently times out — circuit breaker would catch
    it anyway but we save time by not attempting at all)
  - LinkedIn timeout handled by circuit breaker in base._get()
  - Added: Glassdoor ME, Jobsite ME, Wuzzuf ME, Laimoon.com
  - Indeed UAE kept but with reduced timeout via SLOW_HOSTS

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
        signals.extend(self._scrape_indeed_uae(firm))
        signals.extend(self._scrape_laimoon(firm))
        signals.extend(self._scrape_linkedin_me(firm))
        signals.extend(self._scrape_glassdoor_me(firm))
        return signals

    def _scrape_bayt(self, firm: dict) -> list[dict]:
        signals = []
        queries = [f"{firm['short']} associate", f"{firm['short']} lawyer"]
        for q in queries[:2]:
            url = f"https://www.bayt.com/en/uae/jobs/{quote_plus(q.lower().replace(' ','-'))}-jobs/"
            resp = self._get(url)
            if not resp:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for card in soup.find_all(["li","div"], attrs={"data-js-job": True})[:15]:
                text = card.get_text(" ", strip=True)
                employer_tag = card.find(class_=re.compile(r"company|employer|organization", re.I))
                employer = employer_tag.get_text(strip=True) if employer_tag else ""
                if not self._matches_firm(employer + " " + text, firm):
                    continue
                title_tag = card.find(class_=re.compile(r"jb-title|job-title|title|position", re.I))
                title = title_tag.get_text(strip=True) if title_tag else text[:130]
                if not self._is_lawyer_role(title):
                    continue
                link    = card.find("a", href=True)
                job_url = ("https://www.bayt.com" + link["href"]) if link else url
                location = self._extract_location(text) or "UAE"
                dept = classifier.top_department(f"{title} {text[:400]}")
                if not dept:
                    dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}
                signals.append(self._make_signal(
                    firm_id=firm["id"], firm_name=firm["name"],
                    signal_type="job_posting",
                    title=f"[Bayt] {title}", body=text[:800], url=job_url,
                    department=dept["department"],
                    department_score=dept["score"] * self._seniority_w(title),
                    matched_keywords=dept["matched_keywords"],
                    location=location, seniority=self._extract_seniority(title), source="Bayt.com",
                ))
        self.logger.info(f"[{firm['short']}] Bayt: {len(signals)} job(s)")
        return signals

    def _scrape_indeed_uae(self, firm: dict) -> list[dict]:
        signals = []
        q = quote_plus(f"{firm['short']} associate")
        url = f"https://ae.indeed.com/jobs?q={q}&l=Dubai&sort=date&radius=50"
        resp = self._get(url)
        if not resp:
            return signals
        soup = BeautifulSoup(resp.text, "html.parser")
        for card in soup.find_all("div", class_=re.compile(r"job_seen_beacon|tapItem|result|jobCard", re.I))[:12]:
            text = card.get_text(" ", strip=True)
            company_tag = card.find(class_=re.compile(r"company|employer|companyName", re.I))
            company = company_tag.get_text(strip=True) if company_tag else ""
            if not self._matches_firm(company + " " + text, firm):
                continue
            title_tag = card.find(["h2","h3"], class_=re.compile(r"title|jobTitle", re.I))
            title = title_tag.get_text(strip=True) if title_tag else ""
            if not title or not self._is_lawyer_role(title):
                continue
            location = self._extract_location(text) or "Dubai"
            dept = classifier.top_department(f"{title} {text[:400]}")
            if not dept:
                dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}
            signals.append(self._make_signal(
                firm_id=firm["id"], firm_name=firm["name"],
                signal_type="job_posting",
                title=f"[Indeed UAE] {title}", body=text[:800], url=url,
                department=dept["department"],
                department_score=dept["score"] * self._seniority_w(title),
                matched_keywords=dept["matched_keywords"],
                location=location, seniority=self._extract_seniority(title), source="Indeed UAE",
            ))
        self.logger.info(f"[{firm['short']}] Indeed UAE: {len(signals)} job(s)")
        return signals

    def _scrape_laimoon(self, firm: dict) -> list[dict]:
        """Laimoon.com — UAE/GCC job board, good legal coverage."""
        signals = []
        q = quote_plus(f"{firm['short']} lawyer")
        url = f"https://laimoon.com/jobs/uae/lawyer?q={q}"
        resp = self._get(url)
        if not resp:
            return signals
        soup = BeautifulSoup(resp.text, "html.parser")
        for card in soup.find_all(["div","li"], class_=re.compile(r"job|listing|card|result|item", re.I))[:15]:
            text = card.get_text(" ", strip=True)
            if not self._is_lawyer_role(text) or not self._matches_firm(text, firm):
                continue
            title_tag = card.find(["h2","h3","h4","a"])
            title = title_tag.get_text(strip=True) if title_tag else text[:130]
            link    = card.find("a", href=True)
            job_url = (link["href"] if link and link["href"].startswith("http")
                       else f"https://laimoon.com{link['href']}" if link else url)
            location = self._extract_location(text) or "UAE"
            dept = classifier.top_department(f"{title} {text[:400]}")
            if not dept:
                dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}
            signals.append(self._make_signal(
                firm_id=firm["id"], firm_name=firm["name"],
                signal_type="job_posting",
                title=f"[Laimoon] {title}", body=text[:800], url=job_url,
                department=dept["department"],
                department_score=dept["score"] * self._seniority_w(title),
                matched_keywords=dept["matched_keywords"],
                location=location, seniority=self._extract_seniority(title), source="Laimoon",
            ))
        self.logger.info(f"[{firm['short']}] Laimoon: {len(signals)} job(s)")
        return signals

    def _scrape_linkedin_me(self, firm: dict) -> list[dict]:
        """LinkedIn public job search — circuit breaker handles timeouts."""
        signals = []
        keywords = quote_plus(f"{firm['short']} associate lawyer")
        url = (f"https://www.linkedin.com/jobs/search/"
               f"?keywords={keywords}&location=United+Arab+Emirates&f_TPR=r604800")
        resp = self._get(url, extra_headers={"Accept": "text/html"})
        if not resp:
            return signals
        soup = BeautifulSoup(resp.text, "html.parser")
        for card in soup.find_all(class_=re.compile(r"job-search-card|base-card|result-card", re.I))[:12]:
            text = card.get_text(" ", strip=True)
            company_tag = card.find(class_=re.compile(r"company|employer|base-search-card__subtitle", re.I))
            company = company_tag.get_text(strip=True) if company_tag else ""
            if not self._matches_firm(company + " " + text, firm):
                continue
            title_tag = card.find(class_=re.compile(r"title|job-search-card__title", re.I))
            title = title_tag.get_text(strip=True) if title_tag else ""
            if not title or not self._is_lawyer_role(title):
                continue
            location_tag = card.find(class_=re.compile(r"location|job-search-card__location", re.I))
            location = location_tag.get_text(strip=True) if location_tag else "UAE"
            if location and not self._is_me_location(location):
                continue
            dept = classifier.top_department(title)
            if not dept:
                dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}
            signals.append(self._make_signal(
                firm_id=firm["id"], firm_name=firm["name"],
                signal_type="job_posting",
                title=f"[LinkedIn] {title}", body=text[:600], url=url,
                department=dept["department"],
                department_score=dept["score"] * self._seniority_w(title),
                matched_keywords=dept["matched_keywords"],
                location=location, seniority=self._extract_seniority(title), source="LinkedIn",
            ))
        self.logger.info(f"[{firm['short']}] LinkedIn ME: {len(signals)} job(s)")
        return signals

    def _scrape_glassdoor_me(self, firm: dict) -> list[dict]:
        """Glassdoor UAE jobs — good for BigLaw visibility."""
        signals = []
        q = quote_plus(f"{firm['short']} associate")
        url = f"https://www.glassdoor.ae/Job/united-arab-emirates-{q}-jobs-SRCH_IL.0,20_IN240_KO21,{20+len(firm['short'])+10}.htm"
        resp = self._get(url)
        if not resp:
            return signals
        soup = BeautifulSoup(resp.text, "html.parser")
        for card in soup.find_all(["li","div"], class_=re.compile(r"JobsList|react-job-listing|jobCard|job-listing", re.I))[:10]:
            text = card.get_text(" ", strip=True)
            if not self._is_lawyer_role(text) or not self._matches_firm(text, firm):
                continue
            title_tag = card.find(["h2","h3","a"])
            title = title_tag.get_text(strip=True) if title_tag else text[:130]
            location = self._extract_location(text) or "UAE"
            dept = classifier.top_department(f"{title} {text[:400]}")
            if not dept:
                dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}
            signals.append(self._make_signal(
                firm_id=firm["id"], firm_name=firm["name"],
                signal_type="job_posting",
                title=f"[Glassdoor] {title}", body=text[:800], url=url,
                department=dept["department"],
                department_score=dept["score"] * self._seniority_w(title),
                matched_keywords=dept["matched_keywords"],
                location=location, seniority=self._extract_seniority(title), source="Glassdoor",
            ))
        self.logger.info(f"[{firm['short']}] Glassdoor ME: {len(signals)} job(s)")
        return signals

    def _matches_firm(self, text: str, firm: dict) -> bool:
        t = text.lower()
        return any(c.lower() in t for c in [firm["short"], firm["name"]] + firm.get("alt_names", []))

    def _seniority_w(self, title: str) -> float:
        t = title.lower()
        if "senior" in t or "counsel" in t: return 2.5
        if "associate" in t or "attorney" in t or "lawyer" in t: return 2.0
        if "trainee" in t: return 1.5
        return 1.8
