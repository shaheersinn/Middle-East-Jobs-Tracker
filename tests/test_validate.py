"""
tests/test_validate.py — Unit tests for scripts/validate.py

Run with:
    pytest tests/test_validate.py -v

Each test covers a specific validation rule. Fixtures are loaded from
tests/fixtures/{valid,invalid,edge_cases}/.
"""
import sys
import os
from pathlib import Path
from datetime import date, timedelta

import pytest

# Ensure repo root is on path so scripts/ is importable
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from scripts.validate import validate_record, load_yaml_file, main

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _base_record(**overrides) -> dict:
    """Return a minimal valid record dict, with optional field overrides."""
    rec = {
        "record_id": "test-firm-new-office-ae-2025",
        "firm_name": "Test Firm LLP",
        "expansion_type": "new_office",
        "practice_areas": ["Corporate & M&A"],
        "country": "AE",
        "announced_date": "2025-01-01",
        "source_url": "https://example.com/press",
        "source_type": "firm_press_release",
        "confidence": "confirmed",
        "status": "draft",
        "created_at": "2025-01-01T10:00:00Z",
        "last_modified": "2025-01-01T10:00:00Z",
        "schema_version": "1.0.0",
    }
    rec.update(overrides)
    return rec


def _validate(record: dict) -> tuple[list, list]:
    """Run validation and return (errors, warnings)."""
    result = validate_record(record, "test", set())
    return result.errors, result.warnings


# ── Valid cases ───────────────────────────────────────────────────────────────

class TestValidCases:
    def test_minimal_valid_record_passes(self):
        errors, warnings = _validate(_base_record())
        assert errors == []

    def test_valid_fixture_new_office(self):
        path = FIXTURES_DIR / "valid" / "valid_new_office.yaml"
        record, err = load_yaml_file(path)
        assert err is None
        errors, _ = _validate(record)
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_all_valid_fixtures_pass(self):
        valid_dir = FIXTURES_DIR / "valid"
        for yaml_file in valid_dir.glob("*.yaml"):
            record, load_err = load_yaml_file(yaml_file)
            assert load_err is None, f"{yaml_file}: {load_err}"
            result = validate_record(record, str(yaml_file), set())
            assert result.errors == [], (
                f"{yaml_file} has errors: {result.errors}"
            )

    def test_optional_fields_absent_is_valid(self):
        errors, _ = _validate(_base_record())
        assert errors == []

    def test_all_practice_areas_accepted(self):
        from scripts.validate import VALID_PRACTICE_AREAS
        for pa in VALID_PRACTICE_AREAS:
            errors, _ = _validate(_base_record(practice_areas=[pa]))
            assert errors == [], f"Practice area '{pa}' caused error: {errors}"

    def test_all_expansion_types_accepted(self):
        from scripts.validate import VALID_EXPANSION_TYPES
        for et in VALID_EXPANSION_TYPES:
            errors, _ = _validate(_base_record(expansion_type=et))
            assert errors == [], f"Expansion type '{et}' caused error: {errors}"

    def test_all_confidence_levels_accepted(self):
        from scripts.validate import VALID_CONFIDENCE
        for c in VALID_CONFIDENCE:
            errors, _ = _validate(_base_record(confidence=c))
            assert errors == [], f"Confidence '{c}' caused error: {errors}"

    def test_all_status_values_accepted(self):
        from scripts.validate import VALID_STATUS
        for s in VALID_STATUS:
            errors, _ = _validate(_base_record(status=s))
            assert errors == [], f"Status '{s}' caused error: {errors}"

    def test_non_ascii_firm_name_is_valid(self):
        errors, _ = _validate(_base_record(firm_name="Müller & Partners LLP"))
        assert errors == []

    def test_city_with_diacritics_is_valid(self):
        errors, _ = _validate(_base_record(city="Zürich"))
        assert errors == []

    def test_effective_date_after_announced_date_is_valid(self):
        errors, _ = _validate(
            _base_record(announced_date="2025-01-01", effective_date="2025-06-01")
        )
        assert errors == []

    def test_effective_date_18_months_later_is_valid(self):
        errors, _ = _validate(
            _base_record(announced_date="2025-01-01", effective_date="2026-07-01")
        )
        assert errors == []

    def test_headcount_positive_integer_is_valid(self):
        errors, _ = _validate(_base_record(headcount=5))
        assert errors == []

    def test_related_records_non_self_reference_is_valid(self):
        errors, _ = _validate(
            _base_record(
                record_id="firm-a-event-ae-2025",
                related_records=["firm-b-event-ae-2025"],
            )
        )
        assert errors == []

    def test_multiple_practice_areas_is_valid(self):
        errors, _ = _validate(
            _base_record(practice_areas=["Corporate & M&A", "Banking & Finance"])
        )
        assert errors == []


# ── Error cases ───────────────────────────────────────────────────────────────

