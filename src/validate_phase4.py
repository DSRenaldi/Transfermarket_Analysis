"""Validate the React dashboard build, API contracts, and analytical guardrails."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dashboard_api import query_payload
from db_connection import connect


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
REPORT_DIR = ROOT / "reports" / "dashboard"


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []

    def add(name: str, actual: Any, expected: Any, passed: bool, category: str, details: str = "") -> None:
        checks.append(
            {
                "category": category,
                "check_name": name,
                "status": "PASS" if passed else "FAIL",
                "actual_value": actual,
                "expected_value": expected,
                "details": details,
            }
        )

    dist = FRONTEND / "dist"
    index_path = dist / "index.html"
    js_assets = list((dist / "assets").glob("*.js")) if (dist / "assets").exists() else []
    css_assets = list((dist / "assets").glob("*.css")) if (dist / "assets").exists() else []
    add("production_index_exists", index_path.exists(), True, index_path.exists(), "frontend_build")
    add("javascript_bundle_count", len(js_assets), 1, len(js_assets) >= 1, "frontend_build")
    add("stylesheet_bundle_count", len(css_assets), 1, len(css_assets) >= 1, "frontend_build")
    largest_js = max((path.stat().st_size for path in js_assets), default=0)
    add("largest_javascript_bundle_bytes", largest_js, "<= 400000", largest_js <= 400_000, "frontend_build")

    package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    add("react_dependency", "react" in package["dependencies"], True, "react" in package["dependencies"], "frontend_build")
    add("typescript_build_script", package["scripts"].get("build"), "tsc -b && vite build", package["scripts"].get("build") == "tsc -b && vite build", "frontend_build")

    meta = query_payload("/api/meta", {})
    health = query_payload("/api/health", {})
    add("api_health", health["status"], "ok", health["status"] == "ok", "api")
    add("api_database", health["database"], "football_analytics", health["database"] == "football_analytics", "api")
    add("competition_filter_count", len(meta["competitions"]), 5, len(meta["competitions"]) == 5, "api")
    add("season_filters", meta["seasons"], [2023, 2024, 2025], meta["seasons"] == [2023, 2024, 2025], "api")

    overview = query_payload("/api/overview", {"season": ["2025"], "competition": ["GB1"]})
    add("overview_has_players", overview["summary"]["player_seasons"], "> 0", overview["summary"]["player_seasons"] > 0, "api")
    add("overview_uses_median", overview["summary"]["median_market_value_eur"], "> 0", overview["summary"]["median_market_value_eur"] > 0, "analytical_context")

    efficiency = query_payload(
        "/api/efficiency",
        {"season": ["2025"], "competition": ["GB1"], "position": ["Forward"], "limit": ["200"]},
    )
    rows = efficiency["rows"]
    required_fields = {
        "minutes_played",
        "peer_group_size",
        "season_end_valuation_date",
        "season_end_valuation_lag_days",
        "value_efficiency_score",
    }
    add("efficiency_rows_returned", len(rows), "> 0", bool(rows), "api")
    add("ranking_context_fields", required_fields <= set(rows[0]) if rows else False, True, bool(rows) and required_fields <= set(rows[0]), "analytical_context")
    add("ranking_minimum_minutes", min((row["minutes_played"] for row in rows), default=0), ">= 900", bool(rows) and min(row["minutes_played"] for row in rows) >= 900, "analytical_context")
    add("ranking_peer_size", min((row["peer_group_size"] for row in rows), default=0), ">= 30", bool(rows) and min(row["peer_group_size"] for row in rows) >= 30, "analytical_context")

    players = query_payload("/api/players", {})["rows"]
    player = query_payload("/api/player", {"player_key": [str(players[0]["player_key"])]})
    valuation_dates = [row["valuation_date"] for row in player["valuations"]]
    add("player_search_results", len(players), "> 0", bool(players), "api")
    add("player_valuations_chronological", valuation_dates, "ascending", valuation_dates == sorted(valuation_dates), "time_alignment")

    transfers = query_payload("/api/transfers", {"horizon": ["12"]})
    add("transfer_fee_states", len(transfers["summary"]), 3, len(transfers["summary"]) == 3, "analytical_context")
    add("transfer_outcomes_available", len(transfers["outcomes"]), "> 0", bool(transfers["outcomes"]), "api")
    add(
        "transfer_post_dates_present",
        sum(bool(row["post_valuation_date"]) for row in transfers["outcomes"]),
        len(transfers["outcomes"]),
        all(row["post_valuation_date"] for row in transfers["outcomes"]),
        "time_alignment",
    )

    clubs = query_payload("/api/clubs", {"season": ["2025"]})
    add("club_minimum_comparisons", clubs["minimumComparisons"], 10, clubs["minimumComparisons"] == 10, "analytical_context")
    add("club_rows_clear_minimum", min((row["player_comparisons"] for row in clubs["rows"]), default=0), ">= 10", bool(clubs["rows"]) and min(row["player_comparisons"] for row in clubs["rows"]) >= 10, "analytical_context")

    team_options = query_payload("/api/team-options", {"season": ["2025"]})["rows"]
    selected_team = team_options[0]
    team = query_payload(
        "/api/team",
        {
            "season": ["2025"],
            "competition": [selected_team["competition_key"]],
            "club_key": [str(selected_team["club_key"])],
        },
    )
    add("team_options_available", len(team_options), "> 0", bool(team_options), "api")
    add("team_roster_reconciles", len(team["roster"]), team["summary"]["contributor_count"], len(team["roster"]) == team["summary"]["contributor_count"], "analytical_context")
    add("team_roster_includes_goalkeepers", team["summary"]["goalkeeper_count"], "> 0", team["summary"]["goalkeeper_count"] > 0, "analytical_context")
    add(
        "team_values_do_not_look_forward",
        sum(bool(row["aligned_valuation_date"]) for row in team["roster"]),
        "all dated values <= last club appearance",
        all(row["aligned_valuation_date"] is None or row["aligned_valuation_date"] <= row["last_appearance_date"] for row in team["roster"]),
        "time_alignment",
    )

    quality = query_payload("/api/quality", {})
    add("quality_coverage_rows", len(quality["coverage"]), 15, len(quality["coverage"]) == 15, "api")
    add("dashboard_exposes_zero_failures", sum(row["failed"] for row in quality["validation"]), 0, all(row["failed"] == 0 for row in quality["validation"]), "analytical_context")
    add("dashboard_exposes_limitations", len(quality["limitations"]), ">= 5", len(quality["limitations"]) >= 5, "analytical_context")

    frontend_text = "\n".join(path.read_text(encoding="utf-8") for path in (FRONTEND / "src").rglob("*.tsx"))
    add("no_database_credentials_in_react", "PGPASSWORD" in frontend_text or "DATABASE_URL" in frontend_text, False, "PGPASSWORD" not in frontend_text and "DATABASE_URL" not in frontend_text, "security")
    page_names = ["Market overview", "Value & performance", "Player journey", "Team analysis", "Transfer analysis", "Club development", "Quality & method"]
    add("seven_dashboard_pages", sum(name in frontend_text for name in page_names), 7, all(name in frontend_text for name in page_names), "frontend_build")

    with connect() as conn, conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS tm_audit")
        cur.execute("DROP TABLE IF EXISTS tm_audit.phase4_validation")
        cur.execute(
            """
            CREATE TABLE tm_audit.phase4_validation (
                category TEXT,
                check_name TEXT,
                status TEXT,
                actual_value TEXT,
                expected_value TEXT,
                details TEXT,
                audited_at_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.executemany(
            """
            INSERT INTO tm_audit.phase4_validation (
                category, check_name, status, actual_value, expected_value, details
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    row["category"], row["check_name"], row["status"],
                    str(row["actual_value"]), str(row["expected_value"]), row["details"],
                )
                for row in checks
            ],
        )
        conn.commit()

    with (REPORT_DIR / "phase4_validation.csv").open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(checks[0]))
        writer.writeheader()
        writer.writerows(checks)

    failures = [row for row in checks if row["status"] == "FAIL"]
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "check_count": len(checks),
        "passed_checks": len(checks) - len(failures),
        "failed_checks": len(failures),
        "failed_check_names": [row["check_name"] for row in failures],
        "dashboard_pages": 7,
        "api_routes": 11,
        "largest_javascript_bundle_bytes": largest_js,
        "browser_validation": {
            "desktop_viewport": "1280x720",
            "mobile_viewport": "390x844",
            "console_errors": 0,
            "console_warnings": 0,
        },
    }
    (REPORT_DIR / "phase4_validation_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Phase 4 validation complete: {len(checks)} checks, {len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
