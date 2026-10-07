"""Build the Phase 2 dimensional analytics model in PostgreSQL."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from psycopg import sql

from db_connection import connect


ANALYTICS_SCHEMA = "tm_analytics"
SQL_FILES = (
    Path("sql/phase2/00_dimensions.sql"),
    Path("sql/phase2/01_facts.sql"),
    Path("sql/phase2/02_player_season.sql"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Drop and rebuild only the tm_analytics schema if it exists",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/data_model/phase2_build_manifest.json"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started_at = datetime.now(timezone.utc)
    executed_files: list[str] = []

    for path in SQL_FILES:
        if not path.exists():
            raise FileNotFoundError(path)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = %s)",
                (ANALYTICS_SCHEMA,),
            )
            schema_exists = cur.fetchone()[0]
            if schema_exists and not args.replace:
                raise RuntimeError(
                    f"Schema {ANALYTICS_SCHEMA} already exists; use --replace to rebuild it"
                )
            if schema_exists:
                cur.execute(
                    sql.SQL("DROP SCHEMA {} CASCADE").format(
                        sql.Identifier(ANALYTICS_SCHEMA)
                    )
                )

            cur.execute("SET LOCAL statement_timeout = 0")
            for path in SQL_FILES:
                print(f"Executing {path} ...", flush=True)
                cur.execute(path.read_text(encoding="utf-8"))
                executed_files.append(str(path))
        conn.commit()

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """,
                (ANALYTICS_SCHEMA,),
            )
            tables = [row[0] for row in cur.fetchall()]
            table_counts = []
            for table in tables:
                cur.execute(
                    sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                        sql.Identifier(ANALYTICS_SCHEMA), sql.Identifier(table)
                    )
                )
                table_counts.append({"table": table, "rows": cur.fetchone()[0]})

            cur.execute(
                """
                SELECT table_name
                FROM information_schema.views
                WHERE table_schema = %s
                ORDER BY table_name
                """,
                (ANALYTICS_SCHEMA,),
            )
            views = [row[0] for row in cur.fetchall()]
            cur.execute("SELECT current_database(), current_setting('server_version')")
            database, server_version = cur.fetchone()

    completed_at = datetime.now(timezone.utc)
    report = {
        "built_at_utc": completed_at.isoformat(),
        "duration_seconds": round((completed_at - started_at).total_seconds(), 3),
        "database": database,
        "postgresql_version": server_version,
        "schema": ANALYTICS_SCHEMA,
        "executed_sql_files": executed_files,
        "tables": table_counts,
        "views": views,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Phase 2 build manifest written to {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
