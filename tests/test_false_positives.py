"""
Tests for false-positive fixes in the scraper layer.

Covers two areas:
  1. BaseScraper._is_lawyer_role  — word-boundary NON_LAWYER_ROLES check so that
     "hr" at the end of a title (or in parentheses) is still excluded, without
     the old "hr " trailing-space bug that let "associate hr" slip through.

  2. RecruiterScraper._matches_firm — word-boundary matching for short acronyms
     (≤3 chars) so that e.g. "LW" does not match "always", "PH" does not match
     "phone", etc.
"""

import sys
import os

import pytest

# Ensure the project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scrapers.base import BaseScraper  # noqa: E402
from scrapers.recruiter import RecruiterScraper  # noqa: E402
from firms import FIRMS  # noqa: E402


# ---------------------------------------------------------------------------
# BaseScraper._is_lawyer_role
# ---------------------------------------------------------------------------

class TestIsLawyerRole:
    """_is_lawyer_role should return True only for genuine lawyer/associate roles."""

    # ── should be excluded (non-lawyer) ────────────────────────────────────

    def test_hr_at_end_of_title(self):
        """'associate hr' and variants were false positives due to the old 'hr ' check."""
        assert BaseScraper._is_lawyer_role("Associate HR Manager") is False

    def test_hr_in_parentheses(self):
        assert BaseScraper._is_lawyer_role("Senior Associate (HR)") is False

    def test_hr_after_dash(self):
        assert BaseScraper._is_lawyer_role("Associate - hr") is False

    def test_hr_prefix(self):
        assert BaseScraper._is_lawyer_role("hr associate") is False

    def test_paralegal(self):
        assert BaseScraper._is_lawyer_role("Paralegal Dubai") is False

    def test_marketing(self):
        assert BaseScraper._is_lawyer_role("Marketing Associate Dubai") is False

    def test_operations(self):
        assert BaseScraper._is_lawyer_role("Operations Associate Manager") is False

    def test_business_development(self):
        assert BaseScraper._is_lawyer_role("Business Development Associate") is False

    # ── should be included (genuine lawyer roles) ──────────────────────────

    def test_senior_associate_corporate(self):
        assert BaseScraper._is_lawyer_role("Senior Associate Corporate Dubai") is True

    def test_finance_associate(self):
        assert BaseScraper._is_lawyer_role("Finance Associate") is True

    def test_litigation_associate(self):
        assert BaseScraper._is_lawyer_role("Litigation Associate") is True

    def test_senior_counsel(self):
        assert BaseScraper._is_lawyer_role("Senior Counsel") is True

    def test_attorney(self):
        assert BaseScraper._is_lawyer_role("Attorney Dubai") is True

    def test_chronic_does_not_trigger_hr(self):
        """'chronic' contains 'hr' as a substring — should NOT suppress a lawyer role."""
        assert BaseScraper._is_lawyer_role("Chronically busy Senior Associate") is True


# ---------------------------------------------------------------------------
# RecruiterScraper._matches_firm  (word-boundary for short acronyms)
# ---------------------------------------------------------------------------

def _make_scraper():
    """Instantiate RecruiterScraper without running __init__ network code."""
    return RecruiterScraper.__new__(RecruiterScraper)


def _firm(firm_id):
    return next(f for f in FIRMS if f["id"] == firm_id)


class TestMatchesFirm:
    """Short acronyms should not match as substrings inside common English words."""

    def setup_method(self):
        self.scraper = _make_scraper()

    # ── false positives that must be suppressed ────────────────────────────

    def test_lw_does_not_match_always(self):
        """'LW' (Latham alt-name) must NOT match the substring 'lw' in 'always'."""
        raw = "we are always looking for senior associates in dubai"
        assert self.scraper._matches_firm(raw, _firm("latham")) is False

    def test_ph_does_not_match_phone(self):
        """'PH' (Paul Hastings alt-name) must NOT match 'ph' inside 'phone'."""
        raw = "please apply by phone to our dubai office for associate role"
        assert self.scraper._matches_firm(raw, _firm("paul_hastings")) is False

    def test_ph_does_not_match_physician(self):
        raw = "physician associate dubai legal team"
        assert self.scraper._matches_firm(raw, _firm("paul_hastings")) is False

    # ── legitimate matches that must still work ────────────────────────────

    def test_latham_full_name_matches(self):
        raw = "latham watkins is hiring a corporate associate in dubai"
        assert self.scraper._matches_firm(raw, _firm("latham")) is True

    def test_paul_hastings_full_name_matches(self):
        raw = "paul hastings is looking for a senior associate in dubai"
        assert self.scraper._matches_firm(raw, _firm("paul_hastings")) is True

    def test_morgan_lewis_full_name_matches(self):
        raw = "morgan lewis is seeking a finance associate for riyadh"
        assert self.scraper._matches_firm(raw, _firm("morgan_lewis")) is True

    def test_norton_rose_short_matches(self):
        """'Norton Rose' (>3 chars) should still match via substring."""
        raw = "norton rose fulbright hiring arbitration associate dubai"
        assert self.scraper._matches_firm(raw, _firm("norton_rose")) is True

    def test_short_acronym_as_standalone_word_matches(self):
        """A 3-char acronym that appears as a real standalone word should match."""
        raw = "nrf is looking for an associate in dubai"
        assert self.scraper._matches_firm(raw, _firm("norton_rose")) is True
