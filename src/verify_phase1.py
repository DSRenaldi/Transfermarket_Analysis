"""Verify that all Phase 1 PostgreSQL and report artifacts are complete."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from db_connection import connect


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "data_audit"
EXPECTED_RAW_TABLES = {
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
}
EXPECTED_REFERENCE_TABLES = {
    "position_mapping",
    "competition_type_mapping",
    "competition_id_overrides",
    "transfer_fee_rules",
}
EXPECTED_AUDIT_TABLES = {
    "table_profile",
    "column_missingness",
    "key_checks",
    "foreign_key_checks",
    "date_coverage",
    "numeric_quality",
    "mapping_coverage",
    "competition_season_coverage",
}


def database_tables(cur, schema: str) -> set[str]:
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = %s AND table_type = 'BASE TABLE'
        """,
        (schema,),
    )
    return {row[0] for row in cur.fetchall()}


def main() -> int:
    load_manifest = json.loads(
        (REPORT_DIR / "postgres_load_manifest.json").read_text(encoding="utf-8")
    )
    expected_counts = {
        row["table"]: row["rows"]
        for row in load_manifest["tables"]
        if row["schema"] == "tm_raw"
    }

    with connect() as conn, conn.cursor() as cur:
        raw_tables = database_tables(cur, "tm_raw")
        reference_tables = database_tables(cur, "tm_ref")
        audit_tables = database_tables(cur, "tm_audit")
        assert EXPECTED_RAW_TABLES <= raw_tables, EXPECTED_RAW_TABLES - raw_tables
        assert EXPECTED_REFERENCE_TABLES <= reference_tables, (
            EXPECTED_REFERENCE_TABLES - reference_tables
        )
        assert EXPECTED_AUDIT_TABLES <= audit_tables, EXPECTED_AUDIT_TABLES - audit_tables

        for table, expected_count in expected_counts.items():
            cur.execute(f'SELECT COUNT(*) FROM tm_raw."{table}"')
            actual_count = cur.fetchone()[0]
            assert actual_count == expected_count, (
                table,
                expected_count,
                actual_count,
            )

    summary = json.loads(
        (REPORT_DIR / "phase1_summary.json").read_text(encoding="utf-8")
    )
    assert summary["table_count"] == 12
    assert summary["failed_key_checks"] == 0
    assert summary["recommended_v1_scope"][
        "latest_three_common_adequate_seasons"
    ] == [2025, 2024, 2023]

    with (REPORT_DIR / "mapping_coverage.csv").open(
        encoding="utf-8", newline=""
    ) as source:
        mapping_rows = list(csv.DictReader(source))
    assert not [row for row in mapping_rows if row["status"] == "REVIEW"]

    print("Phase 1 verification passed")
    print(f"database={load_manifest['database']}")
    print(f"raw_tables={len(EXPECTED_RAW_TABLES)}")
    print(f"raw_rows={sum(expected_counts.values())}")
    print(f"reference_tables={len(EXPECTED_REFERENCE_TABLES)}")
    print(f"audit_tables={len(EXPECTED_AUDIT_TABLES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
