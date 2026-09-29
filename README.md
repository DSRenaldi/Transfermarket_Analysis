# Football Player Value Analytics

An analytics portfolio project for evaluating football player market value in
the context of time-aligned performance, age, position, club, competition, and
transfer activity.

The project is currently implementing the PostgreSQL-based data foundation.
See [the Phase 1 runbook](docs/phase1-postgresql.md) and the detailed analytical
brief in `context-transfermarket.md`.

## Current pipeline

1. `src/acquire_data.py` downloads and fingerprints all 12 published source tables.
2. `src/load_postgres.py` loads immutable text staging tables and controlled mappings.
3. `src/audit_phase1.py` validates keys, relationships, dates, numerics, mappings,
   and competition-season coverage.
4. Audit evidence is written to `reports/data_audit/` and PostgreSQL schema
   `tm_audit`.

Downloaded source files and local environments are excluded from Git.
