# Schema Reference — ME Law Firm Expansion Tracker

Schema version: **1.0.0**  
File: `data/schema/expansion.schema.json`

---

## Overview

Every expansion event is stored as a single YAML file in `data/firms/YYYY/`.  
All YAML files are validated against `expansion.schema.json`.

---

## Fields

### `record_id` *(required)*
**Type:** string  
**Pattern:** `^[a-z0-9][a-z0-9-]*[a-z0-9]$`  
Unique identifier for this record. Must be a lowercase slug using only letters, digits, and hyphens. Must not start or end with a hyphen. Should match the filename (without `.yaml`).

### `firm_name` *(required)*
**Type:** string  
Full canonical name of the law firm. UTF-8 encoding; preserve non-ASCII characters (e.g. `Müller & Partners LLP`).

### `expansion_type` *(required)*
**Type:** enum  
Type of expansion event. Must be one of the values in `data/taxonomy/expansion-types.txt`.

### `practice_areas` *(required)*
**Type:** array of enum  
Minimum 1 item. Each item must be one of the 24 canonical values in `data/taxonomy/practice-areas.txt`.

### `country` *(required)*
**Type:** string  
**Pattern:** `^[A-Z]{2}$`  
ISO 3166-1 alpha-2 country code (two uppercase letters). See `data/taxonomy/countries.txt`.

### `region` *(optional)*
**Type:** string  
Human-readable region name (e.g. `Middle East`, `GCC`).

### `city` *(optional)*
**Type:** string  
City name. Preserve original diacritics (e.g. `Zürich`, `São Paulo`).

### `announced_date` *(required)*
**Type:** string  
**Pattern:** `^[0-9]{4}-[0-9]{2}-[0-9]{2}$`  
ISO 8601 date (YYYY-MM-DD) of the first known public announcement.

### `effective_date` *(optional)*
**Type:** string  
**Pattern:** `^[0-9]{4}-[0-9]{2}-[0-9]{2}$`  
ISO 8601 date when the expansion takes effect. May be months or years after `announced_date`.

### `source_url` *(required)*
**Type:** string (URI)  
**Pattern:** `^https?://`  
URL of the primary supporting source.

### `source_type` *(required)*
**Type:** enum  
Category of the source. Must be one of the values in `data/taxonomy/source-types.txt`.

### `confidence` *(required)*
**Type:** enum  
Confidence in the accuracy of this record. Must be one of the values in `data/taxonomy/confidence-levels.txt`.

### `status` *(required)*
**Type:** enum  
Lifecycle status of the record. Must be one of: `draft`, `under_review`, `verified`, `published`, `archived`.

### `headcount` *(optional)*
**Type:** integer (minimum: 1)  
Number of people involved in the expansion event, if known.

### `related_records` *(optional)*
**Type:** array of string  
List of `record_id` values of logically related records. Must not include the record's own `record_id`.

### `tags` *(optional)*
**Type:** array of string  
Free-form supplemental labels for filtering (e.g. `["difc", "vision-2030"]`).

### `notes` *(optional)*
**Type:** string (max 1000 characters; preferred max 500)  
Free-form notes about the expansion event. Use this for context that doesn't fit structured fields.

### `created_at` *(required)*
**Type:** string  
**Pattern:** `^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]+)?Z$`  
ISO 8601 UTC datetime when this record was first created.

### `last_modified` *(required)*
**Type:** string  
**Pattern:** same as `created_at`  
ISO 8601 UTC datetime when this record was last updated.

### `schema_version` *(required)*
**Type:** string  
**Pattern:** `^[0-9]+\\.[0-9]+\\.[0-9]+$`  
Semantic version of the schema this record conforms to (e.g. `1.0.0`).

### `created_by` *(optional)*
**Type:** string  
GitHub username or automation ID that created this record.

---

## Validation Rules

### Errors (block CI)
- Any required field is missing or null
- `expansion_type` not in the controlled vocabulary
- `practice_areas` is empty or contains unknown values
- `country` does not match `^[A-Z]{2}$`
- `announced_date` or `effective_date` not in YYYY-MM-DD format
- `source_url` does not start with `http://` or `https://`
- `source_type` not in the controlled vocabulary
- `confidence` not in the controlled vocabulary
- `status` not in the controlled vocabulary
- `record_id` fails the slug pattern
- Duplicate `record_id` across files
- `related_records` contains a self-reference
- `headcount` is not a positive integer
- `created_at` or `last_modified` not in ISO 8601 UTC format
- `schema_version` not in semver format

### Warnings (reported but do not block)
- `announced_date` is in the future
- `announced_date` is more than 2 years old and `status` is still `draft`
- `effective_date` is earlier than `announced_date`
- `confidence` is `unverified` and `status` is `published`
- `notes` exceeds 500 characters
- `region` is set but `city` is absent
- `confidence` is `confirmed` or `high` but `source_type` is a weak source

---

## Changelog

See [schema-changelog.md](../data/schema/schema-changelog.md).
