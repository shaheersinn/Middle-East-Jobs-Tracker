# Schema Changelog

All notable changes to `expansion.schema.json` are documented here.
Follows [Semantic Versioning](https://semver.org/).

---

## [1.0.0] — 2026-03-11

### Added
- Initial schema for law-firm expansion records.
- Required fields: `record_id`, `firm_name`, `expansion_type`, `practice_areas`,
  `country`, `announced_date`, `source_url`, `source_type`, `confidence`, `status`,
  `created_at`, `last_modified`, `schema_version`.
- Optional fields: `region`, `city`, `effective_date`, `headcount`,
  `related_records`, `tags`, `notes`, `created_by`.
- Controlled enumerations for: `expansion_type`, `practice_areas`, `source_type`,
  `confidence`, `status`.
- Pattern validation: `record_id` (lowercase-hyphen slug), `country` (ISO alpha-2),
  `announced_date` / `effective_date` (YYYY-MM-DD), `source_url` (https?://...),
  `created_at` / `last_modified` (ISO 8601 UTC datetime), `schema_version` (semver).
- 24 canonical practice areas aligned with the domain vocabulary.
- 9 expansion types aligned with the domain vocabulary.
- 5 confidence levels.
- 5 status values.
- 8 source types.

### Migration required
- None (initial version).

---

## Versioning Policy

| Change type | Version bump |
|---|---|
| Documentation / clarification only | PATCH (e.g. 1.0.1) |
| New optional field added | MINOR (e.g. 1.1.0) |
| Required field added, field removed, enum value removed, type changed | MAJOR (e.g. 2.0.0) |
