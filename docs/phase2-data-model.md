# Phase 2: Analytical data model

Phase 2 converts the immutable text staging layer into typed PostgreSQL tables
in `tm_analytics`. The model is designed for the React dashboard API and
time-aware SQL analysis. Shared dimensions may filter multiple facts, but the
dashboard must not create ambiguous fact-to-fact relationships.

## Reproduce the model

Run these commands after the Phase 1 load and audit have passed:

```powershell
.\.venv\Scripts\python src\inspect_phase2_inputs.py
.\.venv\Scripts\python src\build_phase2.py --replace
.\.venv\Scripts\python src\validate_phase2.py
.\.venv\Scripts\python src\verify_phase2.py
.\.venv\Scripts\python -m unittest discover -s tests -v
```

`--replace` drops and recreates only the exact `tm_analytics` schema. It does
not alter `tm_raw`, `tm_ref`, or unrelated PostgreSQL objects.

## Dimensions and control tables

| Table | Grain | Purpose |
| --- | --- | --- |
| `project_parameters` | one active parameter set | Analysis cutoff, minimum minutes, and v1 competition/season scope |
| `source_snapshot` | one source table | Row counts and observed business-date boundaries |
| `dim_player` | one player | Typed profile, position group, cleaned height, and quality flags |
| `dim_club` | one club | Typed club profile; profile attributes are not historical membership |
| `dim_competition` | one competition | Source competitions plus five documented analytical overrides |
| `dim_season` | one season-start year | Observed cross-competition season boundaries |
| `dim_date` | one calendar date | Shared date attributes |
| `dim_game` | one game | Historical competition, clubs, result, and appearance-coverage flag |
| `dim_competition_season` | one competition and season | Actual start/end dates and match-to-appearance coverage |

Stable source IDs are used as dimension keys. A missing source master record
remains a nullable dimension key plus a coverage flag; the build does not create
synthetic members merely to make foreign keys pass.

## Facts

| Table | Grain | Important behavior |
| --- | --- | --- |
| `fact_player_appearance` | one player in one match | Preserves all appearance rows, types metrics, flags invalid rows, and derives starter status where lineups match |
| `fact_player_valuation` | one player on one valuation date | Retains dated market value, age at valuation, and available historical club context |
| `fact_transfer` | one source transfer row | Separates fee states and matches the latest valuation on or before the transfer date |
| `fact_player_club_season` | one player, club, competition, season | Aggregates a club stint and aligns valuation to the last appearance in that stint |
| `fact_player_season` | one player, competition, season | Combines club stints without duplicating value; aligns one valuation to competition-season end |

`fact_player_club_season` and `fact_player_season` are restricted to the
confirmed v1 structural scope. They include goalkeepers for reconciliation, but
eligibility flags exclude goalkeepers from the main value analysis.

## Time alignment

- Transfer value: latest valid valuation with `valuation_date <= transfer_date`.
- Club-stint value: latest valid valuation on or before the player's last
  appearance for that club, competition, and season.
- Player-season value: latest valid valuation on or before the observed end date
  of that competition-season.
- Age is calculated against the same relevant reference date.
- Every as-of match retains its valuation date, lag in days, and match-status
  band. `stale_over_365_days` is visible and must not be presented as a fresh
  valuation.

Valuation keys copied into other facts are lineage attributes. They are not
foreign-key relationships and must not be used to create fact-to-fact BI joins.

## V1 scope and eligibility

The structural scope is `GB1`, `ES1`, `IT1`, `L1`, and `FR1`, with season start
years 2023, 2024, and 2025. `is_v1_value_analysis_eligible` additionally
requires an outfield player, at least 900 minutes, and a positive aligned
season-end value.

The model contains 8,316 player-competition-seasons; 4,412 meet all v1 value
analysis rules. The tables deliberately retain non-eligible rows so exclusions
can be explained and reconciled.

## Known coverage limitations

- Fourteen of the fifteen v1 competition-seasons have appearance data for every
  game. FR1 2025 has 305 of 306 games (99.6732%); game `4635303`, Nantes versus
  Toulouse on 2026-05-17, has no appearance rows.
- Thirty-two v1 appearance rows do not match a lineup row. Their starter status
  remains null rather than being inferred.
- Some season-end valuations are old. Dashboards and rankings must expose the
  valuation date and lag; freshness filtering is a Phase 3 decision.
- Positive numeric transfer fees exist for only 17,554 rows. Recorded zero and
  missing values retain separate statuses, and transfer type is not inferred.
- The historical transfer population is broader than the current player and
  club masters, so dimension coverage flags remain material.

## Dashboard relationships

Use one-to-many, single-direction relationships from shared dimensions to
facts. Recommended relationship keys are player, club, competition, season,
date, and game where applicable. Keep the two role-playing club keys in
`fact_transfer` and the primary/season-end club roles in
`fact_player_season` explicit; activate only the intended role for each visual
or use duplicated role-playing dimensions.

The convenience views `vw_v1_player_season`, `vw_v1_player_club_season`,
`vw_historical_transfers`, and `vw_data_freshness` support exploration. React
API queries must still use the documented grains and avoid ambiguous filter
paths or row multiplication.