class TestErrorCases:
    def test_missing_required_field_country(self):
        record = _base_record()
        del record["country"]
        errors, _ = _validate(record)
        assert any("country" in e for e in errors)

    def test_missing_required_field_firm_name(self):
        record = _base_record()
        del record["firm_name"]
        errors, _ = _validate(record)
        assert any("firm_name" in e for e in errors)

    def test_invalid_expansion_type(self):
        errors, _ = _validate(_base_record(expansion_type="unknown_type"))
        assert any("expansion_type" in e for e in errors)

    def test_invalid_practice_area(self):
        errors, _ = _validate(_base_record(practice_areas=["IP"]))
        assert any("practice_area" in e.lower() for e in errors)

    def test_empty_practice_areas(self):
        errors, _ = _validate(_base_record(practice_areas=[]))
        assert any("practice_area" in e.lower() for e in errors)

    def test_invalid_country_code_full_name(self):
        errors, _ = _validate(_base_record(country="United Arab Emirates"))
        assert any("country" in e for e in errors)

    def test_invalid_country_code_lowercase(self):
        errors, _ = _validate(_base_record(country="ae"))
        assert any("country" in e for e in errors)

    def test_invalid_country_code_uae_three_letters(self):
        # "UAE" is 3 letters — fails the 2-letter ISO alpha-2 regex.
        # The canonical form is "AE"; normalize before validating.
        errors, _ = _validate(_base_record(country="UAE"))
        assert any("country" in e for e in errors)

    def test_invalid_announced_date_wrong_format(self):
        errors, _ = _validate(_base_record(announced_date="15-01-2025"))
        assert any("announced_date" in e for e in errors)

    def test_invalid_announced_date_iso8601_datetime(self):
        errors, _ = _validate(_base_record(announced_date="2025-01-15T10:00:00Z"))
        assert any("announced_date" in e for e in errors)

    def test_invalid_source_url_no_scheme(self):
        errors, _ = _validate(_base_record(source_url="www.example.com"))
        assert any("source_url" in e for e in errors)

    def test_invalid_source_url_empty(self):
        errors, _ = _validate(_base_record(source_url=""))
        assert any("source_url" in e for e in errors)

    def test_invalid_source_type(self):
        errors, _ = _validate(_base_record(source_type="newspaper"))
        assert any("source_type" in e for e in errors)

    def test_invalid_confidence(self):
        errors, _ = _validate(_base_record(confidence="very_sure"))
        assert any("confidence" in e for e in errors)

    def test_invalid_status(self):
        errors, _ = _validate(_base_record(status="pending"))
        assert any("status" in e for e in errors)

    def test_invalid_record_id_uppercase(self):
        errors, _ = _validate(_base_record(record_id="UPPERCASE-ID"))
        assert any("record_id" in e for e in errors)

    def test_invalid_record_id_spaces(self):
        errors, _ = _validate(_base_record(record_id="firm name here"))
        assert any("record_id" in e for e in errors)

    def test_invalid_record_id_leading_hyphen(self):
        errors, _ = _validate(_base_record(record_id="-starts-with-hyphen"))
        assert any("record_id" in e for e in errors)

    def test_invalid_record_id_single_char(self):
        errors, _ = _validate(_base_record(record_id="a"))
        assert any("record_id" in e for e in errors)

    def test_duplicate_record_id(self):
        seen = {"test-firm-new-office-ae-2025"}
        record = _base_record()
        result = validate_record(record, "test", seen)
        assert any("Duplicate record_id" in e for e in result.errors)

    def test_self_reference_in_related_records(self):
        record = _base_record(
            record_id="firm-a-event-ae-2025",
            related_records=["firm-a-event-ae-2025"],
        )
        errors, _ = _validate(record)
        assert any("self-reference" in e for e in errors)

    def test_headcount_zero_is_invalid(self):
        errors, _ = _validate(_base_record(headcount=0))
        assert any("headcount" in e for e in errors)

    def test_headcount_negative_is_invalid(self):
        errors, _ = _validate(_base_record(headcount=-1))
        assert any("headcount" in e for e in errors)

    def test_headcount_string_is_invalid(self):
        errors, _ = _validate(_base_record(headcount="five"))
        assert any("headcount" in e for e in errors)

    def test_invalid_schema_version_no_patch(self):
        errors, _ = _validate(_base_record(schema_version="1.0"))
        assert any("schema_version" in e for e in errors)

    def test_invalid_created_at_missing_z(self):
        errors, _ = _validate(_base_record(created_at="2025-01-01T10:00:00"))
        assert any("created_at" in e for e in errors)

    def test_invalid_fixtures_all_fail(self):
        invalid_dir = FIXTURES_DIR / "invalid"
        for yaml_file in invalid_dir.glob("*.yaml"):
            record, load_err = load_yaml_file(yaml_file)
            if load_err:
                continue  # parse error is itself an error — this is expected
            result = validate_record(record, str(yaml_file), set())
            assert result.errors, (
                f"{yaml_file} was expected to fail validation but passed. "
                "Update the fixture or the rule."
            )


