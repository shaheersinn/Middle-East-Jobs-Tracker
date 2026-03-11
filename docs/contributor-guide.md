# Contributor Guide — ME Law Firm Expansion Tracker

This guide explains how to add, edit, and validate expansion records.

---

## Quick Start

1. **Find the right directory**: all records go in `data/firms/YYYY/` (e.g. `data/firms/2026/`).
2. **Name the file**: use the format `firm-name-expansion-type-city-year.yaml`  
   Example: `latham-watkins-new-office-riyadh-2026.yaml`
3. **Fill in the fields**: see [Schema Reference](schema-reference.md) for all fields.
4. **Validate locally** before opening a PR:  
   ```bash
   python scripts/validate.py
   ```
5. **Open a PR**: CI will automatically re-validate.

---

## File Naming Convention

- Lowercase letters, digits, and hyphens only.
- Format: `{firm-slug}-{expansion-type}-{city-slug}-{year}.yaml`
- The `record_id` inside the file must match the filename (without `.yaml`).

| Component | Example |
|---|---|
| firm-slug | `latham-watkins` |
| expansion-type | `new-office` |
| city-slug | `riyadh` |
| year | `2026` |
| Full filename | `latham-watkins-new-office-riyadh-2026.yaml` |

---

## Required Fields

| Field | Description | Example |
|---|---|---|
| `record_id` | Unique slug matching the filename | `latham-watkins-new-office-riyadh-2026` |
| `firm_name` | Full canonical firm name | `Latham & Watkins LLP` |
| `expansion_type` | Type of expansion (see taxonomy) | `new_office` |
| `practice_areas` | List of practice areas (at least 1) | `[Corporate & M&A, Banking & Finance]` |
| `country` | ISO 3166-1 alpha-2 code | `AE`, `SA`, `GB` |
| `announced_date` | ISO 8601 date | `2026-01-15` |
| `source_url` | URL of primary source | `https://www.firm.com/news/...` |
| `source_type` | Category of source | `firm_press_release` |
| `confidence` | Confidence level | `confirmed` |
| `status` | Lifecycle status | `draft` |
| `created_at` | UTC datetime of record creation | `2026-01-15T10:00:00Z` |
| `last_modified` | UTC datetime of last update | `2026-01-15T10:00:00Z` |
| `schema_version` | Schema version (always `1.0.0` for now) | `1.0.0` |

---

## Optional Fields

| Field | Description |
|---|---|
| `region` | Human-readable region (e.g. `Middle East`) |
| `city` | City name, preserving diacritics |
| `effective_date` | ISO 8601 date when change takes effect |
| `headcount` | Number of people involved (positive integer) |
| `related_records` | List of related `record_id` values |
| `tags` | Free-form labels for filtering |
| `notes` | Notes (preferred max 500 chars) |
| `created_by` | GitHub username or automation ID |

---

## Controlled Vocabularies

### Expansion Types
See `data/taxonomy/expansion-types.txt` for the full list:
- `new_office`
- `new_practice_group`
- `merger`
- `lateral_hire_group`
- `office_relocation`
- `office_expansion`
- `strategic_alliance`
- `new_jurisdiction_license`
- `department_restructure`

### Practice Areas
See `data/taxonomy/practice-areas.txt` for the full list of 24 canonical values.
Always use the **exact** canonical name (case-sensitive).

### Confidence Levels
| Level | When to use |
|---|---|
| `confirmed` | Firm's own announcement or authoritative primary source |
| `high` | Strong third-party reporting from reputable legal press |
| `medium` | Multiple credible but indirect sources |
| `low` | Single weak signal (e.g. job posting only) |
| `unverified` | Insufficient evidence — requires manual review before publishing |

### Status Values and Transitions
| Status | Meaning | Allowed next states |
|---|---|---|
| `draft` | Initial entry, not yet reviewed | `under_review`, `archived` |
| `under_review` | Being reviewed for accuracy | `verified`, `archived` |
| `verified` | Confirmed accurate | `published`, `archived` |
| `published` | Live and visible | `archived` |
| `archived` | No longer active | — |

**Do not** publish `unverified` records without explicit approval.

### Country Codes
Use ISO 3166-1 alpha-2 only. Common examples:
- `AE` — United Arab Emirates
- `SA` — Saudi Arabia
- `QA` — Qatar
- `BH` — Bahrain
- `KW` — Kuwait
- `OM` — Oman
- `GB` — United Kingdom (not "UK")
- `US` — United States (not "USA")

See `data/taxonomy/countries.txt` for the full list.

---

## Normalization

If raw source text uses shorthand, normalize before saving:

| Raw input | Canonical value |
|---|---|
| `IP` | `Intellectual Property` |
| `M&A` | `Corporate & M&A` |
| `Privacy` | `Data Privacy & Protection` |
| `Labor` | `Employment & Labor` |
| `UK` | `GB` |
| `USA` | `US` |
| `United Arab Emirates` | `AE` |

Use the normalization helper:
```bash
python scripts/normalize.py
```

---

## Example Record

```yaml
record_id: example-firm-new-office-dubai-2026
firm_name: Example & Partners LLP
expansion_type: new_office
practice_areas:
  - Corporate & M&A
  - Banking & Finance
country: AE
region: Middle East
city: Dubai
announced_date: "2026-01-01"
effective_date: "2026-04-01"
source_url: https://www.examplefirm.com/news/2026/dubai-office
source_type: firm_press_release
confidence: confirmed
status: draft
headcount: 10
notes: "Short description of the expansion event."
created_at: "2026-01-01T10:00:00Z"
last_modified: "2026-01-01T10:00:00Z"
schema_version: "1.0.0"
created_by: your_github_username
```

---

## Validation

Run locally before opening a PR:
```bash
# Validate all records
python scripts/validate.py

# Validate a single file
python scripts/validate.py data/firms/2026/my-new-record.yaml

# Treat warnings as errors (strict mode)
python scripts/validate.py --strict
```

CI automatically validates all records on every PR.

---

## Getting Help

- Schema reference: [docs/schema-reference.md](schema-reference.md)
- Taxonomy reference: [docs/taxonomy-reference.md](taxonomy-reference.md)
- Migration guide: [docs/migration-guide.md](migration-guide.md)
- FAQ: [docs/faq.md](faq.md)
