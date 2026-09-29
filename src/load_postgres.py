"""Load compressed source CSVs and reference mappings into PostgreSQL.

Connection details are read by psycopg from DATABASE_URL or the standard PGHOST,
PGPORT, PGDATABASE, PGUSER, and PGPASSWORD environment variables.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql

from db_connection import connect


RAW_TABLES = (
    "competitions",
    "clubs",
    "players",
    "games",
    "appearances",
    "player_valuations",
    "club_games",
    "game_events",
    "game_lineups",
    "transfers",
    "countries",
    "national_teams",
)
REFERENCE_FILES = (
    "position_mapping",
    "competition_type_mapping",
    "competition_id_overrides",
    "transfer_fee_rules",
)
INDEX_COLUMNS = {
    "competitions": ("competition_id",),
    "clubs": ("club_id", "domestic_competition_id"),
    "players": ("player_id", "current_club_id"),
    "games": ("game_id", "competition_id", "season", "date"),
    "appearances": ("appearance_id", "game_id", "player_id", "competition_id"),
    "player_valuations": ("player_id", "date", "current_club_id"),
    "club_games": ("game_id", "club_id"),
    "game_events": ("game_event_id", "game_id", "player_id"),
    "game_lineups": ("game_lineups_id", "game_id", "player_id"),
    "transfers": ("player_id", "transfer_date", "from_club_id", "to_club_id"),
    "countries": ("country_id",),
    "national_teams": ("national_team_id", "country_id"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--config-dir", type=Path, default=Path("config"))
    parser.add_argument("--raw-schema", default="tm_raw")
    parser.add_argument("--reference-schema", default="tm_ref")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace only the named project staging/reference tables if they exist",
    )
    parser.add_argument(
        "--only-reference",
        action="store_true",
        help="Load only controlled reference tables and leave raw tables unchanged",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/data_audit/postgres_load_manifest.json"),
    )
    return parser.parse_args()


def gzip_headers(path: Path) -> list[str]:
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as source:
        headers = next(csv.reader(source))
    if not headers or any(not header for header in headers):
        raise ValueError(f"Missing or empty CSV header in {path}")
    if len(headers) != len(set(headers)):
        raise ValueError(f"Duplicate CSV headers in {path}")
    return headers


def csv_headers(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        headers = next(csv.reader(source))
    if not headers or any(not header for header in headers):
        raise ValueError(f"Missing or empty CSV header in {path}")
    if len(headers) != len(set(headers)):
        raise ValueError(f"Duplicate CSV headers in {path}")
    return headers


def table_exists(cur: psycopg.Cursor, schema: str, table: str) -> bool:
    cur.execute("SELECT to_regclass(%s)", (f'"{schema}"."{table}"',))
    return cur.fetchone()[0] is not None


def prepare_table(
    cur: psycopg.Cursor,
    schema: str,
    table: str,
    columns: list[str],
    replace: bool,
) -> None:
    cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
    if table_exists(cur, schema, table):
        if not replace:
            raise RuntimeError(
                f"{schema}.{table} already exists; rerun with --replace to reload it"
            )
        cur.execute(
            sql.SQL("DROP TABLE {}.{}").format(
                sql.Identifier(schema), sql.Identifier(table)
            )
        )

    column_definitions = [
        sql.SQL("{} TEXT").format(sql.Identifier(column)) for column in columns
    ]
    column_definitions.extend(
        (
            sql.SQL(
                '"_source_row_number" BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY'
            ),
            sql.SQL(
                '"_loaded_at_utc" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP'
            ),
        )
    )
    cur.execute(
        sql.SQL("CREATE TABLE {}.{} ({})").format(
            sql.Identifier(schema),
            sql.Identifier(table),
            sql.SQL(", ").join(column_definitions),
        )
    )


def copy_stream(
    cur: psycopg.Cursor,
    schema: str,
    table: str,
    columns: list[str],
    source,
) -> None:
    statement = sql.SQL(
        "COPY {}.{} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE, NULL '', ENCODING 'UTF8')"
    ).format(
        sql.Identifier(schema),
        sql.Identifier(table),
        sql.SQL(", ").join(map(sql.Identifier, columns)),
    )
    with cur.copy(statement) as copy:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            copy.write(chunk)


def load_gzip_table(
    conn: psycopg.Connection,
    path: Path,
    schema: str,
    table: str,
    replace: bool,
) -> int:
    columns = gzip_headers(path)
    with conn.cursor() as cur:
        prepare_table(cur, schema, table, columns, replace)
        with gzip.open(path, "rb") as source:
            copy_stream(cur, schema, table, columns, source)
        cur.execute(
            sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                sql.Identifier(schema), sql.Identifier(table)
            )
        )
        row_count = cur.fetchone()[0]
        for column in INDEX_COLUMNS.get(table, ()):
            index_name = f"ix_{table}_{column}"
            cur.execute(
                sql.SQL("CREATE INDEX {} ON {}.{} ({})").format(
                    sql.Identifier(index_name),
                    sql.Identifier(schema),
                    sql.Identifier(table),
                    sql.Identifier(column),
                )
            )
        cur.execute(
            sql.SQL("ANALYZE {}.{}").format(
                sql.Identifier(schema), sql.Identifier(table)
            )
        )
    conn.commit()
    return row_count


def load_reference_table(
    conn: psycopg.Connection,
    path: Path,
    schema: str,
    table: str,
    replace: bool,
) -> int:
    columns = csv_headers(path)
    with conn.cursor() as cur:
        prepare_table(cur, schema, table, columns, replace)
        with path.open("rb") as source:
            copy_stream(cur, schema, table, columns, source)
        cur.execute(
            sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                sql.Identifier(schema), sql.Identifier(table)
            )
        )
        row_count = cur.fetchone()[0]
    conn.commit()
    return row_count


def main() -> int:
    args = parse_args()
    started_at = datetime.now(timezone.utc)
    loaded_tables: list[dict[str, object]] = []

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT current_database(), current_user, current_setting('server_version')"
            )
            database, user, server_version = cur.fetchone()

        if not args.only_reference:
            for table in RAW_TABLES:
                path = args.raw_dir / f"{table}.csv.gz"
                if not path.exists():
                    raise FileNotFoundError(f"Run acquire_data.py first; missing {path}")
                print(f"Loading {args.raw_schema}.{table} ...", flush=True)
                rows = load_gzip_table(conn, path, args.raw_schema, table, args.replace)
                loaded_tables.append(
                    {"schema": args.raw_schema, "table": table, "rows": rows}
                )

        for table in REFERENCE_FILES:
            path = args.config_dir / f"{table}.csv"
            print(f"Loading {args.reference_schema}.{table} ...", flush=True)
            rows = load_reference_table(
                conn, path, args.reference_schema, table, args.replace
            )
            loaded_tables.append(
                {"schema": args.reference_schema, "table": table, "rows": rows}
            )

    report = {
        "loaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(
            (datetime.now(timezone.utc) - started_at).total_seconds(), 3
        ),
        "database": database,
        "database_user": user,
        "postgresql_version": server_version,
        "tables": loaded_tables,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Load manifest written to {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
