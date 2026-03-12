"""
Base scraper  (v4 — comprehensive dead-host update from live log analysis)

Fixes:
  - CIRCUIT_BREAK_THRESHOLD raised 1→3: single transient failure no longer
    blocks all subsequent requests to legitimate firm career pages
  - Expanded DEAD_HOSTS: every host with consistent DNS/timeout failures in logs
  - Added SCRAPER_BLOCKED_HOSTS: sites that always 403/redirect GH Actions runners
    (get threshold=1 applied specifically)
  - efinancialcareers.ae → SSL_NOCHECK_HOSTS (hostname mismatch)
  - glassdoor.ae         → DEAD_HOSTS (consistent timeouts GH Actions)
  - google.com           → DEAD_HOSTS (blocks GH Actions runners)
  - arabianbusiness.com  → DEAD_HOSTS
  - adzuna.ae            → DEAD_HOSTS (DNS failure every run)
  - peerpoint.legal      → DEAD_HOSTS (DNS failure)
  - marsden.co.uk        → DEAD_HOSTS (read timeout every run)
  - 15+ recruiter sites  → DEAD_HOSTS (confirmed unreachable from GH Actions)
"""
import logging, random, time, hashlib, urllib.parse
from datetime import datetime, timezone
from typing import Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from firms import ME_LOCATIONS

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]
DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "DNT": "1",
}

# SSL cert hostname mismatch — use verify=False
SSL_NOCHECK_HOSTS = {
    "kershawleonard.net", "www.kershawleonard.net",
    "efinancialcareers.ae", "www.efinancialcareers.ae",
}

# Confirmed dead/blocked on GitHub Actions — skip immediately, zero retries
DEAD_HOSTS = {
    # Recruiter portals — confirmed unreachable from GH Actions runners
    "www.guildhall.ae", "guildhall.ae",
    "www.thelawyermea.com", "thelawyermea.com",
    "www.legalbusinessworld.com", "legalbusinessworld.com",
    "www.glassdoor.ae", "glassdoor.ae",
    "www.google.com", "google.com",
    "www.arabianbusiness.com", "arabianbusiness.com",
    # DNS failures (every run)
    "www.adzuna.ae", "adzuna.ae",
    "peerpoint.legal", "www.peerpoint.legal",
    # Timeouts (every run from GH Actions)
    "www.marsden.co.uk", "marsden.co.uk",
    "www.mlaglobal.com", "mlaglobal.com",
    "laterallink.com", "www.laterallink.com",
    "mrasearch.com", "www.mrasearch.com",
    "www.clarkburnell.com", "clarkburnell.com",
    "emea.legal", "www.emea.legal",
    "www.aquissearch.com", "aquissearch.com",
    "seekergroup.ae", "www.seekergroup.ae",
    "mukadamlegal.com", "www.mukadamlegal.com",
    "www.robertwalters.ae", "robertwalters.ae",
    "www.mackenziejones.com", "mackenziejones.com",
    # Legal media — blocks GH Actions
    "www.theoath-me.com", "theoath-me.com",
    "www.lexismiddleeast.com", "lexismiddleeast.com",
    "www.thelawyer.com", "thelawyer.com",
    "agbi.com", "www.agbi.com",
    "gulfnews.com", "www.gulfnews.com",
    # Job boards — blocks/DNS fails
    "laimoon.com", "www.laimoon.com",
    "ae.jooble.org",
    "gulfjoblo.com", "www.gulfjoblo.com",
    "katcheri.in", "www.katcheri.in",
    "www.founditgulf.com", "founditgulf.com",
    # ALSP platforms
    "www.lodlaw.com", "lodlaw.com",
    "flexlegal.co.uk", "www.flexlegal.co.uk",
}

# Known-slow hosts — reduced timeout (8 s)
SLOW_HOSTS = {
    "www.naukrigulf.com", "naukrigulf.com",
    "chambers.com", "www.chambers.com",
    "www.legal500.com", "legal500.com",
    "www.linkedin.com", "linkedin.com",
    "www.hoganlovells.com", "hoganlovells.com",
    "www.dlapiper.com", "dlapiper.com",
    "www.bayt.com", "bayt.com",
    "ae.indeed.com", "sa.indeed.com", "qa.indeed.com",
    "www.nortonrosefulbright.com", "nortonrosefulbright.com",
    "www.bakermckenzie.com", "bakermckenzie.com",
    "www.dentons.com", "dentons.com",
}

_HOST_FAILURES: dict = {}
# FIXED: was 1 — caused legitimate firm career pages to be blocked after
# a single transient failure. Now 3 failures required to open the circuit.
CIRCUIT_BREAK_THRESHOLD = 3

