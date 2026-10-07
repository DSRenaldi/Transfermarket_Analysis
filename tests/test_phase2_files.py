from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "data_model"
SQL_DIR = ROOT / "sql" / "phase2"


class Phase2FilesTest(unittest.TestCase):
    def test_phase2_sql_files_exist(self) -> None:
        expected = {"00_dimensions.sql", "01_facts.sql", "02_player_season.sql"}
        self.assertEqual({path.name for path in SQL_DIR.glob("*.sql")}, expected)

    def test_validation_has_no_failures(self) -> None:
        summary = json.loads(
            (REPORT_DIR / "phase2_validation_summary.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(summary["failed_checks"], 0)
        self.assertEqual(summary["failed_check_names"], [])

    def test_v1_has_fifteen_high_coverage_competition_seasons(self) -> None:
        with (REPORT_DIR / "phase2_v1_coverage.csv").open(
            encoding="utf-8", newline=""
        ) as source:
            rows = list(csv.DictReader(source))
        self.assertEqual(len(rows), 15)
        self.assertGreaterEqual(
            min(float(row["appearance_game_coverage_pct"]) for row in rows), 99
        )
        self.assertNotIn("REVIEW", {row["appearance_coverage_status"] for row in rows})

    def test_model_sql_prevents_future_valuation_leakage(self) -> None:
        facts_sql = (SQL_DIR / "01_facts.sql").read_text(encoding="utf-8")
        season_sql = (SQL_DIR / "02_player_season.sql").read_text(encoding="utf-8")
        self.assertIn("v.valuation_date <= t.transfer_date::DATE", facts_sql)
        self.assertIn("v.valuation_date <= cs.season_end_date", season_sql)
        self.assertIn("v.valuation_date <= r.last_appearance_date", season_sql)


if __name__ == "__main__":
    unittest.main()
