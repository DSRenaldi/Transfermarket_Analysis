# Phase 1 Decisions

## Confirmed analysis scope

- Database platform: PostgreSQL 18.
- Initial competitions: Premier League (`GB1`), LaLiga (`ES1`), Serie A (`IT1`), Bundesliga (`L1`), and Ligue 1 (`FR1`).
- Initial seasons: `2023`, `2024`, and `2025` (season start year).
- Player scope: outfield players with at least 900 minutes in a player-season.
- Market-value convention: the latest valuation on or before the documented season-end date, retaining the actual valuation date and valuation lag.
- Goalkeepers remain outside the main value-efficiency ranking until reliable goalkeeper-specific metrics are available.

## Cleaning and exclusion rules

- Preserve every downloaded source value unchanged in `tm_raw`; cleaning happens in downstream typed models.
- Convert player heights below 100 cm or above 230 cm to null in the cleaned layer and retain a data-quality flag. Thirteen source rows are below 100 cm.
- Quarantine appearance rows above 130 minutes from performance aggregation until reviewed. Three source rows exceed this threshold.
- Exclude transfers after the analytical cutoff from historical results and label them as scheduled/future transfers. The source contains 488 future-dated rows as of the audit date.
- Treat missing transfer fees as unknown, not zero.
- Treat recorded zero fees as ambiguous. Do not infer free transfer, loan, or loan return because the source has no reliable transfer-type field.
- Restrict fee-based comparisons to positive numeric fees and always display fee coverage.
- Derive squad value from dated player valuations; `clubs.total_market_value` is entirely missing in this snapshot.
- Preserve raw foreign-key exceptions. Do not create synthetic club or player records merely to silence integrity checks.

## Reference mappings

- All observed player position/subposition pairs map to Goalkeeper, Defender, Midfielder, Forward, or Unknown.
- All observed source competition types are mapped.
- Five competition IDs absent from the source master are handled through documented overrides: `CGB`, `COL1`, `KLUB`, `POCP`, and `UKRS`.
- The overrides resolve analytical categorization but do not conceal the raw master-data foreign-key gap.

## Material limitations for later phases

- Only 17,554 transfers (10.02%) have a positive numeric fee; 96,085 (54.85%) contain zero and 61,526 (35.12%) are missing.
- Transfer club IDs have limited master coverage because the transfer history is broader than the current club dimension.
- Event and lineup player coverage is weaker in qualifying rounds and domestic cups than appearance-table coverage.
- Current player market value is missing for 8,621 players, while historical valuation rows themselves contain no missing market values.
- Contract expiration is missing for 37.03% of players and should not be treated as a complete ranking feature.
- Future-dated transfer records extend to 2030 and require a cutoff in every historical analysis.

## Coverage decision

The five selected leagues have complete match and appearance coverage for the
2023, 2024, and 2025 seasons under the Phase 1 screening rule. Completeness is
assessed against a five-season local median so structural changes, such as Ligue
1 moving from 20 to 18 clubs, are not misclassified as missing data.
