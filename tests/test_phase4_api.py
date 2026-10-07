from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dashboard_api import json_safe, query_payload  # noqa: E402


class Phase4ApiTest(unittest.TestCase):
    def test_health_and_meta(self) -> None:
        health = query_payload("/api/health", {})
        meta = query_payload("/api/meta", {})
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["database"], "football_analytics")
        self.assertEqual(meta["methodologyVersion"], "v1.0")
        self.assertEqual(len(meta["competitions"]), 5)

    def test_overview_and_efficiency_respect_filters(self) -> None:
        params = {"season": ["2025"], "competition": ["GB1"]}
        overview = query_payload("/api/overview", params)
        efficiency = query_payload("/api/efficiency", {**params, "limit": ["50"]})
        self.assertGreater(overview["summary"]["player_seasons"], 0)
        self.assertTrue(efficiency["rows"])
        self.assertTrue(all(row["season_key"] == 2025 for row in efficiency["rows"]))
        self.assertTrue(all(row["competition_key"] == "GB1" for row in efficiency["rows"]))
        self.assertTrue(all(row["minutes_played"] >= 900 for row in efficiency["rows"]))

    def test_player_journey_is_dated(self) -> None:
        options = query_payload("/api/players", {})["rows"]
        self.assertTrue(options)
        player = query_payload("/api/player", {"player_key": [str(options[0]["player_key"])]})
        self.assertTrue(player["valuations"])
        dates = [row["valuation_date"] for row in player["valuations"]]
        self.assertEqual(dates, sorted(dates))

    def test_transfer_club_and_quality_payloads(self) -> None:
        transfers = query_payload("/api/transfers", {"horizon": ["12"]})
        clubs = query_payload("/api/clubs", {"season": ["2025"]})
        quality = query_payload("/api/quality", {})
        self.assertEqual(len(transfers["summary"]), 3)
        self.assertTrue(transfers["outcomes"])
        self.assertTrue(clubs["rows"])
        self.assertTrue(all(row["failed"] == 0 for row in quality["validation"]))
        self.assertEqual(len(quality["coverage"]), 15)

    def test_team_analysis_uses_historical_club_stints(self) -> None:
        options = query_payload("/api/team-options", {"season": ["2025"]})["rows"]
        self.assertTrue(options)
        selected = options[0]
        team = query_payload(
            "/api/team",
            {
                "season": ["2025"],
                "competition": [selected["competition_key"]],
                "club_key": [str(selected["club_key"])],
            },
        )
        self.assertEqual(team["profile"]["club_key"], selected["club_key"])
        self.assertEqual(team["summary"]["contributor_count"], len(team["roster"]))
        self.assertTrue(team["byPosition"])
        self.assertTrue(team["byAge"])
        self.assertGreater(team["benchmark"]["competition_club_count"], 1)
        self.assertTrue(all(row["appearances"] > 0 for row in team["roster"]))
        self.assertTrue(all(row["last_appearance_date"] >= row["aligned_valuation_date"] for row in team["roster"] if row["aligned_valuation_date"]))

    def test_react_production_build_exists(self) -> None:
        self.assertTrue((ROOT / "frontend" / "dist" / "index.html").exists())
        charts = (ROOT / "frontend" / "src" / "components" / "Charts.tsx").read_text(encoding="utf-8")
        self.assertIn('className="trend-value-label"', charts)
        self.assertIn('role="tooltip"', charts)
        self.assertIn("onMouseEnter={() => setActivePointIndex(index)}", charts)
        self.assertIn("tabIndex={0}", charts)
        self.assertIn('className="scatter-tooltip"', charts)
        self.assertIn("onMouseEnter={() => setActiveRowIndex(index)}", charts)
        self.assertIn("Value efficiency", charts)
        team_page = (ROOT / "frontend" / "src" / "pages" / "Team.tsx").read_text(encoding="utf-8")
        self.assertIn('aria-label="Search teams"', team_page)
        self.assertIn("normalizeTeamSearch", team_page)

    def test_display_text_repairs_common_source_mojibake(self) -> None:
        self.assertEqual(json_safe("FuÃŸballclub"), "Fußballclub")


if __name__ == "__main__":
    unittest.main()
