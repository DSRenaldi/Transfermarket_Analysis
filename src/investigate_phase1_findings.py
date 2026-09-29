"""Export focused evidence for Phase 1 audit findings that require context."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from db_connection import connect


REPORT_DIR = Path("reports/data_audit")
NUMERIC_PATTERN = r"^-?[0-9]+(?:\.[0-9]+)?$"

QUERIES = {
    "height_outliers": (
        """
        SELECT player_id, name, position, sub_position, height_in_cm
        FROM tm_raw.players
        WHERE height_in_cm ~ %s
          AND height_in_cm::numeric NOT BETWEEN 100 AND 230
        ORDER BY height_in_cm::numeric, player_id
        """,
        (NUMERIC_PATTERN,),
    ),
    "minutes_outliers": (
        """
        SELECT a.appearance_id, a.player_id, a.player_name, a.game_id,
               a.date, a.competition_id, a.minutes_played,
               g.home_club_name, g.away_club_name
        FROM tm_raw.appearances a
        LEFT JOIN tm_raw.games g ON a.game_id = g.game_id
        WHERE a.minutes_played ~ %s AND a.minutes_played::numeric > 130
        ORDER BY a.minutes_played::numeric DESC, a.appearance_id
        """,
        (NUMERIC_PATTERN,),
    ),
    "future_transfer_summary": (
        """
        SELECT transfer_date, transfer_season, COUNT(*) AS transfer_rows,
               COUNT(*) FILTER (WHERE transfer_fee IS NOT NULL) AS rows_with_fee
        FROM tm_raw.transfers
        WHERE transfer_date::date > CURRENT_DATE
        GROUP BY transfer_date, transfer_season
        ORDER BY transfer_date, transfer_season
        """,
        (),
    ),
    "orphan_game_competitions": (
        """
        SELECT g.competition_id, g.competition_type, COUNT(*) AS game_rows,
               MIN(g.date::date) AS min_date, MAX(g.date::date) AS max_date
        FROM tm_raw.games g
        LEFT JOIN tm_raw.competitions c ON g.competition_id = c.competition_id
        WHERE c.competition_id IS NULL
        GROUP BY g.competition_id, g.competition_type
        ORDER BY game_rows DESC, g.competition_id
        """,
        (),
    ),
    "orphan_game_competition_samples": (
        """
        WITH ranked AS (
          SELECT g.competition_id, g.date, g.home_club_name, g.away_club_name,
                 g.round, g.url,
                 ROW_NUMBER() OVER (PARTITION BY g.competition_id ORDER BY g.date DESC, g.game_id) AS row_number
          FROM tm_raw.games g
          LEFT JOIN tm_raw.competitions c ON g.competition_id = c.competition_id
          WHERE c.competition_id IS NULL
        )
        SELECT competition_id, date, home_club_name, away_club_name, round, url
        FROM ranked
        WHERE row_number <= 3
        ORDER BY competition_id, date DESC
        """,
        (),
    ),
    "orphan_entity_context": (
        """
        WITH findings AS (
          SELECT 'game_events.player_id' AS relationship, g.competition_type,
                 e.competition_id, COUNT(*) AS orphan_rows
          FROM (
            SELECT ge.*, ga.competition_id
            FROM tm_raw.game_events ge
            JOIN tm_raw.games ga ON ge.game_id = ga.game_id
          ) e
          JOIN tm_raw.games g ON e.game_id = g.game_id
          LEFT JOIN tm_raw.players p ON e.player_id = p.player_id
          WHERE e.player_id IS NOT NULL AND p.player_id IS NULL
          GROUP BY g.competition_type, e.competition_id
          UNION ALL
          SELECT 'game_lineups.player_id', g.competition_type,
                 g.competition_id, COUNT(*)
          FROM tm_raw.game_lineups l
          JOIN tm_raw.games g ON l.game_id = g.game_id
          LEFT JOIN tm_raw.players p ON l.player_id = p.player_id
          WHERE l.player_id IS NOT NULL AND p.player_id IS NULL
          GROUP BY g.competition_type, g.competition_id
          UNION ALL
          SELECT 'games.home_club_id', g.competition_type,
                 g.competition_id, COUNT(*)
          FROM tm_raw.games g
          LEFT JOIN tm_raw.clubs c ON g.home_club_id = c.club_id
          WHERE g.home_club_id IS NOT NULL AND c.club_id IS NULL
          GROUP BY g.competition_type, g.competition_id
          UNION ALL
          SELECT 'games.away_club_id', g.competition_type,
                 g.competition_id, COUNT(*)
          FROM tm_raw.games g
          LEFT JOIN tm_raw.clubs c ON g.away_club_id = c.club_id
          WHERE g.away_club_id IS NOT NULL AND c.club_id IS NULL
          GROUP BY g.competition_type, g.competition_id
        )
        SELECT relationship, competition_type, competition_id, orphan_rows
        FROM findings
        ORDER BY relationship, orphan_rows DESC, competition_id
        """,
        (),
    ),
}


def write_csv(name: str, columns: list[str], rows: list[tuple[Any, ...]]) -> None:
    path = REPORT_DIR / f"{name}.csv"
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(columns)
        writer.writerows(rows)


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn, conn.cursor() as cur:
        for name, (query, parameters) in QUERIES.items():
            cur.execute(query, parameters)
            rows = cur.fetchall()
            columns = [column.name for column in cur.description]
            write_csv(name, columns, rows)
            print(f"Wrote {name}.csv ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