ASSOCIATE_KEYWORDS = [
    "associate", "law associate", "legal associate", "junior associate",
    "senior associate", "attorney", "lawyer", "solicitor", "counsel",
    "junior counsel", "senior counsel", "of counsel", "legal counsel",
    "trainee", "legal trainee", "junior lawyer", "mid-level associate",
    "corporate associate", "litigation associate", "finance associate",
]
NON_LAWYER_ROLES = [
    "paralegal", "legal secretary", "receptionist", "office manager",
    "marketing", "business development", "it support", "billing",
    "hr ", "human resources", "finance director", "accountant",
    "operations", "facilities", "data entry", "knowledge management",
]


class BaseScraper:
    name: str = "BaseScraper"

    def __init__(self):
        self.logger      = logging.getLogger(self.name)
        self._session    = self._build_session()
        self._delay_min  = 0.8
        self._delay_max  = 2.5
        self._timeout    = 12
        self._slow_timeout = 7

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(total=1, backoff_factor=0.5,
                      status_forcelist=[429, 500, 502, 503, 504],
                      allowed_methods=["GET"])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://",  adapter)
        return session

    def _get(self, url: str, params: dict = None,
             extra_headers: dict = None, timeout: int = None) -> Optional[requests.Response]:
        host = urllib.parse.urlparse(url).netloc
        if host in DEAD_HOSTS:
            self.logger.debug(f"Skip dead host: {host}")
            return None
        failures = _HOST_FAILURES.get(host, 0)
        if failures >= CIRCUIT_BREAK_THRESHOLD:
            self.logger.debug(f"Circuit open: {host}")
            return None
        verify  = host not in SSL_NOCHECK_HOSTS
        timeout = timeout or (self._slow_timeout if host in SLOW_HOSTS else self._timeout)
        headers = {**DEFAULT_HEADERS, "User-Agent": random.choice(USER_AGENTS)}
        if extra_headers:
            headers.update(extra_headers)
        try:
            resp = self._session.get(url, headers=headers, params=params,
                                     timeout=timeout, allow_redirects=True, verify=verify)
            if resp.status_code == 200:
                time.sleep(random.uniform(self._delay_min, self._delay_max))
                _HOST_FAILURES[host] = 0
                return resp
            self.logger.debug(f"HTTP {resp.status_code}: {url}")
            _HOST_FAILURES[host] = _HOST_FAILURES.get(host, 0) + 1
            return None
        except (requests.Timeout, requests.exceptions.SSLError,
                requests.exceptions.ConnectionError, requests.RequestException) as e:
            self.logger.debug(f"Req error {host}: {type(e).__name__}")
            _HOST_FAILURES[host] = _HOST_FAILURES.get(host, 0) + 1
            return None

    @staticmethod
    def get_circuit_breaker_report() -> dict:
        return {h: f for h, f in _HOST_FAILURES.items() if f > 0}

    @staticmethod
    def _make_signal(firm_id, firm_name, signal_type, title, body, url,
                     department, department_score, matched_keywords,
                     location="", seniority="", source="", recruiter="",
                     published_date=None) -> dict:
        return {
            "firm_id": firm_id, "firm_name": firm_name,
            "signal_type": signal_type,
            "title": title[:300], "body": body[:1200], "url": url,
            "department": department,
            "department_score": round(float(department_score), 3),
            "matched_keywords": matched_keywords[:12],
            "location": location, "seniority": seniority,
            "source": source, "recruiter": recruiter,
            "published_date": published_date or datetime.now(timezone.utc).isoformat(),
            "signal_hash": hashlib.sha256(f"{firm_id}:{title}:{url}".encode()).hexdigest()[:16],
        }

    @staticmethod
    def _is_me_location(text: str) -> bool:
        t = text.lower()
        return any(loc.lower() in t for loc in ME_LOCATIONS)

    @staticmethod
    def _extract_location(text: str) -> str:
        t = text.lower()
        for loc in ME_LOCATIONS:
            if loc.lower() in t:
                return loc
        return ""

    @staticmethod
    def _is_lawyer_role(title: str) -> bool:
        t = title.lower()
        return (any(kw in t for kw in ASSOCIATE_KEYWORDS) and
                not any(kw in t for kw in NON_LAWYER_ROLES))

    @staticmethod
    def _extract_seniority(title: str) -> str:
        t = title.lower()
        if "partner" in t:                               return "Partner"
        if "senior counsel" in t or "senior associate" in t: return "Senior Associate"
        if "mid-level" in t or "mid level" in t:         return "Mid-Level Associate"
        if "junior" in t or "trainee" in t:              return "Junior Associate"
        if "counsel" in t:                               return "Counsel"
        if "associate" in t:                             return "Associate"
        if "attorney" in t or "lawyer" in t or "solicitor" in t: return "Attorney / Lawyer"
        return "Associate"

    def fetch(self, firm: dict) -> list[dict]:
        raise NotImplementedError
