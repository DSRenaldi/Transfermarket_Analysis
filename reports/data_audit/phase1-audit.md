# Phase 1 Data Audit

Generated at: `2026-09-29T07:45:40.868397+00:00`

## Snapshot

- `games.date`: 2006-06-09 to 2026-07-06; missing=0, invalid=0, future=0.
- `appearances.date`: 2012-07-03 to 2026-06-28; missing=0, invalid=0, future=0.
- `player_valuations.date`: 2000-01-20 to 2026-06-12; missing=0, invalid=0, future=0.
- `game_events.date`: 2006-06-09 to 2026-07-06; missing=0, invalid=0, future=0.
- `game_lineups.date`: 2013-07-02 to 2026-07-06; missing=0, invalid=0, future=0.
- `transfers.transfer_date`: 1993-07-01 to 2030-06-30; missing=0, invalid=0, future=488.

## Recommended v1 scope

- Competitions: ES1, FR1, GB1, IT1, L1.
- Seasons: 2025, 2024, 2023.
- Players: outfield, minimum 900 minutes.
- Coverage rule: game count >= 85% of the competition's five-season local median and appearance coverage > 0.

## Key integrity

- Checks run: 13; failed: 0.

## Numeric quality

- REVIEW `players.height_in_cm`: invalid=0, below minimum=13, above maximum=0.
- REVIEW `appearances.minutes_played`: invalid=0, below minimum=0, above maximum=3.

## Mapping and fee coverage

- Unmapped or invalid mapping categories: 0.
- Transfer fee `recorded_zero_ambiguous`: 96085 rows (54.854%).
- Transfer fee `unknown_or_undisclosed`: 61526 rows (35.1246%).
- Transfer fee `numeric_fee`: 17554 rows (10.0214%).

## Referential integrity

- Checks with orphan values: 16 of 23.
- REVIEW `game_lineups.club_id` -> `clubs.club_id`: 386777 rows (12.1666%).
- REVIEW `game_lineups.player_id` -> `players.player_id`: 315555 rows (9.9262%).
- REVIEW `game_events.club_id` -> `clubs.club_id`: 169317 rows (13.2853%).
- REVIEW `game_events.player_id` -> `players.player_id`: 128274 rows (10.0649%).
- REVIEW `transfers.from_club_id` -> `clubs.club_id`: 109676 rows (62.613%).
- REVIEW `player_valuations.current_club_id` -> `clubs.club_id`: 92973 rows (14.1662%).
- REVIEW `transfers.to_club_id` -> `clubs.club_id`: 92746 rows (52.9478%).
- REVIEW `club_games.club_id` -> `clubs.club_id`: 24060 rows (13.5232%).
- REVIEW `club_games.opponent_id` -> `clubs.club_id`: 24060 rows (13.5232%).
- REVIEW `games.home_club_id` -> `clubs.club_id`: 12818 rows (14.409%).
- REVIEW `games.away_club_id` -> `clubs.club_id`: 11242 rows (12.6374%).
- REVIEW `appearances.player_club_id` -> `clubs.club_id`: 11062 rows (0.5839%).
- REVIEW `players.current_club_id` -> `clubs.club_id`: 2986 rows (5.9543%).
- REVIEW `games.competition_id` -> `competitions.competition_id`: 1214 rows (1.3647%).
- REVIEW `clubs.domestic_competition_id` -> `competitions.competition_id`: 20 rows (2.5126%).

## High missingness

- `clubs.total_market_value`: 100.0% missing.
- `national_teams.coach_name`: 100.0% missing.
- `players.current_national_team_id`: 93.4994% missing.
- `game_events.player_assist_id`: 85.2269% missing.
- `players.international_caps`: 61.403% missing.
- `players.international_goals`: 61.403% missing.
- `game_events.player_in_id`: 50.5247% missing.
- `clubs.coach_name`: 49.3719% missing.
- `players.agent_name`: 46.4536% missing.
- `transfers.market_value_in_eur`: 38.9119% missing.
- `players.contract_expiration_date`: 37.0277% missing.
- `transfers.transfer_fee`: 35.1246% missing.
- `club_games.own_position`: 28.5269% missing.
- `club_games.opponent_position`: 28.5269% missing.
- `games.home_club_position`: 28.5269% missing.

## Method notes

- Raw CSV values are loaded as text so source semantics are preserved before typing and cleaning.
- A recorded transfer fee of zero remains ambiguous; it is not automatically labeled as a free transfer.
- Foreign-key exceptions can reflect national teams, defunct clubs, or incomplete entity coverage and require contextual review.
- The automatic coverage rule is a screening heuristic, not a guarantee that every round or appearance is complete.
- Detailed evidence is available in the CSV files in this directory and in the `tm_audit` PostgreSQL schema.
