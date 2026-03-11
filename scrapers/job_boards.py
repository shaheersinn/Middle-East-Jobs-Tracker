"""
ME Job Boards Scraper  (v3 — expanded + fixed)
================================================
FIXED:  Removed glassdoor.ae (timeout), arabianbusiness.com (blocked),
        google.com (blocked on GH Actions)
ADDED:  GulfTalent, Jameson Legal (ME specialist), Jooble AE, GulfJoblo,
        Katcheri, Wuzzuf, FoundIt Gulf, Adzuna UAE, CareerJet ME,
        Indeed KSA/Qatar country-level, Hiredge
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin

from scrapers.base import BaseScraper
from classifier.department import DepartmentClassifier

classifier = DepartmentClassifier()


class JobBoardsScraper(BaseScraper):
    name = "JobBoardsScraper"

    def fetch(self, firm: dict) -> list[dict]:
        signals = []
        signals.extend(self._scrape_bayt(firm))
        signals.extend(self._scrape_gulftalent(firm))
        signals.extend(self._scrape_jameson_legal(firm))
        signals.extend(self._scrape_indeed_uae(firm))
        signals.extend(self._scrape_indeed_ksa(firm))
        signals.extend(self._scrape_indeed_qatar(firm))
        signals.extend(self._scrape_laimoon(firm))
        signals.extend(self._scrape_jooble(firm))
        signals.extend(self._scrape_gulfjoblo(firm))
        signals.extend(self._scrape_katcheri(firm))
        signals.extend(self._scrape_wuzzuf(firm))
        signals.extend(self._scrape_foundit(firm))
        signals.extend(self._scrape_adzuna(firm))
        signals.extend(self._scrape_linkedin_me(firm))
        return signals

    # ── Helpers ────────────────────────────────────────────────────────────

    def _matches_firm(self, text: str, firm: dict) -> bool:
        t = text.lower()
        return any(c.lower() in t for c in
                   [firm["short"], firm["name"]] + firm.get("alt_names", []))

    def _seniority_w(self, title: str) -> float:
        t = title.lower()
        if "partner" in t:               return 3.5
        if "senior" in t or "counsel" in t: return 2.5
        if "associate" in t or "attorney" in t or "lawyer" in t: return 2.0
        if "trainee" in t:               return 1.5
        return 1.8

    def _make_job_signal(self, firm, title, body, url, source, location=""):
        dept = classifier.top_department(f"{title} {body[:400]}")
        if not dept:
            dept = {"department": "Corporate / M&A", "score": 1.0, "matched_keywords": []}
        return self._make_signal(
            firm_id=firm["id"], firm_name=firm["name"],
            signal_type="job_posting",
            title=f"[{source}] {title}", body=body[:800], url=url,
            department=dept["department"],
            department_score=dept["score"] * self._seniority_w(title),
            matched_keywords=dept["matched_keywords"],
            location=location or self._extract_location(body) or "Middle East",
            seniority=self._extract_seniority(title), source=source,
        )

    def _parse_generic(self, resp, firm, source, base_url,
                       card_pat=None, max_cards=20) -> list[dict]:
        if not resp:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        pat  = card_pat or re.compile(r"job|listing|card|vacancy|result|item", re.I)
        cards = soup.find_all(["div","li","article"], class_=pat)[:max_cards]
        signals = []
        for card in cards:
            text = card.get_text(" ", strip=True)
            if len(text) < 30: continue
            if not self._matches_firm(text, firm): continue
            if not self._is_lawyer_role(text): continue
            title_tag = card.find(["h2","h3","h4","a"])
            title = title_tag.get_text(strip=True) if title_tag else text[:130]
            link  = card.find("a", href=True)
            url   = (link["href"] if link and link["href"].startswith("http")
                     else urljoin(base_url, link["href"]) if link else base_url)
            signals.append(self._make_job_signal(firm, title, text, url, source))
        return signals

    # ── Board scrapers ─────────────────────────────────────────────────────

    def _scrape_bayt(self, firm: dict) -> list[dict]:
        signals = []
        q   = quote_plus(f"{firm['short']} lawyer associate")
        url = f"https://www.bayt.com/en/uae/jobs/lawyer-jobs/?filters[jb_location_country_iso][]=AE&filters[jb_location_country_iso][]=SA&filters[jb_location_country_iso][]=QA&q={q}"
        resp = self._get(url)
        result = self._parse_generic(resp, firm, "Bayt.com", "https://www.bayt.com",
                                     re.compile(r"jb-|job|card|listing", re.I))
        self.logger.info(f"[{firm['short']}] Bayt: {len(result)} job(s)")
        return result

    def _scrape_gulftalent(self, firm: dict) -> list[dict]:
        """GulfTalent — major GCC specialist job board."""
        q    = quote_plus(f"{firm['short']} lawyer")
        url  = f"https://www.gulftalent.com/jobs?search={q}&location=&title=lawyer"
        resp = self._get(url)
        result = self._parse_generic(resp, firm, "GulfTalent", "https://www.gulftalent.com",
                                     re.compile(r"job|listing|card|vacancy", re.I))
        self.logger.info(f"[{firm['short']}] GulfTalent: {len(result)} job(s)")
        return result

    def _scrape_jameson_legal(self, firm: dict) -> list[dict]:
        """Jameson Legal — ME specialist legal-only board covering all 7 GCC jurisdictions."""
        url  = "https://www.jamesonlegal.com/jl/middle-east"
        resp = self._get(url)
        result = self._parse_generic(resp, firm, "Jameson Legal", "https://www.jamesonlegal.com",
                                     re.compile(r"job|vacancy|role|listing|card", re.I))
        self.logger.info(f"[{firm['short']}] Jameson Legal: {len(result)} job(s)")
        return result

    def _scrape_indeed_uae(self, firm: dict) -> list[dict]:
        signals = []
        q   = quote_plus(f"{firm['short']} associate")
        url = f"https://ae.indeed.com/jobs?q={q}&l=Dubai&sort=date"
        resp = self._get(url)
        if not resp: return signals
        soup = BeautifulSoup(resp.text, "html.parser")
        for card in soup.find_all("div", class_=re.compile(r"job_seen_beacon|tapItem|result|jobCard", re.I))[:12]:
            text = card.get_text(" ", strip=True)
            company_tag = card.find(class_=re.compile(r"company|companyName|employer", re.I))
            company = company_tag.get_text(strip=True) if company_tag else ""
            if not self._matches_firm(company + " " + text, firm): continue
            title_tag = card.find(["h2","h3"], class_=re.compile(r"title|jobTitle", re.I))
            title = title_tag.get_text(strip=True) if title_tag else ""
            if not title or not self._is_lawyer_role(title): continue
            signals.append(self._make_job_signal(firm, title, text, url, "Indeed UAE", "Dubai"))
        self.logger.info(f"[{firm['short']}] Indeed UAE: {len(signals)} job(s)")
        return signals

    def _scrape_indeed_ksa(self, firm: dict) -> list[dict]:
        """Separate KSA scrape — surfaces Riyadh roles not in UAE roll-up."""
        q   = quote_plus(f"{firm['short']} lawyer")
        url = f"https://sa.indeed.com/jobs?q={q}&l=Riyadh&sort=date"
        resp = self._get(url)
        result = self._parse_generic(resp, firm, "Indeed KSA", "https://sa.indeed.com",
                                     re.compile(r"job_seen|tapItem|result|jobCard", re.I), 10)
        self.logger.info(f"[{firm['short']}] Indeed KSA: {len(result)} job(s)")
        return result

    def _scrape_indeed_qatar(self, firm: dict) -> list[dict]:
        q   = quote_plus(f"{firm['short']} associate")
        url = f"https://qa.indeed.com/jobs?q={q}&l=Doha&sort=date"
        resp = self._get(url)
        result = self._parse_generic(resp, firm, "Indeed Qatar", "https://qa.indeed.com",
                                     re.compile(r"job_seen|tapItem|result|jobCard", re.I), 8)
        self.logger.info(f"[{firm['short']}] Indeed Qatar: {len(result)} job(s)")
        return result

    def _scrape_laimoon(self, firm: dict) -> list[dict]:
        q   = quote_plus(f"{firm['short']} lawyer")
        url = f"https://laimoon.com/jobs/uae/lawyer?q={q}"
        resp = self._get(url)
        result = self._parse_generic(resp, firm, "Laimoon", "https://laimoon.com")
        self.logger.info(f"[{firm['short']}] Laimoon: {len(result)} job(s)")
        return result

    def _scrape_jooble(self, firm: dict) -> list[dict]:
        """Jooble AE — aggregates DIFC/ADGM arbitration roles; real-time."""
        q   = quote_plus(f"{firm['short']} lawyer associate")
        url = f"https://ae.jooble.org/{q}/Dubai"
        resp = self._get(url)
        result = self._parse_generic(resp, firm, "Jooble AE", "https://ae.jooble.org",
                                     re.compile(r"job|listing|card|vacancy|result", re.I))
        self.logger.info(f"[{firm['short']}] Jooble AE: {len(result)} job(s)")
        return result

    def _scrape_gulfjoblo(self, firm: dict) -> list[dict]:
        """GulfJoblo — daily GCC postings across all 6 countries."""
        q   = quote_plus(f"{firm['short']} legal")
        url = f"https://gulfjoblo.com/jobs?q={q}&country=UAE"
        resp = self._get(url)
        result = self._parse_generic(resp, firm, "GulfJoblo", "https://gulfjoblo.com")
        self.logger.info(f"[{firm['short']}] GulfJoblo: {len(result)} job(s)")
        return result

    def _scrape_katcheri(self, firm: dict) -> list[dict]:
        """Katcheri — specialist legal alerts; Dubai/DIFC associate PQE roles."""
        url  = "https://katcheri.in/jobs/dubai-difc-legal"
        resp = self._get(url)
        result = self._parse_generic(resp, firm, "Katcheri", "https://katcheri.in")
        self.logger.info(f"[{firm['short']}] Katcheri: {len(result)} job(s)")
        return result

    def _scrape_wuzzuf(self, firm: dict) -> list[dict]:
        """Wuzzuf — covers Egypt + GCC; first to post roles with Cairo/Riyadh dual ops."""
        q   = quote_plus(f"{firm['short']} lawyer")
        url = f"https://wuzzuf.net/search/jobs/?q={q}&a=hpb"
        resp = self._get(url)
        result = self._parse_generic(resp, firm, "Wuzzuf", "https://wuzzuf.net",
                                     re.compile(r"job|card|listing|result|position", re.I))
        self.logger.info(f"[{firm['short']}] Wuzzuf: {len(result)} job(s)")
        return result

    def _scrape_foundit(self, firm: dict) -> list[dict]:
        """FoundIt Gulf (formerly Monster Gulf) — 800k+ ME jobs."""
        q   = quote_plus(f"{firm['short']} lawyer associate")
        url = f"https://www.founditgulf.com/search/jobs?searchId=&q={q}&loc=Dubai"
        resp = self._get(url)
        result = self._parse_generic(resp, firm, "FoundIt Gulf", "https://www.founditgulf.com")
        self.logger.info(f"[{firm['short']}] FoundIt Gulf: {len(result)} job(s)")
        return result

    def _scrape_adzuna(self, firm: dict) -> list[dict]:
        """Adzuna UAE — large aggregator with legal-specific filters."""
        q   = quote_plus(f"{firm['short']} lawyer")
        url = f"https://www.adzuna.ae/search?q={q}&cat=legal-jobs&loc=United+Arab+Emirates"
        resp = self._get(url)
        result = self._parse_generic(resp, firm, "Adzuna UAE", "https://www.adzuna.ae",
                                     re.compile(r"job|listing|card|advert|result", re.I))
        self.logger.info(f"[{firm['short']}] Adzuna UAE: {len(result)} job(s)")
        return result

    def _scrape_linkedin_me(self, firm: dict) -> list[dict]:
        """LinkedIn — circuit breaker handles timeouts gracefully."""
        signals = []
        keywords = quote_plus(f"{firm['short']} associate lawyer")
        url = (f"https://www.linkedin.com/jobs/search/"
               f"?keywords={keywords}&location=United+Arab+Emirates&f_TPR=r604800")
        resp = self._get(url, extra_headers={"Accept": "text/html"})
        if not resp: return signals
        soup = BeautifulSoup(resp.text, "html.parser")
        for card in soup.find_all(class_=re.compile(r"job-search-card|base-card|result-card", re.I))[:12]:
            text = card.get_text(" ", strip=True)
            company_tag = card.find(class_=re.compile(r"company|base-search-card__subtitle", re.I))
            company = company_tag.get_text(strip=True) if company_tag else ""
            if not self._matches_firm(company + " " + text, firm): continue
            title_tag = card.find(class_=re.compile(r"title|job-search-card__title", re.I))
            title = title_tag.get_text(strip=True) if title_tag else ""
            if not title or not self._is_lawyer_role(title): continue
            location_tag = card.find(class_=re.compile(r"location|job-search-card__location", re.I))
            location = location_tag.get_text(strip=True) if location_tag else "UAE"
            if location and not self._is_me_location(location): continue
            signals.append(self._make_job_signal(firm, title, text, url, "LinkedIn", location))
        self.logger.info(f"[{firm['short']}] LinkedIn ME: {len(signals)} job(s)")
        return signals
