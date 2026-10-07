"""Verify that the Phase 2 analytical model and evidence are complete."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from db_connection import connect


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "data_model"
EXPECTED_TABLES = {
    "project_parameters",
    "source_snapshot",
    "dim_competition",
    "dim_club",
    "dim_player",
    "dim_date",
    "dim_season",
    "dim_game",
    "dim_competition_season",
    "fact_player_appearance",
    "fact_player_valuation",
    "fact_transfer",
    "fact_player_club_season",
    "fact_player_season",
}
EXPECTED_VIEWS = {
    "vw_v1_player_season",
    "vw_v1_player_club_season",
    "vw_historical_transfers",
    "vw_data_freshness",
}


def relation_names(cur, relation_type: str) -> set[str]:
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'tm_analytics' AND table_type = %s
        """,
        (relation_type,),
    )
    return {row[0] for row in cur.fetchall()}


def main() -> int:
    manifest = json.loads(
        (REPORT_DIR / "phase2_build_manifest.json").read_text(encoding="utf-8")
    )
    expected_counts = {row["table"]: row["rows"] for row in manifest["tables"]}
    summary = json.loads(
        (REPORT_DIR / "phase2_validation_summary.json").read_text(encoding="utf-8")
    )

    assert manifest["schema"] == "tm_analytics"
    assert summary["failed_checks"] == 0, summary["failed_check_names"]

    with connect() as conn, conn.cursor() as cur:
        tables = relation_names(cur, "BASE TABLE")
        views = relation_names(cur, "VIEW")
        assert EXPECTED_TABLES <= tables, EXPECTED_TABLES - tables
        assert EXPECTED_VIEWS <= views, EXPECTED_VIEWS - views

        for table, expected_count in expected_counts.items():
            cur.execute(f'SELECT COUNT(*) FROM tm_analytics."{table}"')
            actual_count = cur.fetchone()[0]
            assert actual_count == expected_count, (table, expected_count, actual_count)

        cur.execute(
            """
            SELECT COUNT(*)
            FROM pg_constraint fk
            JOIN pg_class child ON child.oid = fk.conrelid
            JOIN pg_namespace child_ns ON child_ns.oid = child.relnamespace
            JOIN pg_class parent ON parent.oid = fk.confrelid
            JOIN pg_namespace parent_ns ON parent_ns.oid = parent.relnamespace
            WHERE fk.contype = 'f'
              AND child_ns.nspname = 'tm_analytics'
              AND parent_ns.nspname = 'tm_analytics'
              AND child.relname LIKE 'fact_%'
              AND parent.relname LIKE 'fact_%'
            """
        )
        assert cur.fetchone()[0] == 0

    with (REPORT_DIR / "phase2_validation.csv").open(
        encoding="utf-8", newline=""
    ) as source:
        validation_rows = list(csv.DictReader(source))
    assert len(validation_rows) == summary["check_count"]
    assert not [row for row in validation_rows if row["status"] == "FAIL"]

    with (REPORT_DIR / "phase2_v1_coverage.csv").open(
        encoding="utf-8", newline=""
    ) as source:
        coverage_rows = list(csv.DictReader(source))
    assert len(coverage_rows) == 15
    assert min(float(row["appearance_game_coverage_pct"]) for row in coverage_rows) >= 99

    print("Phase 2 verification passed")
    print(f"database={manifest['database']}")
    print(f"analytics_tables={len(EXPECTED_TABLES)}")
    print(f"analytics_views={len(EXPECTED_VIEWS)}")
    print(f"validation_checks={summary['check_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
