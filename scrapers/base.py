"""
Base scraper class.
Provides:
  - _get(url) with circuit-breaker, retry, backoff, user-agent rotation
  - Per-host failure tracking: hosts that fail 2+ times are skipped for the run
  - verify=False for hosts with known cert issues (kershawleonard)
  - Short per-request timeout + fast-fail for known slow hosts
  - _make_signal() standard signal dict builder
  - ME location + associate role filter helpers
"""

import logging
import random
import time
import hashlib
import urllib.parse
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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]

DEFAULT_HEADERS = {
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
    "DNT":             "1",
}

# Hosts with known SSL cert issues — use verify=False
SSL_NOCHECK_HOSTS = {
    "kershawleonard.net",
    "www.kershawleonard.net",
}

# Hosts confirmed dead/blocked on GitHub Actions — skip immediately
DEAD_HOSTS = {
    "www.guildhall.ae",
    "guildhall.ae",
    "www.thelawyermea.com",
    "thelawyermea.com",
    "www.legalbusinessworld.com",
    "legalbusinessworld.com",
}

# Hosts known to be very slow — use reduced timeout
SLOW_HOSTS = {
    "www.naukrigulf.com",
    "naukrigulf.com",
    "chambers.com",
    "www.chambers.com",
    "www.legal500.com",
    "legal500.com",
    "www.linkedin.com",
    "linkedin.com",
}

# Circuit breaker: tracks per-host failures within one process run
_HOST_FAILURES: dict = {}
CIRCUIT_BREAK_THRESHOLD = 2

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
    "operations", "facilities", "data entry", "legal tech",
    "knowledge management", "compliance officer", "in-house",
]


class BaseScraper:
    name: str = "BaseScraper"

    def __init__(self):
        self.logger      = logging.getLogger(self.name)
        self._session    = self._build_session()
        self._delay_min  = 1.0
        self._delay_max  = 3.0
        self._timeout    = 15
        self._slow_timeout = 8
        self._max_retries = 1

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(total=1, backoff_factor=1.0,
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
            self.logger.debug(f"Skipping dead host: {host}")
            return None

        failures = _HOST_FAILURES.get(host, 0)
        if failures >= CIRCUIT_BREAK_THRESHOLD:
            self.logger.debug(f"Circuit open for {host} ({failures} failures)")
            return None

        verify  = host not in SSL_NOCHECK_HOSTS
        if timeout is None:
            timeout = self._slow_timeout if host in SLOW_HOSTS else self._timeout

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
            elif resp.status_code == 404:
                return None
            else:
                self.logger.debug(f"HTTP {resp.status_code} for {url}")
                _HOST_FAILURES[host] = _HOST_FAILURES.get(host, 0) + 1
                return None
        except requests.Timeout:
            self.logger.debug(f"Timeout {host}")
            _HOST_FAILURES[host] = _HOST_FAILURES.get(host, 0) + 1
            return None
        except requests.exceptions.SSLError as e:
            self.logger.debug(f"SSL error {host}: {e}")
            _HOST_FAILURES[host] = _HOST_FAILURES.get(host, 0) + 1
            return None
        except requests.exceptions.ConnectionError as e:
            self.logger.debug(f"Connection error {host}: {e}")
            _HOST_FAILURES[host] = _HOST_FAILURES.get(host, 0) + 1
            return None
        except requests.RequestException as e:
            self.logger.debug(f"Request error {host}: {e}")
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
            "firm_id":          firm_id,
            "firm_name":        firm_name,
            "signal_type":      signal_type,
            "title":            title[:300],
            "body":             body[:1200],
            "url":              url,
            "department":       department,
            "department_score": round(float(department_score), 3),
            "matched_keywords": matched_keywords[:12],
            "location":         location,
            "seniority":        seniority,
            "source":           source,
            "recruiter":        recruiter,
            "published_date":   published_date or datetime.now(timezone.utc).isoformat(),
            "signal_hash":      hashlib.sha256(f"{firm_id}:{title}:{url}".encode()).hexdigest()[:16],
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
