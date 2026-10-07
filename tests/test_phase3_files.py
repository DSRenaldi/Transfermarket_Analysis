from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "analysis"
SQL_DIR = ROOT / "sql" / "phase3"


class Phase3FilesTest(unittest.TestCase):
    def test_phase3_sql_files_exist(self) -> None:
        expected = {
            "00_methodology.sql",
            "01_player_kpis.sql",
            "02_value_efficiency.sql",
            "03_transfer_outcomes.sql",
        }
        self.assertEqual({path.name for path in SQL_DIR.glob("*.sql")}, expected)

    def test_validation_has_no_failures(self) -> None:
        summary = json.loads(
            (REPORT_DIR / "phase3_validation_summary.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(summary["failed_checks"], 0)
        self.assertEqual(summary["failed_check_names"], [])
        self.assertEqual(summary["peer_group_count"], 45)

    def test_top_ranking_exposes_required_context(self) -> None:
        with (REPORT_DIR / "phase3_top_efficiency.csv").open(
            encoding="utf-8", newline=""
        ) as source:
            rows = list(csv.DictReader(source))
        self.assertTrue(rows)
        required = {
            "season_key",
            "competition_name",
            "position_group",
            "minutes_played",
            "peer_group_size",
            "season_end_valuation_date",
            "season_end_valuation_lag_days",
            "value_efficiency_score",
        }
        self.assertTrue(required <= set(rows[0]))

    def test_score_sql_uses_documented_formula_and_freshness(self) -> None:
        score_sql = (SQL_DIR / "02_value_efficiency.sql").read_text(
            encoding="utf-8"
        )
        kpi_sql = (SQL_DIR / "01_player_kpis.sql").read_text(encoding="utf-8")
        self.assertIn(") - c.market_value_z_score AS value_efficiency_score", score_sql)
        self.assertIn("maximum_season_valuation_lag_days", kpi_sql)
        self.assertIn("LN(1 + q.season_end_market_value_eur", score_sql)

    def test_phase2_birth_date_parser_accepts_source_timestamps(self) -> None:
        dimensions_sql = (ROOT / "sql" / "phase2" / "00_dimensions.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("LEFT(p.date_of_birth, 10)::DATE", dimensions_sql)


if __name__ == "__main__":
    unittest.main()
