#!/usr/bin/env python3
"""
validate.py — Expansion record validator for the ME Law Firm Expansion Tracker.

Usage:
    python scripts/validate.py                     # validate all data/firms/**/*.yaml
    python scripts/validate.py path/to/record.yaml  # validate a single file
    python scripts/validate.py --strict             # exit non-zero on warnings too

Exit codes:
    0 — all records pass (errors=0)
    1 — one or more records have errors
    2 — argument or setup error

Checks performed:
    Errors  — required fields, types, enum values, country format, date format,
               URL format, record_id pattern, duplicate record_ids, empty
               practice_areas, self-referencing related_records.
    Warnings — announced_date older than 2 years while still draft,
               effective_date before announced_date,
               unverified + published combination,
               future announced_date,
               unusually long notes (>500 chars),
               missing city when region is provided,
               high-confidence record with weak source type.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone, date
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

try:
    import jsonschema
    from jsonschema import validate as jsonschema_validate, ValidationError
    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
SCHEMA_PATH = REPO_ROOT / "data" / "schema" / "expansion.schema.json"
DATA_DIR = REPO_ROOT / "data" / "firms"

# ── Controlled vocabularies (mirrors the schema enums) ────────────────────────
VALID_EXPANSION_TYPES = {
    "new_office", "new_practice_group", "merger", "lateral_hire_group",
    "office_relocation", "office_expansion", "strategic_alliance",
    "new_jurisdiction_license", "department_restructure",
}

VALID_PRACTICE_AREAS = {
    "Corporate & M&A", "Private Equity", "Capital Markets",
    "Banking & Finance", "Real Estate", "Litigation & Dispute Resolution",
    "Arbitration & Mediation", "Intellectual Property",
    "Technology & Cybersecurity", "Data Privacy & Protection",
    "Employment & Labor", "Tax", "Regulatory & Compliance",
    "Antitrust & Competition", "White Collar & Investigations",
    "Healthcare & Life Sciences", "Energy & Natural Resources",
    "Environmental", "Infrastructure & Projects",
    "Restructuring & Insolvency", "Immigration", "Family & Private Client",
    "Public Law & Government Affairs", "Trade & Customs",
}

VALID_SOURCE_TYPES = {
    "firm_press_release", "legal_directory", "legal_news", "court_filing",
    "job_posting", "industry_report", "social_media", "other",
}

VALID_CONFIDENCE = {"confirmed", "high", "medium", "low", "unverified"}

VALID_STATUS = {"draft", "under_review", "verified", "published", "archived"}

RECORD_ID_RE = re.compile(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$')
COUNTRY_RE = re.compile(r'^[A-Z]{2}$')
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
DATETIME_RE = re.compile(
    r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$'
)
URL_RE = re.compile(r'^https?://')
SEMVER_RE = re.compile(r'^\d+\.\d+\.\d+$')

WEAK_SOURCE_TYPES = {"job_posting", "social_media", "other"}
HIGH_CONFIDENCE_LEVELS = {"confirmed", "high"}
NOTES_WARN_THRESHOLD = 500
OLD_DRAFT_YEARS = 2


# ── Result container ──────────────────────────────────────────────────────────

class ValidationResult:
    def __init__(self, path: str):
        self.path = path
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    def error(self, msg: str):
        self.errors.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)

    def __str__(self) -> str:
        lines = [f"  FILE: {self.path}"]
        for e in self.errors:
            lines.append(f"    ERROR   {e}")
        for w in self.warnings:
            lines.append(f"    WARNING {w}")
        if not self.errors and not self.warnings:
            lines.append("    OK")
        return "\n".join(lines)


# ── Validators ────────────────────────────────────────────────────────────────

def _parse_date(val: str) -> date | None:
    try:
        return date.fromisoformat(val)
    except (ValueError, TypeError):
        return None


def validate_record(record: dict, path: str, seen_ids: set) -> ValidationResult:
    """Validate a single expansion record dict. Returns a ValidationResult."""
    r = ValidationResult(path)

    # ── Required fields ───────────────────────────────────────────────────
    required = [
        "record_id", "firm_name", "expansion_type", "practice_areas",
        "country", "announced_date", "source_url", "source_type",
        "confidence", "status", "created_at", "last_modified",
        "schema_version",
    ]
    for field in required:
        if field not in record or record[field] is None:
            r.error(f"Missing required field: '{field}'")

    if r.errors:
        return r  # Can't continue safely without required fields

    # ── record_id ─────────────────────────────────────────────────────────
    rid = record["record_id"]
    if not isinstance(rid, str) or not RECORD_ID_RE.match(rid):
        r.error(
            f"Invalid record_id '{rid}': must be lowercase letters, digits, "
            "and hyphens only, and must not start or end with a hyphen."
        )
    elif rid in seen_ids:
        r.error(f"Duplicate record_id '{rid}'")
    else:
        seen_ids.add(rid)

    # ── firm_name ─────────────────────────────────────────────────────────
    if not isinstance(record["firm_name"], str) or not record["firm_name"].strip():
        r.error("firm_name must be a non-empty string")

    # ── expansion_type ────────────────────────────────────────────────────
    if record["expansion_type"] not in VALID_EXPANSION_TYPES:
        r.error(
            f"Invalid expansion_type '{record['expansion_type']}'. "
            f"Allowed: {sorted(VALID_EXPANSION_TYPES)}"
        )

    # ── practice_areas ────────────────────────────────────────────────────
    pas = record["practice_areas"]
    if not isinstance(pas, list) or len(pas) == 0:
        r.error("practice_areas must be a non-empty list")
    else:
        for pa in pas:
            if pa not in VALID_PRACTICE_AREAS:
                r.error(
                    f"Unknown practice_area '{pa}'. "
                    f"Use a value from the controlled vocabulary."
                )

    # ── country ───────────────────────────────────────────────────────────
    country = record["country"]
    if not isinstance(country, str) or not COUNTRY_RE.match(country):
        r.error(
            f"Invalid country '{country}': must be ISO 3166-1 alpha-2 "
            "(two uppercase letters, e.g. AE, GB, US)"
        )

    # ── announced_date ────────────────────────────────────────────────────
    ann_str = record["announced_date"]
    if not isinstance(ann_str, str) or not DATE_RE.match(ann_str):
        r.error(f"Invalid announced_date '{ann_str}': must be YYYY-MM-DD")
        ann_date = None
    else:
        ann_date = _parse_date(ann_str)
        if ann_date is None:
            r.error(f"announced_date '{ann_str}' is not a valid calendar date")
        else:
            today = date.today()
            if ann_date > today:
                r.warn(f"announced_date '{ann_str}' is in the future")
            # Draft record older than 2 years
            if (record["status"] == "draft" and
                    (today - ann_date).days > OLD_DRAFT_YEARS * 365):
                r.warn(
                    f"Record is still 'draft' but announced_date is over "
                    f"{OLD_DRAFT_YEARS} years ago ({ann_str})"
                )

    # ── effective_date (optional) ─────────────────────────────────────────
    eff_str = record.get("effective_date")
    if eff_str is not None:
        if not isinstance(eff_str, str) or not DATE_RE.match(eff_str):
            r.error(f"Invalid effective_date '{eff_str}': must be YYYY-MM-DD")
        else:
            eff_date = _parse_date(eff_str)
            if eff_date is None:
                r.error(f"effective_date '{eff_str}' is not a valid calendar date")
            elif ann_date is not None and eff_date < ann_date:
                r.warn(
                    f"effective_date '{eff_str}' is earlier than "
                    f"announced_date '{ann_str}'"
                )

    # ── source_url ────────────────────────────────────────────────────────
    url = record["source_url"]
    if not isinstance(url, str) or not URL_RE.match(url):
        r.error(
            f"Invalid source_url '{url}': must start with http:// or https://"
        )

    # ── source_type ───────────────────────────────────────────────────────
    if record["source_type"] not in VALID_SOURCE_TYPES:
        r.error(
            f"Invalid source_type '{record['source_type']}'. "
            f"Allowed: {sorted(VALID_SOURCE_TYPES)}"
        )

    # ── confidence ────────────────────────────────────────────────────────
    confidence = record["confidence"]
    if confidence not in VALID_CONFIDENCE:
        r.error(
            f"Invalid confidence '{confidence}'. "
            f"Allowed: {sorted(VALID_CONFIDENCE)}"
        )

    # ── status ────────────────────────────────────────────────────────────
    status = record["status"]
    if status not in VALID_STATUS:
        r.error(
            f"Invalid status '{status}'. "
            f"Allowed: {sorted(VALID_STATUS)}"
        )

    # ── Cross-field: unverified + published ───────────────────────────────
    if confidence == "unverified" and status == "published":
        r.warn(
            "Record is 'published' but confidence is 'unverified'. "
            "This requires explicit policy approval."
        )

    # ── headcount (optional) ──────────────────────────────────────────────
    hc = record.get("headcount")
    if hc is not None:
        if not isinstance(hc, int) or hc < 1:
            r.error(f"headcount must be a positive integer, got '{hc}'")

    # ── related_records (optional) ────────────────────────────────────────
    rr = record.get("related_records")
    if rr is not None:
        if not isinstance(rr, list):
            r.error("related_records must be a list")
        else:
            for rel in rr:
                if rel == rid:
                    r.error(
                        f"related_records contains self-reference: '{rel}'"
                    )
                elif not isinstance(rel, str) or not RECORD_ID_RE.match(rel):
                    r.error(
                        f"related_records entry '{rel}' is not a valid "
                        "record_id slug"
                    )

    # ── created_at ────────────────────────────────────────────────────────
    if not isinstance(record["created_at"], str) or not DATETIME_RE.match(
        record["created_at"]
    ):
        r.error(
            f"Invalid created_at '{record['created_at']}': "
            "must be ISO 8601 UTC datetime (YYYY-MM-DDTHH:MM:SSZ)"
        )

    # ── last_modified ─────────────────────────────────────────────────────
    if not isinstance(record["last_modified"], str) or not DATETIME_RE.match(
        record["last_modified"]
    ):
        r.error(
            f"Invalid last_modified '{record['last_modified']}': "
            "must be ISO 8601 UTC datetime (YYYY-MM-DDTHH:MM:SSZ)"
        )

    # ── schema_version ────────────────────────────────────────────────────
    if not isinstance(record["schema_version"], str) or not SEMVER_RE.match(
        record["schema_version"]
    ):
        r.error(
            f"Invalid schema_version '{record['schema_version']}': "
            "must follow semantic versioning (e.g. 1.0.0)"
        )

    # ── Warnings: notes length ────────────────────────────────────────────
    notes = record.get("notes")
    if notes and len(notes) > NOTES_WARN_THRESHOLD:
        r.warn(
            f"notes is {len(notes)} characters; preferred maximum is "
            f"{NOTES_WARN_THRESHOLD}"
        )

    # ── Warnings: missing city with region ────────────────────────────────
    if record.get("region") and not record.get("city"):
        r.warn(
            "region is set but city is absent; add city if it is known "
            "from the source"
        )

    # ── Warnings: high confidence + weak source ───────────────────────────
    if (confidence in HIGH_CONFIDENCE_LEVELS and
            record.get("source_type") in WEAK_SOURCE_TYPES):
        r.warn(
            f"Confidence is '{confidence}' but source_type is "
            f"'{record['source_type']}' (a weak source). "
            "Verify confidence assignment."
        )

    # ── JSON Schema structural check (if jsonschema available) ────────────
    if _HAS_JSONSCHEMA and SCHEMA_PATH.exists():
        try:
            schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
            jsonschema_validate(instance=record, schema=schema)
        except ValidationError as exc:
            r.error(f"JSON Schema violation: {exc.message}")

    return r


# ── File loading ──────────────────────────────────────────────────────────────

def load_yaml_file(path: Path) -> tuple[dict | None, str | None]:
    """Return (record_dict, None) on success, (None, error_msg) on failure."""
    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            return None, f"YAML file does not contain a mapping (got {type(data).__name__})"
        return data, None
    except yaml.YAMLError as exc:
        return None, f"YAML parse error: {exc}"
    except OSError as exc:
        return None, f"File read error: {exc}"


# ── Main ──────────────────────────────────────────────────────────────────────

def collect_yaml_files(paths: list[str]) -> list[Path]:
    """Resolve CLI arguments to a list of YAML file paths."""
    if paths:
        return [Path(p) for p in paths]
    return sorted(DATA_DIR.glob("**/*.yaml"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate expansion YAML records against the schema."
    )
    parser.add_argument(
        "files",
        nargs="*",
        metavar="FILE",
        help="YAML files to validate. Defaults to all data/firms/**/*.yaml",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if there are any warnings (in addition to errors).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-record output; only print summary.",
    )
    args = parser.parse_args(argv)

    files = collect_yaml_files(args.files)
    if not files:
        print("No YAML files found to validate.")
        return 0

    seen_ids: set[str] = set()
    results: list[ValidationResult] = []
    total_errors = 0
    total_warnings = 0

    for file_path in files:
        record, load_err = load_yaml_file(file_path)
        if load_err:
            vr = ValidationResult(str(file_path))
            vr.error(load_err)
            results.append(vr)
            total_errors += 1
            continue

        vr = validate_record(record, str(file_path), seen_ids)
        results.append(vr)
        total_errors += len(vr.errors)
        total_warnings += len(vr.warnings)

    if not args.quiet:
        for vr in results:
            print(str(vr))
            print()

    print(f"Validated {len(files)} file(s): {total_errors} error(s), {total_warnings} warning(s).")

    if total_errors > 0:
        return 1
    if args.strict and total_warnings > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
