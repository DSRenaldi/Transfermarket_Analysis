"""Verify that the Phase 3 analysis model and evidence are complete."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from db_connection import connect


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "analysis"
EXPECTED_TABLES = {
    "methodology_parameters",
    "position_metric_weight",
    "age_band_definition",
    "fact_player_season_kpi",
    "fact_player_value_development",
    "fact_value_efficiency",
    "fact_transfer_value_outcome",
    "agg_market_value_by_age",
    "agg_peer_group_benchmark",
    "agg_transfer_value_outcome",
}
EXPECTED_VIEWS = {
    "vw_value_efficiency_ranking",
    "vw_player_value_development",
    "vw_transfer_value_outcomes",
}


def relation_names(cur, relation_type: str) -> set[str]:
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'tm_analysis' AND table_type = %s
        """,
        (relation_type,),
    )
    return {row[0] for row in cur.fetchall()}


def main() -> int:
    manifest = json.loads(
        (REPORT_DIR / "phase3_build_manifest.json").read_text(encoding="utf-8")
    )
    summary = json.loads(
        (REPORT_DIR / "phase3_validation_summary.json").read_text(encoding="utf-8")
    )
    expected_counts = {row["table"]: row["rows"] for row in manifest["tables"]}

    assert manifest["schema"] == "tm_analysis"
    assert manifest["methodology_version"] == "v1.0"
    assert summary["failed_checks"] == 0, summary["failed_check_names"]
    assert summary["score_eligible_player_seasons"] > 0
    assert summary["peer_group_count"] == 45

    with connect() as conn, conn.cursor() as cur:
        tables = relation_names(cur, "BASE TABLE")
        views = relation_names(cur, "VIEW")
        assert EXPECTED_TABLES <= tables, EXPECTED_TABLES - tables
        assert EXPECTED_VIEWS <= views, EXPECTED_VIEWS - views

        for table, expected_count in expected_counts.items():
            cur.execute(f'SELECT COUNT(*) FROM tm_analysis."{table}"')
            actual_count = cur.fetchone()[0]
            assert actual_count == expected_count, (table, expected_count, actual_count)

        cur.execute(
            """
            SELECT COUNT(*)
            FROM tm_analysis.fact_value_efficiency
            WHERE minutes_played < 900
               OR season_end_market_value_eur <= 0
               OR season_end_valuation_lag_days NOT BETWEEN 0 AND 365
            """
        )
        assert cur.fetchone()[0] == 0

    with (REPORT_DIR / "phase3_validation.csv").open(
        encoding="utf-8", newline=""
    ) as source:
        validation_rows = list(csv.DictReader(source))
    assert len(validation_rows) == summary["check_count"]
    assert not [row for row in validation_rows if row["status"] == "FAIL"]

    with (REPORT_DIR / "phase3_peer_group_summary.csv").open(
        encoding="utf-8", newline=""
    ) as source:
        peer_rows = list(csv.DictReader(source))
    assert len(peer_rows) == 45
    assert min(int(row["player_count"]) for row in peer_rows) >= 30

    top_export = REPORT_DIR / "phase3_top_efficiency.csv"
    assert top_export.exists() and top_export.stat().st_size > 0
    assert (REPORT_DIR / "phase3-analysis.md").exists()

    print("Phase 3 verification passed")
    print(f"database={manifest['database']}")
    print(f"analysis_tables={len(EXPECTED_TABLES)}")
    print(f"analysis_views={len(EXPECTED_VIEWS)}")
    print(f"validation_checks={summary['check_count']}")
    print(f"scored_player_seasons={summary['score_eligible_player_seasons']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
