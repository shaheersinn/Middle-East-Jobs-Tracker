#!/usr/bin/env python3
"""
normalize.py — Normalization helpers for the ME Law Firm Expansion Tracker.

Provides canonical mapping of common shorthand to controlled vocabulary.
Can be used as a library or run standalone to show normalization suggestions.

Usage:
    from scripts.normalize import normalize_practice_area, normalize_country

    normalize_practice_area("IP")         # -> "Intellectual Property"
    normalize_practice_area("M&A")        # -> "Corporate & M&A"
    normalize_country("UK")               # -> "GB"
    normalize_country("United States")    # -> "US"
"""

import re
import sys

# ── Practice area normalization map ───────────────────────────────────────────
# Keys are lowercase stripped versions of common shorthand or raw text.
# Values are canonical practice area names from the controlled vocabulary.

_PRACTICE_AREA_MAP: dict[str, str] = {
    # Shorthand -> canonical
    "ip": "Intellectual Property",
    "privacy": "Data Privacy & Protection",
    "data privacy": "Data Privacy & Protection",
    "data protection": "Data Privacy & Protection",
    "gdpr": "Data Privacy & Protection",
    "privacy & cybersecurity": "Technology & Cybersecurity",
    "cyber": "Technology & Cybersecurity",
    "cybersecurity": "Technology & Cybersecurity",
    "tech": "Technology & Cybersecurity",
    "technology": "Technology & Cybersecurity",
    "fintech": "Technology & Cybersecurity",
    "labor": "Employment & Labor",
    "labour": "Employment & Labor",
    "employment": "Employment & Labor",
    "m&a": "Corporate & M&A",
    "ma": "Corporate & M&A",
    "mergers and acquisitions": "Corporate & M&A",
    "corporate": "Corporate & M&A",
    "competition": "Antitrust & Competition",
    "antitrust": "Antitrust & Competition",
    "pe": "Private Equity",
    "private equity": "Private Equity",
    "funds": "Private Equity",
    "fund formation": "Private Equity",
    "banking": "Banking & Finance",
    "finance": "Banking & Finance",
    "capital markets": "Capital Markets",
    "ecm": "Capital Markets",
    "dcm": "Capital Markets",
    "real estate": "Real Estate",
    "property": "Real Estate",
    "litigation": "Litigation & Dispute Resolution",
    "disputes": "Litigation & Dispute Resolution",
    "arbitration": "Arbitration & Mediation",
    "mediation": "Arbitration & Mediation",
    "adr": "Arbitration & Mediation",
    "restructuring": "Restructuring & Insolvency",
    "insolvency": "Restructuring & Insolvency",
    "bankruptcy": "Restructuring & Insolvency",
    "energy": "Energy & Natural Resources",
    "oil and gas": "Energy & Natural Resources",
    "natural resources": "Energy & Natural Resources",
    "infrastructure": "Infrastructure & Projects",
    "projects": "Infrastructure & Projects",
    "project finance": "Infrastructure & Projects",
    "regulatory": "Regulatory & Compliance",
    "compliance": "Regulatory & Compliance",
    "tax": "Tax",
    "immigration": "Immigration",
    "white collar": "White Collar & Investigations",
    "investigations": "White Collar & Investigations",
    "healthcare": "Healthcare & Life Sciences",
    "life sciences": "Healthcare & Life Sciences",
    "environmental": "Environmental",
    "environment": "Environmental",
    "family": "Family & Private Client",
    "private client": "Family & Private Client",
    "public law": "Public Law & Government Affairs",
    "government affairs": "Public Law & Government Affairs",
    "trade": "Trade & Customs",
    "customs": "Trade & Customs",
    "trade & customs": "Trade & Customs",
}

# ── Country normalization map ─────────────────────────────────────────────────
_COUNTRY_MAP: dict[str, str] = {
    # Non-ISO -> ISO 3166-1 alpha-2
    "uk": "GB",
    "u.k.": "GB",
    "united kingdom": "GB",
    "england": "GB",
    "britain": "GB",
    "great britain": "GB",
    "usa": "US",
    "u.s.a.": "US",
    "u.s.": "US",
    "united states": "US",
    "united states of america": "US",
    "germany": "DE",
    "deutschland": "DE",
    "france": "FR",
    "uae": "AE",
    "u.a.e.": "AE",
    "united arab emirates": "AE",
    "emirates": "AE",
    "saudi arabia": "SA",
    "ksa": "SA",
    "kingdom of saudi arabia": "SA",
    "qatar": "QA",
    "bahrain": "BH",
    "kingdom of bahrain": "BH",
    "kuwait": "KW",
    "oman": "OM",
    "sultanate of oman": "OM",
    "jordan": "JO",
    "egypt": "EG",
    "turkey": "TR",
    "türkiye": "TR",
    "iraq": "IQ",
    "lebanon": "LB",
    "morocco": "MA",
    "libya": "LY",
    "yemen": "YE",
    "syria": "SY",
    "canada": "CA",
    "australia": "AU",
    "singapore": "SG",
    "hong kong": "HK",
    "japan": "JP",
    "china": "CN",
}


def normalize_practice_area(raw: str) -> str | None:
    """
    Normalize a raw practice area string to the canonical vocabulary value.

    Returns the canonical string if a mapping is found, or None if the raw
    value is ambiguous and requires manual review.

    If the raw value already matches a canonical value exactly, it is returned
    unchanged.
    """
    from scripts.validate import VALID_PRACTICE_AREAS  # avoid circular at module level

    if raw in VALID_PRACTICE_AREAS:
        return raw

    key = raw.strip().lower()
    key = re.sub(r'\s+', ' ', key)

    if key in _PRACTICE_AREA_MAP:
        return _PRACTICE_AREA_MAP[key]

    # Partial match: check if any canonical value contains the key or vice versa
    matches = [v for k, v in _PRACTICE_AREA_MAP.items() if key in k or k in key]
    if len(matches) == 1:
        return matches[0]

    return None  # ambiguous — flag for manual review


def normalize_country(raw: str) -> str | None:
    """
    Normalize a raw country string to ISO 3166-1 alpha-2.

    Returns the ISO code if found, or None if ambiguous.
    If the input is already a valid 2-letter uppercase code, it is returned.
    """
    import re as _re

    stripped = raw.strip()
    if _re.match(r'^[A-Z]{2}$', stripped):
        return stripped  # Already ISO alpha-2

    key = stripped.lower()
    return _COUNTRY_MAP.get(key, None)


def normalize_text(text: str) -> str:
    """Trim whitespace and collapse multiple internal spaces."""
    return re.sub(r'\s+', ' ', text.strip())


if __name__ == "__main__":
    # Quick self-test / demo
    examples = [
        ("practice_area", "IP"),
        ("practice_area", "Privacy"),
        ("practice_area", "Privacy & Cybersecurity"),
        ("practice_area", "Labor"),
        ("practice_area", "M&A"),
        ("practice_area", "Competition"),
        ("practice_area", "Corporate & M&A"),
        ("country", "UK"),
        ("country", "USA"),
        ("country", "United States"),
        ("country", "Germany"),
        ("country", "AE"),
    ]
    print("Normalization demo:")
    for kind, raw in examples:
        if kind == "practice_area":
            result = normalize_practice_area(raw)
        else:
            result = normalize_country(raw)
        status = "OK" if result else "NEEDS MANUAL REVIEW"
        print(f"  {kind:<15} {raw!r:<35} -> {result!r}  [{status}]")
    sys.exit(0)
