"""Profile Phase 2 model inputs needed for Phase 3 methodology decisions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from db_connection import connect


REPORT_PATH = Path("reports/analysis/phase3_input_profile.json")


def json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def rows_as_dicts(cur) -> list[dict[str, Any]]:
    columns = [column.name for column in cur.description]
    return [
        {name: json_value(value) for name, value in zip(columns, row)}
        for row in cur.fetchall()
    ]


def main() -> int:
    profile: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat()
    }

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS player_seasons,
                   COUNT(*) FILTER (WHERE is_outfield) AS outfield,
                   COUNT(*) FILTER (WHERE meets_minimum_minutes) AS minimum_minutes,
                   COUNT(*) FILTER (WHERE season_end_market_value_eur > 0) AS positive_value,
                   COUNT(*) FILTER (WHERE is_v1_value_analysis_eligible) AS phase2_eligible,
                   COUNT(*) FILTER (
                     WHERE is_v1_value_analysis_eligible
                       AND season_end_valuation_lag_days <= 365
                   ) AS phase3_fresh_value_eligible
            FROM tm_analytics.fact_player_season
            """
        )
        profile["eligibility_funnel"] = rows_as_dicts(cur)[0]

        cur.execute(
            """
            SELECT competition_key, season_key, position_group,
                   COUNT(*) AS eligible_players,
                   MIN(minutes_played) AS minimum_minutes,
                   MAX(minutes_played) AS maximum_minutes,
                   COUNT(*) FILTER (WHERE starts IS NULL) AS null_starts,
                   COUNT(*) FILTER (WHERE season_end_valuation_lag_days > 365) AS stale_values
            FROM tm_analytics.fact_player_season
            WHERE is_v1_value_analysis_eligible
            GROUP BY competition_key, season_key, position_group
            ORDER BY season_key, competition_key, position_group
            """
        )
        profile["peer_groups"] = rows_as_dicts(cur)

        cur.execute(
            """
            SELECT position_group,
                   COUNT(*) FILTER (
                     WHERE is_v1_value_analysis_eligible
                       AND season_end_valuation_lag_days <= 365
                   ) AS eligible_players,
                   ROUND(AVG(goals_per_90) FILTER (
                     WHERE is_v1_value_analysis_eligible
                       AND season_end_valuation_lag_days <= 365
                   ), 4) AS average_goals_per_90,
                   ROUND(AVG(assists_per_90) FILTER (
                     WHERE is_v1_value_analysis_eligible
                       AND season_end_valuation_lag_days <= 365
                   ), 4) AS average_assists_per_90,
                   ROUND(AVG(cards_per_90) FILTER (
                     WHERE is_v1_value_analysis_eligible
                       AND season_end_valuation_lag_days <= 365
                   ), 4) AS average_cards_per_90
            FROM tm_analytics.fact_player_season
            GROUP BY position_group
            ORDER BY position_group
            """
        )
        profile["position_metric_profile"] = rows_as_dicts(cur)

        cur.execute(
            """
            SELECT COUNT(*) AS player_season_duplicates_across_competitions
            FROM (
              SELECT player_key, season_key
              FROM tm_analytics.fact_player_season
              GROUP BY player_key, season_key
              HAVING COUNT(*) > 1
            ) duplicated
            """
        )
        profile["cross_competition_player_seasons"] = rows_as_dicts(cur)[0]

        cur.execute(
            """
            WITH horizons(months) AS (VALUES (6), (12), (24))
            SELECT h.months AS horizon_months,
                   COUNT(*) FILTER (WHERE t.is_historical_analysis_eligible) AS historical_transfers,
                   COUNT(*) FILTER (
                     WHERE t.is_historical_analysis_eligible
                       AND t.player_key IS NOT NULL
                       AND t.market_value_at_transfer_eur > 0
                       AND t.transfer_date + MAKE_INTERVAL(months => h.months)
                           <= (SELECT max_business_date FROM tm_analytics.source_snapshot
                               WHERE source_table = 'player_valuations')
                   ) AS baseline_and_matured
            FROM tm_analytics.fact_transfer t
            CROSS JOIN horizons h
            GROUP BY h.months
            ORDER BY h.months
            """
        )
        profile["transfer_horizon_candidates"] = rows_as_dicts(cur)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Phase 3 input profile written to {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
