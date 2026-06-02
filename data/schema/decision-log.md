# Decision Log

This file records all architectural and design decisions for the ME Law Firm Expansion Tracker.

| Cycle | Date | Decision | Reasoning | Tradeoffs | Quality Score |
|---|---|---|---|---|---|
| 1 | 2026-03-11 | **Audit Mode chosen for Cycle 1** | Repository had existing scraper/jobs infrastructure; expansion tracking schema was absent. Audit + Implementation combined. | Cycle was broader than a single scope, but all additions are additive. | 8/10 |
| 1 | 2026-03-11 | **JSON Schema draft-07 for expansion.schema.json** | Wide support; works with `jsonschema` Python library; human-readable. Rejected draft-2020 (less tooling support). | draft-07 has minor limitations vs. newer drafts but is well-supported. | — |
| 1 | 2026-03-11 | **One YAML file per expansion event** | Simplest to review, diff, validate, and deduplicate. Rejected a single large JSON array (hard to diff, merge conflicts). | Lots of small files in `data/firms/YYYY/`; acceptable for this scale. | — |
| 1 | 2026-03-11 | **24 canonical practice areas from problem statement** | Prevents naming drift; forces normalization; drives analytics. Rejected free-form strings (unquantifiable). | Rigid list requires taxonomy governance; covered in `normalize.py`. | — |
| 1 | 2026-03-11 | **Country field: ISO 3166-1 alpha-2 regex only (not lookup table)** | Simple and portable; avoids embedding a 250-row country table. "UK" is technically 2 uppercase letters but wrong ISO code; normalization handles it via `normalize.py`. | A full ISO lookup table would be stricter but adds maintenance burden. Revisit in Cycle 2. | — |
| 1 | 2026-03-11 | **`pyyaml` and `jsonschema` added to requirements.txt** | Required for `scripts/validate.py`. Minimal additions; both stable libraries with no known CVEs at this version. | Slight increase in install time. | — |
| 1 | 2026-03-11 | **`validate-on-pr.yml` scoped to data/schema/scripts/tests paths** | Avoids triggering on scraper changes that don't affect expansion records. | Might miss indirect breaks; acceptable for now. | — |
| 1 | 2026-03-11 | **Removed unused `global _RECRUITER_CACHE` in scrapers/recruiter.py** | Was causing F824 flake8 error, blocking CI. Dict mutation does not require `global`. No behavioral change. | Zero risk; backward compatible. | — |
