"""Validate Phase 3 KPI, scoring, cohort, and transfer-outcome models."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from db_connection import connect


REPORT_DIR = Path("reports/analysis")


def serialize(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


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
        if isinstance(actual, (int, float, Decimal)) and isinstance(
            expected, (int, float, Decimal)
        ):
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
        cur.execute(
            """
            SELECT minimum_minutes, maximum_season_valuation_lag_days,
                   minimum_peer_group_size, winsor_lower_percentile,
                   winsor_upper_percentile, maximum_transfer_target_lag_days,
                   transfer_horizons_months
            FROM tm_analysis.methodology_parameters
            WHERE methodology_version = 'v1.0'
            """
        )
        parameters = cur.fetchone()
        add_check("methodology", "methodology_v1_exists", parameters is not None, True, parameters is not None)
        if parameters:
            min_minutes, max_lag, min_peer, p_low, p_high, transfer_lag, horizons = parameters
            add_check("methodology", "minimum_minutes", min_minutes, 900, min_minutes == 900)
            add_check("methodology", "maximum_season_valuation_lag_days", max_lag, 365, max_lag == 365)
            add_check("methodology", "minimum_peer_group_size", min_peer, 30, min_peer == 30)
            add_check("methodology", "winsor_lower_percentile", p_low, Decimal("0.05"), p_low == Decimal("0.05"))
            add_check("methodology", "winsor_upper_percentile", p_high, Decimal("0.95"), p_high == Decimal("0.95"))
            add_check("methodology", "maximum_transfer_target_lag_days", transfer_lag, 90, transfer_lag == 90)
            add_check("methodology", "transfer_horizons", horizons, [6, 12, 24], horizons == [6, 12, 24])

        cur.execute(
            """
            SELECT position_group, COUNT(*) AS metric_count,
                   SUM(metric_weight) AS weight_sum
            FROM tm_analysis.position_metric_weight
            GROUP BY position_group
            ORDER BY position_group
            """
        )
        weight_rows = rows_as_dicts(cur)
        add_check("methodology", "position_weight_groups", len(weight_rows), 3, len(weight_rows) == 3)
        for row in weight_rows:
            add_check(
                "methodology",
                f"{row['position_group'].lower()}_metric_count",
                row["metric_count"],
                5,
                row["metric_count"] == 5,
            )
            add_check(
                "methodology",
                f"{row['position_group'].lower()}_weight_sum",
                row["weight_sum"],
                Decimal("1"),
                row["weight_sum"] == Decimal("1"),
            )

        cur.execute("SELECT COUNT(*) FROM tm_analytics.fact_player_season")
        phase2_rows = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM tm_analysis.fact_player_season_kpi")
        kpi_rows = cur.fetchone()[0]
        add_check("grain", "player_season_kpi_row_count", kpi_rows, phase2_rows, kpi_rows == phase2_rows)

        grain_queries = {
            "fact_player_season_kpi": "player_key, competition_key, season_key",
            "fact_player_value_development": "player_key, season_key",
            "fact_value_efficiency": "player_key, competition_key, season_key",
            "fact_transfer_value_outcome": "transfer_key, horizon_months",
            "agg_market_value_by_age": "competition_key, season_key, position_group, age_band",
            "agg_peer_group_benchmark": "competition_key, season_key, position_group",
            "agg_transfer_value_outcome": "horizon_months, fee_status",
        }
        for table, columns in grain_queries.items():
            cur.execute(
                f"""
                SELECT COUNT(*) FROM (
                  SELECT {columns}
                  FROM tm_analysis.{table}
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
            FROM tm_analysis.fact_player_season_kpi k
            JOIN tm_analytics.fact_player_season p
              USING (player_key, competition_key, season_key)
            WHERE k.minutes_played <> p.minutes_played
               OR k.goals <> p.goals
               OR k.assists <> p.assists
               OR k.season_end_market_value_eur <> p.season_end_market_value_eur
            """
        )
        kpi_reconciliation_failures = cur.fetchone()[0]
        add_check("reconciliation", "phase2_to_phase3_kpi_mismatches", kpi_reconciliation_failures, 0, kpi_reconciliation_failures == 0)

        cur.execute(
            """
            SELECT COUNT(*) FILTER (WHERE is_phase3_score_eligible) AS eligible,
                   COUNT(*) FILTER (WHERE score_eligibility_status = 'stale_valuation_over_365_days') AS stale,
                   COUNT(*) FILTER (WHERE age_at_season_end IS NULL AND is_phase3_score_eligible) AS eligible_missing_age
            FROM tm_analysis.fact_player_season_kpi
            """
        )
        eligible_count, stale_count, eligible_missing_age = cur.fetchone()
        add_check("eligibility", "phase3_score_eligible_rows", eligible_count, None, None)
        add_check("eligibility", "stale_valuation_exclusions", stale_count, 20, stale_count == 20)
        add_check(
            "eligibility",
            "eligible_rows_missing_age",
            eligible_missing_age,
            None,
            None,
            "Retained in the Unknown age band; age is not imputed.",
        )

        cur.execute("SELECT COUNT(*) FROM tm_analysis.fact_value_efficiency")
        score_count = cur.fetchone()[0]
        add_check("score", "score_rows_match_eligible_rows", score_count, eligible_count, score_count == eligible_count)

        cur.execute(
            """
            SELECT COUNT(*) AS peer_groups,
                   MIN(peer_group_size) AS minimum_peer_size,
                   MAX(peer_group_size) AS maximum_peer_size,
                   COUNT(*) FILTER (WHERE position_group = 'Goalkeeper') AS goalkeeper_rows,
                   COUNT(*) FILTER (WHERE minutes_played < 900) AS below_minutes,
                   COUNT(*) FILTER (WHERE season_end_valuation_lag_days > 365) AS stale_rows,
                   COUNT(*) FILTER (WHERE season_end_valuation_date > season_end_reference_date) AS future_valuation_rows
            FROM tm_analysis.fact_value_efficiency
            """
        )
        _, minimum_peer_size, maximum_peer_size, goalkeeper_rows, below_minutes, stale_rows, future_rows = cur.fetchone()
        cur.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT competition_key, season_key, position_group
              FROM tm_analysis.fact_value_efficiency
              GROUP BY competition_key, season_key, position_group
            ) peers
            """
        )
        peer_group_count = cur.fetchone()[0]
        add_check("score", "peer_group_count", peer_group_count, 45, peer_group_count == 45)
        add_check("score", "minimum_peer_group_size_observed", minimum_peer_size, 30, minimum_peer_size >= 30)
        add_check("score", "maximum_peer_group_size_observed", maximum_peer_size, None, None)
        add_check("score", "goalkeepers_in_score", goalkeeper_rows, 0, goalkeeper_rows == 0)
        add_check("score", "score_rows_below_900_minutes", below_minutes, 0, below_minutes == 0)
        add_check("score", "stale_values_in_score", stale_rows, 0, stale_rows == 0)
        add_check("score", "future_values_in_score", future_rows, 0, future_rows == 0)

        cur.execute(
            """
            SELECT MAX(ABS(mean_performance)) AS max_abs_mean_performance,
                   MAX(ABS(mean_market_value)) AS max_abs_mean_market_value,
                   MAX(ABS(sd_performance - 1)) AS max_performance_sd_deviation,
                   MAX(ABS(sd_market_value - 1)) AS max_market_value_sd_deviation
            FROM (
              SELECT competition_key, season_key, position_group,
                     AVG(performance_z_score) AS mean_performance,
                     AVG(market_value_z_score) AS mean_market_value,
                     STDDEV_SAMP(performance_z_score) AS sd_performance,
                     STDDEV_SAMP(market_value_z_score) AS sd_market_value
              FROM tm_analysis.fact_value_efficiency
              GROUP BY competition_key, season_key, position_group
            ) standardized
            """
        )
        max_mean_perf, max_mean_value, max_sd_perf, max_sd_value = cur.fetchone()
        tolerance = Decimal("0.00001")
        add_check("standardization", "maximum_absolute_performance_mean", max_mean_perf, tolerance, max_mean_perf <= tolerance)
        add_check("standardization", "maximum_absolute_market_value_mean", max_mean_value, tolerance, max_mean_value <= tolerance)
        add_check("standardization", "maximum_performance_sd_deviation", max_sd_perf, tolerance, max_sd_perf <= tolerance)
        add_check("standardization", "maximum_market_value_sd_deviation", max_sd_value, tolerance, max_sd_value <= tolerance)

        cur.execute(
            """
            SELECT COUNT(*)
            FROM tm_analysis.fact_value_efficiency
            WHERE ABS(value_efficiency_score - (performance_z_score - market_value_z_score)) > 0.000002
            """
        )
        score_formula_failures = cur.fetchone()[0]
        add_check("score", "value_efficiency_formula_failures", score_formula_failures, 0, score_formula_failures == 0)

        cur.execute(
            """
            SELECT COUNT(*) FILTER (WHERE value_efficiency_rank = 1) AS first_rank_rows,
                   COUNT(*) FILTER (WHERE exploratory_efficiency_band = 'high_relative_efficiency') AS high_efficiency_rows
            FROM tm_analysis.fact_value_efficiency
            """
        )
        rank_one_rows, high_efficiency_rows = cur.fetchone()
        add_check("score", "rank_one_rows", rank_one_rows, peer_group_count, rank_one_rows == peer_group_count)
        add_check("score", "high_relative_efficiency_rows", high_efficiency_rows, None, None)

        cur.execute("SELECT SUM(player_count) FROM tm_analysis.agg_market_value_by_age")
        age_aggregate_players = cur.fetchone()[0]
        add_check("age", "age_aggregate_reconciles_to_scores", age_aggregate_players, score_count, age_aggregate_players == score_count)

        cur.execute(
            """
            SELECT COUNT(*)
            FROM tm_analysis.fact_player_value_development
            WHERE NOT has_consecutive_value_comparison
              AND (season_value_change_eur IS NOT NULL OR season_value_growth_pct IS NOT NULL)
            """
        )
        invalid_development_changes = cur.fetchone()[0]
        add_check("age", "nonconsecutive_value_change_rows", invalid_development_changes, 0, invalid_development_changes == 0)

        cur.execute(
            """
            SELECT COUNT(*) AS development_rows,
                   COUNT(*) FILTER (WHERE has_consecutive_value_comparison) AS comparable_rows
            FROM tm_analysis.fact_player_value_development
            """
        )
        development_rows, comparable_development_rows = cur.fetchone()
        cur.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT player_key, season_key
              FROM tm_analysis.fact_player_season_kpi
              GROUP BY player_key, season_key
            ) player_seasons
            """
        )
        expected_development_rows = cur.fetchone()[0]
        add_check("age", "development_grain_row_count", development_rows, expected_development_rows, development_rows == expected_development_rows)
        add_check("age", "consecutive_value_comparison_rows", comparable_development_rows, None, None)

        cur.execute("SELECT COUNT(*) FROM tm_analytics.fact_transfer WHERE is_historical_analysis_eligible")
        historical_transfers = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM tm_analysis.fact_transfer_value_outcome")
        transfer_outcome_rows = cur.fetchone()[0]
        add_check("transfer", "transfer_outcome_rows", transfer_outcome_rows, historical_transfers * 3, transfer_outcome_rows == historical_transfers * 3)

        cur.execute(
            """
            SELECT COUNT(*) FILTER (
                     WHERE post_valuation_date IS NOT NULL
                       AND (post_valuation_date <= transfer_date OR post_valuation_date > target_date)
                   ) AS invalid_post_dates,
                   COUNT(*) FILTER (
                     WHERE is_value_change_eligible
                       AND (NOT is_horizon_matured
                         OR NOT has_eligible_baseline
                         OR NOT has_eligible_post_valuation)
                   ) AS invalid_eligible_rows,
                   COUNT(*) FILTER (WHERE is_value_change_eligible) AS eligible_outcomes
            FROM tm_analysis.fact_transfer_value_outcome
            """
        )
        invalid_post_dates, invalid_eligible_outcomes, eligible_outcomes = cur.fetchone()
        add_check("transfer", "invalid_post_valuation_dates", invalid_post_dates, 0, invalid_post_dates == 0)
        add_check("transfer", "invalid_value_change_eligible_rows", invalid_eligible_outcomes, 0, invalid_eligible_outcomes == 0)
        add_check("transfer", "eligible_transfer_value_outcomes", eligible_outcomes, None, None)

        cur.execute(
            """
            SELECT COUNT(*)
            FROM pg_constraint fk
            JOIN pg_class child ON child.oid = fk.conrelid
            JOIN pg_namespace child_ns ON child_ns.oid = child.relnamespace
            JOIN pg_class parent ON parent.oid = fk.confrelid
            JOIN pg_namespace parent_ns ON parent_ns.oid = parent.relnamespace
            WHERE fk.contype = 'f'
              AND child_ns.nspname = 'tm_analysis'
              AND child.relname LIKE 'fact_%'
              AND parent.relname LIKE 'fact_%'
            """
        )
        fact_to_fact_fks = cur.fetchone()[0]
        add_check("model_relationship", "fact_to_fact_foreign_keys", fact_to_fact_fks, 0, fact_to_fact_fks == 0)

        cur.execute(
            """
            SELECT b.*,
                   COUNT(*) FILTER (WHERE v.exploratory_efficiency_band = 'high_relative_efficiency') AS high_efficiency_players,
                   ROUND(MIN(v.value_efficiency_score), 4) AS minimum_efficiency_score,
                   ROUND(MAX(v.value_efficiency_score), 4) AS maximum_efficiency_score
            FROM tm_analysis.agg_peer_group_benchmark b
            JOIN tm_analysis.fact_value_efficiency v
              USING (competition_key, season_key, position_group)
            GROUP BY b.competition_key, b.season_key, b.position_group,
                     b.player_count, b.total_market_value_eur, b.average_market_value_eur,
                     b.median_market_value_eur, b.p25_market_value_eur,
                     b.p75_market_value_eur, b.top_10_value_concentration_pct,
                     b.average_goals_per_90, b.average_assists_per_90,
                     b.average_goal_contributions_per_90,
                     b.median_goal_contributions_per_90,
                     b.spearman_performance_value_correlation,
                     b.earliest_valuation_date, b.latest_valuation_date,
                     b.methodology_version
            ORDER BY b.season_key, b.competition_key, b.position_group
            """
        )
        peer_summary = rows_as_dicts(cur)

        cur.execute(
            """
            SELECT season_key, competition_key, position_group,
                   exploratory_efficiency_band, COUNT(*) AS player_count
            FROM tm_analysis.fact_value_efficiency
            GROUP BY season_key, competition_key, position_group, exploratory_efficiency_band
            ORDER BY season_key, competition_key, position_group, exploratory_efficiency_band
            """
        )
        score_band_summary = rows_as_dicts(cur)

        cur.execute(
            """
            SELECT *
            FROM tm_analysis.agg_market_value_by_age
            ORDER BY season_key, competition_key, position_group, age_band_order
            """
        )
        age_summary = rows_as_dicts(cur)

        cur.execute(
            """
            SELECT *
            FROM tm_analysis.agg_transfer_value_outcome
            ORDER BY horizon_months, fee_status
            """
        )
        transfer_summary = rows_as_dicts(cur)

        cur.execute(
            """
            SELECT * FROM (
              SELECT v.player_name, v.competition_name, v.season_key,
                     v.position_group, v.primary_club_name,
                     v.minutes_played, v.goals_per_90, v.assists_per_90,
                     v.season_end_market_value_eur, v.season_end_valuation_date,
                     v.season_end_valuation_lag_days, v.peer_group_size,
                     v.performance_z_score, v.market_value_z_score,
                     v.value_efficiency_score, v.value_efficiency_rank,
                     ROW_NUMBER() OVER (
                       PARTITION BY v.competition_key, v.season_key, v.position_group
                       ORDER BY v.value_efficiency_rank, v.player_key
                     ) AS export_order
              FROM tm_analysis.vw_value_efficiency_ranking v
            ) ranked
            WHERE export_order <= 10
            ORDER BY season_key, competition_name, position_group, value_efficiency_rank, player_name
            """
        )
        top_efficiency = rows_as_dicts(cur)

        cur.execute("CREATE SCHEMA IF NOT EXISTS tm_audit")
        cur.execute("DROP TABLE IF EXISTS tm_audit.phase3_validation")
        cur.execute(
            """
            CREATE TABLE tm_audit.phase3_validation (
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
            INSERT INTO tm_audit.phase3_validation (
                category, check_name, status, actual_value,
                expected_value, difference, details
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    row["category"], row["check_name"], row["status"],
                    serialize(row["actual_value"]), serialize(row["expected_value"]),
                    serialize(row["difference"]), row["details"],
                )
                for row in checks
            ],
        )
        conn.commit()

    write_csv(REPORT_DIR / "phase3_validation.csv", checks)
    write_csv(REPORT_DIR / "phase3_peer_group_summary.csv", peer_summary)
    write_csv(REPORT_DIR / "phase3_score_band_summary.csv", score_band_summary)
    write_csv(REPORT_DIR / "phase3_age_summary.csv", age_summary)
    write_csv(REPORT_DIR / "phase3_transfer_outcome_summary.csv", transfer_summary)
    write_csv(REPORT_DIR / "phase3_top_efficiency.csv", top_efficiency)

    failed = [row for row in checks if row["status"] == "FAIL"]
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "methodology_version": "v1.0",
        "check_count": len(checks),
        "passed_checks": sum(row["status"] == "PASS" for row in checks),
        "failed_checks": len(failed),
        "informational_checks": sum(row["status"] == "INFO" for row in checks),
        "score_eligible_player_seasons": score_count,
        "peer_group_count": peer_group_count,
        "minimum_peer_group_size": minimum_peer_size,
        "maximum_peer_group_size": maximum_peer_size,
        "high_relative_efficiency_rows": high_efficiency_rows,
        "player_season_development_rows": development_rows,
        "consecutive_value_comparison_rows": comparable_development_rows,
        "transfer_outcome_rows": transfer_outcome_rows,
        "eligible_transfer_value_outcomes": eligible_outcomes,
        "failed_check_names": [row["check_name"] for row in failed],
    }
    (REPORT_DIR / "phase3_validation_summary.json").write_text(
        json.dumps(
            {key: json_value(value) for key, value in summary.items()},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Phase 3 validation complete: {len(checks)} checks, {len(failed)} failures")
    if failed:
        for row in failed:
            print(
                f"FAIL {row['check_name']}: "
                f"actual={row['actual_value']} expected={row['expected_value']}"
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