# ── Warning cases ─────────────────────────────────────────────────────────────

class TestWarningCases:
    def test_unverified_published_triggers_warning(self):
        _, warnings = _validate(
            _base_record(confidence="unverified", status="published")
        )
        assert any("unverified" in w for w in warnings)

    def test_effective_date_before_announced_date_triggers_warning(self):
        _, warnings = _validate(
            _base_record(announced_date="2025-06-01", effective_date="2025-01-01")
        )
        assert any("effective_date" in w for w in warnings)

    def test_future_announced_date_triggers_warning(self):
        future = (date.today() + timedelta(days=30)).isoformat()
        _, warnings = _validate(_base_record(announced_date=future))
        assert any("future" in w for w in warnings)

    def test_old_draft_record_triggers_warning(self):
        old_date = (date.today() - timedelta(days=800)).isoformat()
        _, warnings = _validate(_base_record(announced_date=old_date, status="draft"))
        assert any("draft" in w for w in warnings)

    def test_high_confidence_with_job_posting_triggers_warning(self):
        _, warnings = _validate(
            _base_record(confidence="confirmed", source_type="job_posting")
        )
        assert any("weak source" in w.lower() for w in warnings)

    def test_region_without_city_triggers_warning(self):
        _, warnings = _validate(_base_record(region="Middle East"))
        assert any("city" in w for w in warnings)

    def test_notes_over_500_chars_triggers_warning(self):
        long_notes = "x" * 501
        _, warnings = _validate(_base_record(notes=long_notes))
        assert any("notes" in w for w in warnings)

    def test_notes_exactly_500_chars_no_warning(self):
        ok_notes = "x" * 500
        _, warnings = _validate(_base_record(notes=ok_notes))
        assert not any("notes" in w for w in warnings)


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_edge_fixture_long_gap_dates(self):
        path = FIXTURES_DIR / "edge_cases" / "edge_long_gap_dates.yaml"
        record, err = load_yaml_file(path)
        assert err is None
        result = validate_record(record, str(path), set())
        assert result.errors == [], f"Edge case should pass: {result.errors}"

    def test_edge_fixture_non_ascii_firm_name(self):
        path = FIXTURES_DIR / "edge_cases" / "edge_non_ascii_firm_name.yaml"
        record, err = load_yaml_file(path)
        assert err is None
        result = validate_record(record, str(path), set())
        assert result.errors == [], f"Edge case should pass: {result.errors}"

    def test_single_practice_area_minimum(self):
        errors, _ = _validate(_base_record(practice_areas=["Tax"]))
        assert errors == []

    def test_all_24_practice_areas_in_one_record(self):
        from scripts.validate import VALID_PRACTICE_AREAS
        errors, _ = _validate(_base_record(practice_areas=list(VALID_PRACTICE_AREAS)))
        assert errors == []

    def test_http_source_url_is_valid(self):
        errors, _ = _validate(_base_record(source_url="http://example.com/release"))
        assert errors == []

    def test_notes_max_length_1000_chars_no_error(self):
        errors, _ = _validate(_base_record(notes="n" * 1000))
        assert errors == []

    def test_draft_to_archived_is_valid_record(self):
        errors, _ = _validate(_base_record(status="archived"))
        assert errors == []

    def test_country_sa_is_valid(self):
        errors, _ = _validate(_base_record(country="SA"))
        assert errors == []

    def test_country_gb_is_valid(self):
        errors, _ = _validate(_base_record(country="GB"))
        assert errors == []


# ── CLI / main() integration ──────────────────────────────────────────────────

class TestCLI:
    def test_main_valid_file_exits_zero(self, tmp_path):
        import yaml
        record = _base_record()
        f = tmp_path / "record.yaml"
        f.write_text(yaml.dump(record), encoding="utf-8")
        result = main([str(f)])
        assert result == 0

    def test_main_invalid_file_exits_one(self, tmp_path):
        import yaml
        record = _base_record(expansion_type="not_a_valid_type")
        f = tmp_path / "bad.yaml"
        f.write_text(yaml.dump(record), encoding="utf-8")
        result = main([str(f)])
        assert result == 1

    def test_main_strict_warnings_exit_one(self, tmp_path):
        import yaml
        record = _base_record(confidence="unverified", status="published")
        f = tmp_path / "warn.yaml"
        f.write_text(yaml.dump(record), encoding="utf-8")
        result = main(["--strict", str(f)])
        assert result == 1

    def test_main_no_files_exits_zero(self, tmp_path, monkeypatch):
        # Redirect DATA_DIR to empty tmp path
        import scripts.validate as sv
        original = sv.DATA_DIR
        sv.DATA_DIR = tmp_path
        result = main([])
        sv.DATA_DIR = original
        assert result == 0
