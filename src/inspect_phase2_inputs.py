"""Profile source relationships needed to finalize the Phase 2 model."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from db_connection import connect


SCOPE_COMPETITIONS = ("GB1", "ES1", "IT1", "L1", "FR1")
SCOPE_SEASONS = (2023, 2024, 2025)


def rows_as_dicts(cur) -> list[dict[str, object]]:
    columns = [column.name for column in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def main() -> int:
    report: dict[str, object] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope_competitions": SCOPE_COMPETITIONS,
        "scope_seasons": SCOPE_SEASONS,
    }
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT type AS lineup_type, COUNT(*) AS rows
            FROM tm_raw.game_lineups
            GROUP BY type
            ORDER BY rows DESC, lineup_type
            """
        )
        report["lineup_types"] = rows_as_dicts(cur)

        cur.execute(
            """
            SELECT COUNT(*) AS duplicate_groups,
                   COALESCE(SUM(group_size - 1), 0) AS duplicate_excess_rows
            FROM (
              SELECT game_id, player_id, COUNT(*) AS group_size
              FROM tm_raw.game_lineups
              GROUP BY game_id, player_id
              HAVING COUNT(*) > 1
            ) duplicate_lineups
            """
        )
        report["lineup_player_game_duplicates"] = rows_as_dicts(cur)[0]

        cur.execute(
            """
            SELECT g.competition_id,
                   g.season::integer AS season,
                   COUNT(*) AS appearance_rows,
                   COUNT(DISTINCT a.player_id) AS players,
                   COUNT(DISTINCT a.game_id) AS games,
                   COUNT(*) FILTER (WHERE p.player_id IS NULL) AS missing_player_dimension_rows,
                   COUNT(*) FILTER (WHERE c.club_id IS NULL) AS missing_club_dimension_rows,
                   COUNT(*) FILTER (
                     WHERE a.minutes_played::numeric < 0 OR a.minutes_played::numeric > 130
                   ) AS invalid_minute_rows
            FROM tm_raw.appearances a
            JOIN tm_raw.games g ON a.game_id = g.game_id
            LEFT JOIN tm_raw.players p ON a.player_id = p.player_id
            LEFT JOIN tm_raw.clubs c ON a.player_club_id = c.club_id
            WHERE g.competition_id = ANY(%s)
              AND g.season::integer = ANY(%s)
            GROUP BY g.competition_id, g.season::integer
            ORDER BY season, competition_id
            """,
            (list(SCOPE_COMPETITIONS), list(SCOPE_SEASONS)),
        )
        report["v1_appearance_scope"] = rows_as_dicts(cur)

        cur.execute(
            """
            SELECT COUNT(*) AS rows,
                   COUNT(*) FILTER (WHERE l.game_lineups_id IS NULL) AS without_lineup_match,
                   COUNT(*) FILTER (WHERE l.type = 'starting_lineup') AS starters,
                   COUNT(*) FILTER (WHERE l.type = 'substitutes') AS substitutes
            FROM tm_raw.appearances a
            JOIN tm_raw.games g ON a.game_id = g.game_id
            LEFT JOIN tm_raw.game_lineups l
              ON a.game_id = l.game_id AND a.player_id = l.player_id
            WHERE g.competition_id = ANY(%s)
              AND g.season::integer = ANY(%s)
            """,
            (list(SCOPE_COMPETITIONS), list(SCOPE_SEASONS)),
        )
        report["v1_lineup_match"] = rows_as_dicts(cur)[0]

        cur.execute(
            """
            SELECT g.game_id, g.competition_id, g.season::integer AS season,
                   g.date, g.home_club_name, g.away_club_name,
                   g.home_club_goals, g.away_club_goals
            FROM tm_raw.games g
            LEFT JOIN tm_raw.appearances a ON g.game_id = a.game_id
            WHERE g.competition_id = ANY(%s)
              AND g.season::integer = ANY(%s)
            GROUP BY g.game_id, g.competition_id, g.season, g.date,
                     g.home_club_name, g.away_club_name,
                     g.home_club_goals, g.away_club_goals
            HAVING COUNT(a.appearance_id) = 0
            ORDER BY g.date, g.game_id
            """,
            (list(SCOPE_COMPETITIONS), list(SCOPE_SEASONS)),
        )
        report["v1_games_without_appearances"] = rows_as_dicts(cur)

    destination = Path("reports/data_model/phase2_input_profile.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"Phase 2 input profile written to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
