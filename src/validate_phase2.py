"""Validate Phase 2 grains, reconciliations, and temporal alignment."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from psycopg import sql

from db_connection import connect


REPORT_DIR = Path("reports/data_model")
ANALYTICS_SCHEMA = "tm_analytics"


def serialize(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def rows_as_dicts(cur) -> list[dict[str, Any]]:
    columns = [column.name for column in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: serialize(value) for key, value in row.items()})


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []

    def add_check(
        category: str,
        name: str,
        actual: Any,
        expected: Any = None,
        passed: bool | None = None,
        details: str = "",
    ) -> None:
        status = "INFO" if passed is None else ("PASS" if passed else "FAIL")
        difference = None
        if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            difference = actual - expected
        checks.append(
            {
                "category": category,
                "check_name": name,
                "status": status,
                "actual_value": actual,
                "expected_value": expected,
                "difference": difference,
                "details": details,
            }
        )

    with connect() as conn, conn.cursor() as cur:
        row_count_pairs = (
            ("dim_player", "tm_raw", "players"),
            ("dim_club", "tm_raw", "clubs"),
            ("dim_game", "tm_raw", "games"),
            ("fact_player_appearance", "tm_raw", "appearances"),
            ("fact_player_valuation", "tm_raw", "player_valuations"),
            ("fact_transfer", "tm_raw", "transfers"),
        )
        for model_table, source_schema, source_table in row_count_pairs:
            cur.execute(
                sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                    sql.Identifier(ANALYTICS_SCHEMA), sql.Identifier(model_table)
                )
            )
            modeled = cur.fetchone()[0]
            cur.execute(
                sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                    sql.Identifier(source_schema), sql.Identifier(source_table)
                )
            )
            source = cur.fetchone()[0]
            add_check(
                "row_count",
                f"{model_table}_matches_{source_table}",
                modeled,
                source,
                modeled == source,
            )

        cur.execute("SELECT COUNT(*) FROM tm_analytics.dim_competition")
        competition_count = cur.fetchone()[0]
        cur.execute(
            """
            SELECT COUNT(*)
            FROM (
              SELECT competition_id FROM tm_raw.competitions
              UNION
              SELECT competition_id FROM tm_ref.competition_id_overrides
            ) competitions
            """
        )
        expected_competitions = cur.fetchone()[0]
        add_check(
            "row_count",
            "dim_competition_includes_overrides",
            competition_count,
            expected_competitions,
            competition_count == expected_competitions,
        )

        grain_queries = {
            "fact_player_appearance": "appearance_key",
            "fact_player_valuation": "source_player_id, valuation_date",
            "fact_transfer": "transfer_key",
            "fact_player_club_season": "player_key, club_key, competition_key, season_key",
            "fact_player_season": "player_key, competition_key, season_key",
        }
        for table, columns in grain_queries.items():
            cur.execute(
                f"""
                SELECT COUNT(*)
                FROM (
                  SELECT {columns}
                  FROM tm_analytics.{table}
                  GROUP BY {columns}
                  HAVING COUNT(*) > 1
                ) duplicate_grains
                """
            )
            duplicates = cur.fetchone()[0]
            add_check("grain", f"{table}_duplicate_grains", duplicates, 0, duplicates == 0)

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
        fact_to_fact_fks = cur.fetchone()[0]
        add_check(
            "model_relationship",
            "fact_to_fact_foreign_keys",
            fact_to_fact_fks,
            0,
            fact_to_fact_fks == 0,
            "Valuation keys in other facts are lineage attributes, not BI relationships.",
        )

        cur.execute(
            """
            SELECT COUNT(*) AS appearance_rows,
                   SUM(minutes_played::numeric)::bigint AS minutes,
                   SUM(goals::integer)::bigint AS goals,
                   SUM(assists::integer)::bigint AS assists
            FROM tm_raw.appearances a
            JOIN tm_raw.games g ON a.game_id = g.game_id
            WHERE g.competition_id = ANY(ARRAY['GB1','ES1','IT1','L1','FR1'])
              AND g.season::integer = ANY(ARRAY[2023,2024,2025])
            """
        )
        raw_v1 = dict(zip(("appearance_rows", "minutes", "goals", "assists"), cur.fetchone()))

        cur.execute(
            """
            SELECT COUNT(*) AS appearance_rows,
                   SUM(minutes_played)::bigint AS minutes,
                   SUM(goals)::bigint AS goals,
                   SUM(assists)::bigint AS assists
            FROM tm_analytics.fact_player_appearance
            WHERE is_v1_scope AND is_valid_for_aggregation
            """
        )
        fact_v1 = dict(zip(("appearance_rows", "minutes", "goals", "assists"), cur.fetchone()))

        cur.execute(
            """
            SELECT SUM(appearance_rows)::bigint AS appearance_rows,
                   SUM(minutes_played)::bigint AS minutes,
                   SUM(goals)::bigint AS goals,
                   SUM(assists)::bigint AS assists
            FROM tm_analytics.fact_player_season
            """
        )
        season_v1 = dict(zip(("appearance_rows", "minutes", "goals", "assists"), cur.fetchone()))

        for metric in ("appearance_rows", "minutes", "goals", "assists"):
            add_check(
                "reconciliation",
                f"v1_appearance_{metric}",
                fact_v1[metric],
                raw_v1[metric],
                fact_v1[metric] == raw_v1[metric],
            )
            add_check(
                "reconciliation",
                f"v1_player_season_{metric}",
                season_v1[metric],
                fact_v1[metric],
                season_v1[metric] == fact_v1[metric],
            )

        cur.execute(
            """
            SELECT COUNT(*) FILTER (WHERE player_key IS NULL OR club_key IS NULL) AS missing_dimensions,
                   COUNT(*) FILTER (WHERE NOT is_valid_for_aggregation) AS invalid_rows,
                   COUNT(*) FILTER (WHERE lineup_match_status = 'missing') AS missing_lineups,
                   COUNT(*) FILTER (WHERE lineup_match_status = 'duplicate_conflict') AS duplicate_lineup_conflicts
            FROM tm_analytics.fact_player_appearance
            WHERE is_v1_scope
            """
        )
        missing_dimensions, invalid_rows, missing_lineups, duplicate_conflicts = cur.fetchone()
        add_check("v1_quality", "v1_missing_player_or_club_dimensions", missing_dimensions, 0, missing_dimensions == 0)
        add_check("v1_quality", "v1_invalid_appearance_rows", invalid_rows, 0, invalid_rows == 0)
        add_check("v1_quality", "v1_appearances_without_lineup", missing_lineups, None, None, "Starts remain null for these rows.")
        add_check("v1_quality", "v1_duplicate_lineup_conflicts", duplicate_conflicts, 0, duplicate_conflicts == 0)

        temporal_queries = {
            "transfer_valuation_after_transfer": "SELECT COUNT(*) FROM tm_analytics.fact_transfer WHERE matched_valuation_date > transfer_date",
            "club_season_valuation_after_reference": "SELECT COUNT(*) FROM tm_analytics.fact_player_club_season WHERE stint_end_valuation_date > stint_end_reference_date",
            "player_season_valuation_after_reference": "SELECT COUNT(*) FROM tm_analytics.fact_player_season WHERE season_end_valuation_date > season_end_reference_date",
        }
        for name, query in temporal_queries.items():
            cur.execute(query)
            violations = cur.fetchone()[0]
            add_check("time_alignment", name, violations, 0, violations == 0)

        cur.execute(
            """
            SELECT COUNT(*) AS competition_seasons,
                   COUNT(*) FILTER (WHERE appearance_coverage_status = 'FULL') AS full_coverage,
                   COUNT(*) FILTER (WHERE appearance_coverage_status = 'HIGH') AS high_coverage,
                   MIN(appearance_game_coverage_pct) AS minimum_coverage_pct
            FROM tm_analytics.dim_competition_season
            WHERE is_v1_scope
            """
        )
        competition_seasons, full_coverage, high_coverage, min_coverage = cur.fetchone()
        add_check("coverage", "v1_competition_season_count", competition_seasons, 15, competition_seasons == 15)
        add_check("coverage", "v1_full_coverage_competition_seasons", full_coverage, None, None)
        add_check("coverage", "v1_high_coverage_competition_seasons", high_coverage, None, None)
        add_check("coverage", "v1_minimum_game_appearance_coverage_pct", min_coverage, 99, min_coverage >= 99)

        cur.execute(
            """
            SELECT COUNT(*) AS player_seasons,
                   COUNT(*) FILTER (WHERE is_outfield) AS outfield_player_seasons,
                   COUNT(*) FILTER (WHERE meets_minimum_minutes) AS player_seasons_900_minutes,
                   COUNT(*) FILTER (WHERE season_end_market_value_eur > 0) AS player_seasons_with_value,
                   COUNT(*) FILTER (WHERE is_v1_value_analysis_eligible) AS analysis_eligible,
                   MAX(season_end_valuation_lag_days) AS max_valuation_lag_days
            FROM tm_analytics.fact_player_season
            """
        )
        player_season_profile = dict(
            zip(
                (
                    "player_seasons",
                    "outfield_player_seasons",
                    "player_seasons_900_minutes",
                    "player_seasons_with_value",
                    "analysis_eligible",
                    "max_valuation_lag_days",
                ),
                cur.fetchone(),
            )
        )
        for name, value in player_season_profile.items():
            add_check("player_season_profile", name, value, None, None)

        cur.execute(
            """
            SELECT COUNT(*) AS transfers,
                   COUNT(*) FILTER (WHERE is_after_analysis_cutoff) AS after_cutoff,
                   COUNT(*) FILTER (WHERE is_fee_analysis_eligible) AS positive_fee,
                   COUNT(*) FILTER (WHERE matched_valuation_key IS NOT NULL) AS with_prior_valuation,
                   COUNT(*) FILTER (
                     WHERE is_fee_analysis_eligible AND matched_valuation_key IS NOT NULL
                   ) AS fee_and_valuation_eligible
            FROM tm_analytics.fact_transfer
            """
        )
        transfer_profile = dict(
            zip(
                (
                    "transfers",
                    "after_cutoff",
                    "positive_fee",
                    "with_prior_valuation",
                    "fee_and_valuation_eligible",
                ),
                cur.fetchone(),
            )
        )
        for name, value in transfer_profile.items():
            add_check("transfer_profile", name, value, None, None)

        cur.execute(
            """
            SELECT competition_key, season_key, game_count, games_with_appearances,
                   appearance_game_coverage_pct, appearance_coverage_status
            FROM tm_analytics.dim_competition_season
            WHERE is_v1_scope
            ORDER BY season_key, competition_key
            """
        )
        coverage_rows = rows_as_dicts(cur)

        cur.execute(
            """
            SELECT competition_key, season_key,
                   COUNT(*) AS player_seasons,
                   COUNT(*) FILTER (WHERE is_outfield) AS outfield_player_seasons,
                   COUNT(*) FILTER (WHERE meets_minimum_minutes) AS player_seasons_900_minutes,
                   COUNT(*) FILTER (WHERE season_end_market_value_eur > 0) AS with_market_value,
                   COUNT(*) FILTER (WHERE is_v1_value_analysis_eligible) AS analysis_eligible,
                   ROUND(AVG(season_end_valuation_lag_days), 2) AS average_valuation_lag_days,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY season_end_valuation_lag_days) AS median_valuation_lag_days
            FROM tm_analytics.fact_player_season
            GROUP BY competition_key, season_key
            ORDER BY season_key, competition_key
            """
        )
        valuation_coverage_rows = rows_as_dicts(cur)

        cur.execute(
            """
            SELECT valuation_match_status, fee_status,
                   COUNT(*) AS transfer_rows,
                   COUNT(*) FILTER (WHERE is_historical_analysis_eligible) AS historical_rows
            FROM tm_analytics.fact_transfer
            GROUP BY valuation_match_status, fee_status
            ORDER BY transfer_rows DESC, valuation_match_status, fee_status
            """
        )
        transfer_coverage_rows = rows_as_dicts(cur)

        cur.execute("CREATE SCHEMA IF NOT EXISTS tm_audit")
        cur.execute("DROP TABLE IF EXISTS tm_audit.phase2_validation")
        cur.execute(
            """
            CREATE TABLE tm_audit.phase2_validation (
                category TEXT,
                check_name TEXT,
                status TEXT,
                actual_value TEXT,
                expected_value TEXT,
                difference TEXT,
                details TEXT,
                audited_at_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.executemany(
            """
            INSERT INTO tm_audit.phase2_validation (
                category, check_name, status, actual_value,
                expected_value, difference, details
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    row["category"],
                    row["check_name"],
                    row["status"],
                    serialize(row["actual_value"]),
                    serialize(row["expected_value"]),
                    serialize(row["difference"]),
                    row["details"],
                )
                for row in checks
            ],
        )
        conn.commit()

    write_csv(REPORT_DIR / "phase2_validation.csv", checks)
    write_csv(REPORT_DIR / "phase2_v1_coverage.csv", coverage_rows)
    write_csv(REPORT_DIR / "phase2_valuation_coverage.csv", valuation_coverage_rows)
    write_csv(REPORT_DIR / "phase2_transfer_coverage.csv", transfer_coverage_rows)

    failed = [row for row in checks if row["status"] == "FAIL"]
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "check_count": len(checks),
        "passed_checks": sum(row["status"] == "PASS" for row in checks),
        "failed_checks": len(failed),
        "informational_checks": sum(row["status"] == "INFO" for row in checks),
        "player_season_profile": player_season_profile,
        "transfer_profile": transfer_profile,
        "minimum_v1_game_appearance_coverage_pct": serialize(min_coverage),
        "failed_check_names": [row["check_name"] for row in failed],
    }
    (REPORT_DIR / "phase2_validation_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"Phase 2 validation complete: {len(checks)} checks, {len(failed)} failures")
    if failed:
        for row in failed:
            print(f"FAIL {row['check_name']}: actual={row['actual_value']} expected={row['expected_value']}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
