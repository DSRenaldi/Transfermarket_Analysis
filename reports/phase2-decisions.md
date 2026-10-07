# Phase 2 Decisions

## Model and grains

- Use `tm_analytics` as the typed analytical schema; keep `tm_raw` immutable.
- Preserve four core grains: player-match appearance, player-date valuation,
  transfer event, and player-competition-season.
- Add `fact_player_club_season` as a documented intermediate analytical grain so
  transfers between clubs inside one competition-season remain traceable.
- In `fact_player_season`, sum performance across club stints, identify the
  primary club by minutes, identify the season-end club by latest appearance,
  and attach market value only once.
- Do not create direct fact-to-fact foreign keys or ambiguous dashboard
  relationships.

## Temporal rules

- An as-of valuation must be the latest valid valuation on or before its
  reference date. Future valuations are prohibited by build logic, constraints,
  and validation checks.
- Use the observed competition-season end date for player-season valuation and
  the last club appearance for club-stint valuation.
- Retain valuation date, lag days, and freshness band for every as-of result.
- Set the historical transfer analysis cutoff to the latest observed game date
  (`2026-07-06`) so transfers beyond performance coverage are excluded. This
  produces 520 post-cutoff records; it differs intentionally from the 488 rows
  that were future-dated relative to the Phase 1 audit date.

## Scope and exclusions

- Build player-season aggregates for all players in the five selected leagues
  and three selected seasons, including goalkeepers for reconciliation.
- Mark the main value-analysis population only when a row is outfield, has at
  least 900 minutes, and has a positive aligned season-end market value.
- Preserve invalid or unresolved records in lower-grain facts with explicit
  status flags; exclude them from aggregates rather than silently correcting
  them.
- Keep transfer fee zero as `recorded_zero_ambiguous`, missing as
  `unknown_or_undisclosed`, and positive numeric values as `numeric_fee`.

## Confirmed coverage findings

- The v1 appearance fact contains 162,694 valid rows with complete player and
  club dimension coverage; its minutes, goals, and assists reconcile exactly to
  the source and to the player-season aggregate.
- Fourteen v1 competition-seasons have full game/appearance coverage. FR1 2025
  is classified `HIGH`, not `FULL`, because one of 306 games has no appearances.
- Thirty-two v1 appearance rows lack a lineup match. `is_starter` remains null
  for these records.
- The model contains 8,538 player-club-seasons and 8,316
  player-competition-seasons. Of these, 4,412 satisfy the full v1 value-analysis
  eligibility rule.
- Validation comprises 43 checks with zero failures; all tested grains are
  unique and all as-of dates obey their reference-date boundary.
