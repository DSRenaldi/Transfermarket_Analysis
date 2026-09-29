# Phase 1: PostgreSQL data foundation

This phase downloads the published Transfermarkt Datasets snapshot, preserves it
as compressed source files, loads it into PostgreSQL staging tables, profiles
data quality, and proposes an evidence-based initial analysis scope.

## Architecture

- `tm_raw`: byte-derived staging tables. Source columns remain `TEXT`; the loader
  adds only `_source_row_number` and `_loaded_at_utc`.
- `tm_ref`: controlled mappings for positions, competition types, and transfer-fee
  interpretation, including documented competition-ID overrides when games are
  absent from the source competition master.
- `tm_audit`: refreshed audit outputs generated from `tm_raw`.

Raw typing is intentionally deferred. This prevents missing values, zero fees,
codes, and malformed values from being silently coerced during ingestion.

## Connection configuration

Create or select an empty PostgreSQL database, then configure either
`DATABASE_URL` or the standard PostgreSQL environment variables. Do not put a
real password in a committed file.

For local development, copy `.env.example` to `.env` and edit it. `.env` is
ignored by Git and loaded automatically by the PostgreSQL scripts.

PowerShell example:

```powershell
$env:PGHOST = "localhost"
$env:PGPORT = "5432"
$env:PGDATABASE = "football_analytics"
$env:PGUSER = "postgres"
$env:PGPASSWORD = Read-Host "PostgreSQL password" -MaskInput
```

The scripts intentionally do not create a database or alter objects outside the
three project schemas.

## Reproduce Phase 1

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python src\acquire_data.py
.\.venv\Scripts\python src\create_database.py
.\.venv\Scripts\python src\load_postgres.py
.\.venv\Scripts\python src\audit_phase1.py
.\.venv\Scripts\python src\investigate_phase1_findings.py
.\.venv\Scripts\python src\verify_phase1.py
.\.venv\Scripts\python -m unittest discover -s tests -v
```

Use `--replace` with `load_postgres.py` only when the existing project staging
and mapping tables should be rebuilt. It never drops the database or an entire
schema.

## Audit outputs

The pipeline produces CSV evidence in `reports/data_audit/` and publishes the
same result sets to `tm_audit`:

- table row counts and column counts;
- column missingness;
- primary/candidate-key nulls and duplicates;
- foreign-key orphan counts;
- date coverage and invalid date formats;
- numeric parsing, negative-value, and range checks;
- position, competition, and fee-status mapping coverage;
- competition-season match and appearance coverage;
- an automatically screened v1 scope for the five major European leagues.

## Transfer limitation

The source `transfers` table has numeric `transfer_fee` but no reliable transfer
type. A zero fee therefore remains `recorded_zero_ambiguous`; it must not be
automatically labeled as a free transfer, loan, or loan return. A supplemental
source or explicit derivation rule is required before transfer-type analysis.
