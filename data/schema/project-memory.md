# Project Memory

This file records cumulative architectural decisions, open questions, rejected options,
and risks for the ME Law Firm Expansion Tracker.

---

## Stable Decisions

- Schema uses JSON Schema draft-07 (`expansion.schema.json`).
- One YAML file per expansion event, stored in `data/firms/YYYY/`.
- 24 canonical practice areas are the single source of truth (from `data/taxonomy/practice-areas.txt`).
- 9 expansion types are authoritative (from `data/taxonomy/expansion-types.txt`).
- 5 confidence levels: `confirmed`, `high`, `medium`, `low`, `unverified`.
- 5 status values: `draft`, `under_review`, `verified`, `published`, `archived`.
- 8 source types (from `data/taxonomy/source-types.txt`).
- Country field uses ISO 3166-1 alpha-2 pattern check only (2 uppercase letters).
- Normalization is handled by `scripts/normalize.py` before validation.
- `pyyaml >= 6.0.0` and `jsonschema >= 4.17.0` are dependencies.
- CI validation workflow: `.github/workflows/validate-on-pr.yml`.
- Tests in `tests/test_validate.py` with fixtures in `tests/fixtures/`.
- `scripts/validate.py` is the single source of truth for validation logic.
- The existing scraper/jobs tracking system (`main.py`, `scrapers/`, etc.) is preserved unchanged.

---

## Open Questions

- Should the country field be validated against a full ISO 3166-1 alpha-2 lookup table
  (stricter) rather than just a 2-uppercase-letter regex? Currently using regex only.
- Should `deduplicate.py` use fuzzy matching on `firm_name` or exact matching only?
- Should `weekly-summary.yml` CI workflow be added to auto-generate reports?
- Should expansion records support a parent/child hierarchy for multi-city announcements?
- Should there be a `migrate.py` script to transform schema v1.0.0 -> v2.0.0?
- Should the `data/taxonomy/countries.txt` list be the authoritative validation set?

---

## Rejected Options

- **Free-form practice area strings**: rejected in favor of controlled vocabulary to enable analytics.
- **Single large JSON array for all records**: rejected in favor of one-file-per-event (better diffs, lower merge conflict risk).
- **JSON Schema draft-2020-12**: rejected due to lower tooling support; draft-07 is sufficient.
- **Auto-publishing unverified records**: rejected per security and quality policy.
- **Global `_RECRUITER_CACHE` declaration in `_populate_cache`**: removed; dict mutation does not require `global`; was causing F824 CI failure.

---

## Risks to Track

- Country validation using regex only (`^[A-Z]{2}$`) means "UK" would pass as a country code.
  Normalization via `normalize.py` is the mitigation. Consider a lookup table in Cycle 2.
- The `notes` field has a 1000-char schema max but a 500-char preferred max enforced only
  as a warning. Consider hardening to 500 in schema if data quality issues arise.
- No `migrate.py` exists yet; breaking schema changes will require a migration script.
- No deduplication script exists yet; duplicate records are only warned about, not blocked.
- The `data/taxonomy/countries.txt` is a subset of all ISO codes (ME-focused). If expansion
  records are added for non-ME countries, the list should be extended or validation changed.
