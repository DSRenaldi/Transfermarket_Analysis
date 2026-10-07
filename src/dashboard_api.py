"""Read-only JSON API and static server for the React analytics dashboard."""

from __future__ import annotations

import argparse
import json
import mimetypes
from datetime import date, datetime
from decimal import Decimal
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from psycopg.rows import dict_row

from db_connection import connect


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "frontend" / "dist"
ALLOWED_COMPETITIONS = {"GB1", "ES1", "IT1", "L1", "FR1"}
ALLOWED_SEASONS = {2023, 2024, 2025}
ALLOWED_POSITIONS = {"Defender", "Midfielder", "Forward"}
ALLOWED_FEE_STATUSES = {
    "numeric_fee",
    "recorded_zero_ambiguous",
    "unknown_or_undisclosed",
}
COMPETITION_LABELS = {
    "GB1": "Premier League",
    "ES1": "LaLiga",
    "IT1": "Serie A",
    "L1": "Bundesliga",
    "FR1": "Ligue 1",
}


def label_competitions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        key = row.get("competition_key")
        if key in COMPETITION_LABELS:
            row["competition_name"] = COMPETITION_LABELS[key]
    return rows


def json_safe(value: Any) -> Any:
    if isinstance(value, str) and any(marker in value for marker in ("Ã", "Â", "â")):
        try:
            return value.encode("windows-1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def first(params: dict[str, list[str]], name: str) -> str | None:
    values = params.get(name)
    return values[0].strip() if values and values[0].strip() else None


def validated_filters(params: dict[str, list[str]]) -> dict[str, Any]:
    competition = first(params, "competition")
    if competition and competition not in ALLOWED_COMPETITIONS:
        raise ValueError("Unsupported competition filter")
    season_text = first(params, "season")
    season = int(season_text) if season_text else None
    if season is not None and season not in ALLOWED_SEASONS:
        raise ValueError("Unsupported season filter")
    position = first(params, "position")
    if position and position not in ALLOWED_POSITIONS:
        raise ValueError("Unsupported position filter")
    return {"competition": competition, "season": season, "position": position}


def filter_clause(
    filters: dict[str, Any], alias: str = "v"
) -> tuple[str, list[Any]]:
    conditions: list[str] = []
    values: list[Any] = []
    for key, column in (
        ("competition", "competition_key"),
        ("season", "season_key"),
        ("position", "position_group"),
    ):
        if filters[key] is not None:
            conditions.append(f"{alias}.{column} = %s")
            values.append(filters[key])
    return (" AND ".join(conditions) if conditions else "TRUE", values)


def fetch_all(cur, query: str, values: list[Any] | tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(query, values)
    return [json_safe(row) for row in cur.fetchall()]


def overview_payload(cur, params: dict[str, list[str]]) -> dict[str, Any]:
    filters = validated_filters(params)
    where, values = filter_clause(filters)
    summary = fetch_all(
        cur,
        f"""
        SELECT COUNT(*) AS player_seasons,
               COUNT(DISTINCT v.player_key) AS unique_players,
               SUM(v.season_end_market_value_eur)::BIGINT AS total_market_value_eur,
               PERCENTILE_CONT(0.5) WITHIN GROUP (
                 ORDER BY v.season_end_market_value_eur
               )::NUMERIC(18,2) AS median_market_value_eur,
               ROUND(AVG(v.value_efficiency_score), 3) AS average_efficiency_score,
               MIN(v.season_end_valuation_date) AS earliest_valuation_date,
               MAX(v.season_end_valuation_date) AS latest_valuation_date
        FROM tm_analysis.fact_value_efficiency v
        WHERE {where}
        """,
        values,
    )[0]
    by_position = fetch_all(
        cur,
        f"""
        SELECT v.position_group, COUNT(*) AS player_seasons,
               SUM(v.season_end_market_value_eur)::BIGINT AS total_market_value_eur,
               PERCENTILE_CONT(0.5) WITHIN GROUP (
                 ORDER BY v.season_end_market_value_eur
               )::NUMERIC(18,2) AS median_market_value_eur,
               ROUND(AVG(v.performance_z_score), 3) AS average_performance_z
        FROM tm_analysis.fact_value_efficiency v
        WHERE {where}
        GROUP BY v.position_group
        ORDER BY v.position_group
        """,
        values,
    )
    by_competition = label_competitions(fetch_all(
        cur,
        f"""
        SELECT v.competition_key, c.competition_name,
               COUNT(*) AS player_seasons,
               SUM(v.season_end_market_value_eur)::BIGINT AS total_market_value_eur,
               PERCENTILE_CONT(0.5) WITHIN GROUP (
                 ORDER BY v.season_end_market_value_eur
               )::NUMERIC(18,2) AS median_market_value_eur
        FROM tm_analysis.fact_value_efficiency v
        JOIN tm_analytics.dim_competition c USING (competition_key)
        WHERE {where}
        GROUP BY v.competition_key, c.competition_name
        ORDER BY total_market_value_eur DESC
        """,
        values,
    ))
    by_age = fetch_all(
        cur,
        f"""
        SELECT v.age_band, a.age_band_order, COUNT(*) AS player_seasons,
               PERCENTILE_CONT(0.5) WITHIN GROUP (
                 ORDER BY v.season_end_market_value_eur
               )::NUMERIC(18,2) AS median_market_value_eur,
               ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                 ORDER BY v.value_efficiency_score
               )::NUMERIC, 3) AS median_efficiency_score
        FROM tm_analysis.fact_value_efficiency v
        JOIN tm_analysis.age_band_definition a USING (age_band)
        WHERE {where}
        GROUP BY v.age_band, a.age_band_order
        ORDER BY a.age_band_order
        """,
        values,
    )
    return {
        "filters": filters,
        "summary": summary,
        "byPosition": by_position,
        "byCompetition": by_competition,
        "byAge": by_age,
    }


def efficiency_payload(cur, params: dict[str, list[str]]) -> dict[str, Any]:
    filters = validated_filters(params)
    where, values = filter_clause(filters, "v")
    limit_text = first(params, "limit")
    limit = min(max(int(limit_text or "600"), 10), 2000)
    rows = label_competitions(fetch_all(
        cur,
        f"""
        SELECT v.player_key, p.player_name, v.competition_key,
               c.competition_name, v.season_key, v.position_group,
               v.sub_position, club.club_name AS primary_club_name,
               v.age_at_season_end, v.age_band, v.minutes_played,
               v.goals_per_90, v.assists_per_90,
               v.goal_contributions_per_90, v.performance_z_score,
               v.market_value_z_score, v.value_efficiency_score,
               v.value_efficiency_rank, v.value_efficiency_percentile,
               v.exploratory_efficiency_band, v.peer_group_size,
               v.season_end_market_value_eur,
               v.season_end_valuation_date,
               v.season_end_valuation_lag_days
        FROM tm_analysis.fact_value_efficiency v
        JOIN tm_analytics.dim_player p USING (player_key)
        JOIN tm_analytics.dim_competition c USING (competition_key)
        LEFT JOIN tm_analytics.dim_club club ON v.primary_club_key = club.club_key
        WHERE {where}
        ORDER BY v.value_efficiency_score DESC, v.player_key
        LIMIT %s
        """,
        [*values, limit],
    ))
    return {"filters": filters, "rows": rows, "returnedRows": len(rows)}


def players_payload(cur, params: dict[str, list[str]]) -> dict[str, Any]:
    query = (first(params, "query") or "").strip()
    if query:
        rows = fetch_all(
            cur,
            """
            SELECT DISTINCT p.player_key, p.player_name, p.position_group,
                   p.country_of_citizenship
            FROM tm_analytics.dim_player p
            JOIN tm_analysis.fact_player_season_kpi k USING (player_key)
            WHERE p.player_name ILIKE %s
            ORDER BY p.player_name
            LIMIT 30
            """,
            [f"%{query}%"],
        )
    else:
        rows = fetch_all(
            cur,
            """
            SELECT player_key, player_name, position_group, country_of_citizenship
            FROM (
              SELECT DISTINCT ON (v.player_key)
                     v.player_key, p.player_name, v.position_group,
                     p.country_of_citizenship, v.season_key,
                     v.value_efficiency_score
              FROM tm_analysis.fact_value_efficiency v
              JOIN tm_analytics.dim_player p USING (player_key)
              ORDER BY v.player_key, v.season_key DESC, v.value_efficiency_score DESC
            ) latest
            ORDER BY value_efficiency_score DESC, player_name
            LIMIT 30
            """,
        )
    return {"query": query, "rows": rows}


def player_payload(cur, params: dict[str, list[str]]) -> dict[str, Any]:
    player_text = first(params, "player_key")
    if not player_text or not player_text.isdigit():
        raise ValueError("player_key must be a positive integer")
    player_key = int(player_text)
    profile_rows = fetch_all(
        cur,
        """
        SELECT player_key, player_name, date_of_birth, country_of_citizenship,
               position_group, sub_position, foot, height_cm,
               height_quality_status
        FROM tm_analytics.dim_player
        WHERE player_key = %s
        """,
        [player_key],
    )
    if not profile_rows:
        raise LookupError("Player not found")
    seasons = label_competitions(fetch_all(
        cur,
        """
        SELECT k.season_key, k.competition_key, c.competition_name,
               club.club_name AS primary_club_name, k.position_group,
               k.age_at_season_end, k.minutes_played, k.goals, k.assists,
               k.goal_contributions_per_90, k.season_end_market_value_eur,
               k.season_end_valuation_date, k.season_end_valuation_lag_days,
               v.performance_z_score, v.market_value_z_score,
               v.value_efficiency_score, v.value_efficiency_rank,
               v.peer_group_size
        FROM tm_analysis.fact_player_season_kpi k
        JOIN tm_analytics.dim_competition c USING (competition_key)
        LEFT JOIN tm_analytics.dim_club club ON k.primary_club_key = club.club_key
        LEFT JOIN tm_analysis.fact_value_efficiency v
          USING (player_key, competition_key, season_key)
        WHERE k.player_key = %s
        ORDER BY k.season_key, k.competition_key
        """,
        [player_key],
    ))
    valuations = fetch_all(
        cur,
        """
        SELECT valuation_date, market_value_eur, age_at_valuation,
               source_club_name_at_valuation AS club_name
        FROM tm_analytics.fact_player_valuation
        WHERE player_key = %s AND is_valid_valuation
        ORDER BY valuation_date
        """,
        [player_key],
    )
    transfers = fetch_all(
        cur,
        """
        SELECT transfer_date, source_from_club_name AS from_club_name,
               source_to_club_name AS to_club_name, fee_status,
               transfer_fee_eur, market_value_at_transfer_eur,
               matched_valuation_date
        FROM tm_analytics.fact_transfer
        WHERE player_key = %s AND is_historical_analysis_eligible
        ORDER BY transfer_date
        """,
        [player_key],
    )
    return {
        "profile": profile_rows[0],
        "seasons": seasons,
        "valuations": valuations,
        "transfers": transfers,
    }


def transfers_payload(cur, params: dict[str, list[str]]) -> dict[str, Any]:
    horizon = int(first(params, "horizon") or "12")
    if horizon not in {6, 12, 24}:
        raise ValueError("horizon must be 6, 12, or 24")
    fee_status = first(params, "fee_status")
    if fee_status and fee_status not in ALLOWED_FEE_STATUSES:
        raise ValueError("Unsupported fee status")
    summary_values: list[Any] = [horizon]
    summary_condition = "horizon_months = %s"
    if fee_status:
        summary_condition += " AND fee_status = %s"
        summary_values.append(fee_status)
    summary = fetch_all(
        cur,
        f"""
        SELECT horizon_months, fee_status, transfer_count,
               matured_transfer_count, value_change_eligible_count,
               value_change_coverage_pct, average_value_change_eur,
               median_value_change_eur, average_value_growth_pct,
               median_value_growth_pct
        FROM tm_analysis.agg_transfer_value_outcome
        WHERE {summary_condition}
        ORDER BY fee_status
        """,
        summary_values,
    )
    outcome_values: list[Any] = [horizon]
    outcome_condition = "o.horizon_months = %s AND o.is_value_change_eligible"
    if fee_status:
        outcome_condition += " AND o.fee_status = %s"
        outcome_values.append(fee_status)
    outcomes = fetch_all(
        cur,
        f"""
        SELECT o.transfer_key, o.player_key, p.player_name,
               o.transfer_date, o.horizon_months,
               fc.club_name AS from_club_name, tc.club_name AS to_club_name,
               o.fee_status, o.transfer_fee_eur,
               o.baseline_market_value_eur, o.post_market_value_eur,
               o.post_transfer_value_change_eur,
               o.post_transfer_value_growth_pct,
               o.post_valuation_date, o.post_valuation_target_lag_days,
               o.post_club_match_status
        FROM tm_analysis.fact_transfer_value_outcome o
        LEFT JOIN tm_analytics.dim_player p USING (player_key)
        LEFT JOIN tm_analytics.dim_club fc ON o.from_club_key = fc.club_key
        LEFT JOIN tm_analytics.dim_club tc ON o.to_club_key = tc.club_key
        WHERE {outcome_condition}
        ORDER BY o.post_transfer_value_change_eur DESC NULLS LAST
        LIMIT 40
        """,
        outcome_values,
    )
    return {"horizon": horizon, "feeStatus": fee_status, "summary": summary, "outcomes": outcomes}


def clubs_payload(cur, params: dict[str, list[str]]) -> dict[str, Any]:
    filters = validated_filters(params)
    conditions = ["d.has_consecutive_value_comparison", "d.season_end_club_key IS NOT NULL"]
    values: list[Any] = []
    if filters["competition"]:
        conditions.append("d.competition_key = %s")
        values.append(filters["competition"])
    if filters["season"]:
        conditions.append("d.season_key = %s")
        values.append(filters["season"])
    if filters["position"]:
        conditions.append("d.position_group = %s")
        values.append(filters["position"])
    where = " AND ".join(conditions)
    rows = fetch_all(
        cur,
        f"""
        SELECT d.season_end_club_key AS club_key, c.club_name,
               COUNT(*) AS player_comparisons,
               SUM(d.season_value_change_eur)::BIGINT AS total_value_change_eur,
               PERCENTILE_CONT(0.5) WITHIN GROUP (
                 ORDER BY d.season_value_change_eur
               )::NUMERIC(18,2) AS median_value_change_eur,
               PERCENTILE_CONT(0.5) WITHIN GROUP (
                 ORDER BY d.season_value_growth_pct
               )::NUMERIC(18,2) AS median_value_growth_pct,
               COUNT(*) FILTER (WHERE d.season_value_change_eur > 0) AS players_with_value_gain
        FROM tm_analysis.fact_player_value_development d
        JOIN tm_analytics.dim_club c ON d.season_end_club_key = c.club_key
        WHERE {where}
        GROUP BY d.season_end_club_key, c.club_name
        HAVING COUNT(*) >= 10
        ORDER BY median_value_change_eur DESC, player_comparisons DESC
        LIMIT 60
        """,
        values,
    )
    return {
        "filters": filters,
        "minimumComparisons": 10,
        "rows": rows,
        "interpretation": "Association with the season-end club; not proof that the club caused value change.",
    }


def team_options_payload(cur, params: dict[str, list[str]]) -> dict[str, Any]:
    filters = validated_filters(params)
    if filters["season"] is None:
        raise ValueError("season is required for team analysis")
    conditions = [
        "pcs.season_key = %s",
        "pcs.valid_appearances > 0",
        "pcs.competition_key IN ('GB1', 'ES1', 'IT1', 'L1', 'FR1')",
    ]
    values: list[Any] = [filters["season"]]
    if filters["competition"]:
        conditions.append("pcs.competition_key = %s")
        values.append(filters["competition"])
    rows = label_competitions(fetch_all(
        cur,
        f"""
        SELECT pcs.club_key, club.club_name, pcs.competition_key,
               comp.competition_name, COUNT(*) AS contributor_count
        FROM tm_analytics.fact_player_club_season pcs
        JOIN tm_analytics.dim_club club USING (club_key)
        JOIN tm_analytics.dim_competition comp USING (competition_key)
        WHERE {' AND '.join(conditions)}
        GROUP BY pcs.club_key, club.club_name, pcs.competition_key,
                 comp.competition_name
        ORDER BY comp.competition_name, club.club_name
        """,
        values,
    ))
    return {"filters": filters, "rows": rows}


def team_payload(cur, params: dict[str, list[str]]) -> dict[str, Any]:
    filters = validated_filters(params)
    if filters["season"] is None:
        raise ValueError("season is required for team analysis")
    if filters["competition"] is None:
        raise ValueError("competition is required for a team selection")
    club_text = first(params, "club_key")
    if not club_text or not club_text.isdigit() or int(club_text) <= 0:
        raise ValueError("club_key must be a positive integer")
    club_key = int(club_text)

    conditions = [
        "pcs.club_key = %s",
        "pcs.competition_key = %s",
        "pcs.season_key = %s",
        "pcs.valid_appearances > 0",
    ]
    values: list[Any] = [club_key, filters["competition"], filters["season"]]
    if filters["position"]:
        conditions.append("p.position_group = %s")
        values.append(filters["position"])
    where = " AND ".join(conditions)

    profile_rows = label_competitions(fetch_all(
        cur,
        """
        SELECT pcs.club_key, club.club_name, club.club_code,
               club.stadium_name, club.stadium_seats,
               pcs.competition_key, comp.competition_name,
               comp.country_name, pcs.season_key,
               MIN(pcs.first_appearance_date) AS first_appearance_date,
               MAX(pcs.last_appearance_date) AS last_appearance_date,
               COUNT(*) AS contributor_count
        FROM tm_analytics.fact_player_club_season pcs
        JOIN tm_analytics.dim_club club USING (club_key)
        JOIN tm_analytics.dim_competition comp USING (competition_key)
        WHERE pcs.club_key = %s
          AND pcs.competition_key = %s
          AND pcs.season_key = %s
          AND pcs.valid_appearances > 0
        GROUP BY pcs.club_key, club.club_name, club.club_code,
                 club.stadium_name, club.stadium_seats,
                 pcs.competition_key, comp.competition_name,
                 comp.country_name, pcs.season_key
        """,
        [club_key, filters["competition"], filters["season"]],
    ))
    if not profile_rows:
        raise LookupError("Team was not found in the selected competition and season")

    roster = fetch_all(
        cur,
        f"""
        SELECT pcs.player_key, p.player_name, p.position_group,
               p.sub_position, p.country_of_citizenship,
               pcs.age_at_stint_end, pcs.valid_appearances AS appearances,
               pcs.starts, pcs.minutes_played, pcs.goals, pcs.assists,
               pcs.goal_contributions, pcs.goals_per_90,
               pcs.assists_per_90, pcs.goal_contributions_per_90,
               pcs.first_appearance_date, pcs.last_appearance_date,
               pcs.club_count_in_competition_season > 1 AS played_for_multiple_clubs,
               pcs.stint_end_market_value_eur AS aligned_market_value_eur,
               pcs.stint_end_valuation_date AS aligned_valuation_date,
               pcs.stint_end_valuation_lag_days AS valuation_lag_days,
               pcs.stint_end_valuation_match_status AS valuation_status,
               pcs.stint_end_market_value_eur > 0
                 AND pcs.stint_end_valuation_lag_days BETWEEN 0 AND 365
                 AS has_fresh_aligned_value,
               k.minutes_played AS season_minutes_played,
               k.score_eligibility_status,
               v.performance_z_score, v.value_efficiency_score,
               v.value_efficiency_rank, v.peer_group_size
        FROM tm_analytics.fact_player_club_season pcs
        JOIN tm_analytics.dim_player p USING (player_key)
        LEFT JOIN tm_analysis.fact_player_season_kpi k
          USING (player_key, competition_key, season_key)
        LEFT JOIN tm_analysis.fact_value_efficiency v
          USING (player_key, competition_key, season_key)
        WHERE {where}
        ORDER BY pcs.minutes_played DESC, p.player_name
        """,
        values,
    )

    summary = fetch_all(
        cur,
        f"""
        SELECT COUNT(*) AS contributor_count,
               COUNT(*) FILTER (WHERE p.position_group = 'Goalkeeper') AS goalkeeper_count,
               COUNT(*) FILTER (WHERE k.is_phase3_score_eligible) AS score_eligible_count,
               SUM(pcs.minutes_played)::BIGINT AS total_minutes,
               SUM(pcs.goals)::BIGINT AS total_goals,
               SUM(pcs.assists)::BIGINT AS total_assists,
               SUM(pcs.stint_end_market_value_eur) FILTER (
                 WHERE pcs.stint_end_market_value_eur > 0
                   AND pcs.stint_end_valuation_lag_days BETWEEN 0 AND 365
               )::BIGINT AS aligned_squad_value_eur,
               PERCENTILE_CONT(0.5) WITHIN GROUP (
                 ORDER BY pcs.stint_end_market_value_eur
               ) FILTER (
                 WHERE pcs.stint_end_market_value_eur > 0
                   AND pcs.stint_end_valuation_lag_days BETWEEN 0 AND 365
               )::NUMERIC(18,2) AS median_player_value_eur,
               ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                 ORDER BY pcs.age_at_stint_end
               ) FILTER (WHERE pcs.age_at_stint_end IS NOT NULL)::NUMERIC, 1) AS median_age,
               COUNT(*) FILTER (
                 WHERE pcs.stint_end_market_value_eur > 0
                   AND pcs.stint_end_valuation_lag_days BETWEEN 0 AND 365
               ) AS players_with_aligned_value,
               ROUND(COUNT(*) FILTER (
                 WHERE pcs.stint_end_market_value_eur > 0
                   AND pcs.stint_end_valuation_lag_days BETWEEN 0 AND 365
               )::NUMERIC / NULLIF(COUNT(*), 0) * 100, 1) AS valuation_coverage_pct,
               MIN(pcs.stint_end_valuation_date) FILTER (
                 WHERE pcs.stint_end_valuation_lag_days BETWEEN 0 AND 365
               ) AS earliest_valuation_date,
               MAX(pcs.stint_end_valuation_date) FILTER (
                 WHERE pcs.stint_end_valuation_lag_days BETWEEN 0 AND 365
               ) AS latest_valuation_date
        FROM tm_analytics.fact_player_club_season pcs
        JOIN tm_analytics.dim_player p USING (player_key)
        LEFT JOIN tm_analysis.fact_player_season_kpi k
          USING (player_key, competition_key, season_key)
        WHERE {where}
        """,
        values,
    )[0]

    by_position = fetch_all(
        cur,
        f"""
        SELECT p.position_group, COUNT(*) AS contributor_count,
               SUM(pcs.minutes_played)::BIGINT AS minutes_played,
               SUM(pcs.stint_end_market_value_eur) FILTER (
                 WHERE pcs.stint_end_market_value_eur > 0
                   AND pcs.stint_end_valuation_lag_days BETWEEN 0 AND 365
               )::BIGINT AS aligned_market_value_eur,
               ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                 ORDER BY pcs.age_at_stint_end
               ) FILTER (WHERE pcs.age_at_stint_end IS NOT NULL)::NUMERIC, 1) AS median_age
        FROM tm_analytics.fact_player_club_season pcs
        JOIN tm_analytics.dim_player p USING (player_key)
        WHERE {where}
        GROUP BY p.position_group
        ORDER BY CASE p.position_group
          WHEN 'Goalkeeper' THEN 1 WHEN 'Defender' THEN 2
          WHEN 'Midfielder' THEN 3 WHEN 'Forward' THEN 4 ELSE 5 END
        """,
        values,
    )

    by_age = fetch_all(
        cur,
        f"""
        SELECT CASE
                 WHEN pcs.age_at_stint_end IS NULL THEN 'Unknown'
                 WHEN pcs.age_at_stint_end < 20 THEN 'Under 20'
                 WHEN pcs.age_at_stint_end <= 22 THEN '20-22'
                 WHEN pcs.age_at_stint_end <= 25 THEN '23-25'
                 WHEN pcs.age_at_stint_end <= 28 THEN '26-28'
                 WHEN pcs.age_at_stint_end <= 31 THEN '29-31'
                 ELSE '32+'
               END AS age_band,
               CASE
                 WHEN pcs.age_at_stint_end IS NULL THEN 7
                 WHEN pcs.age_at_stint_end < 20 THEN 1
                 WHEN pcs.age_at_stint_end <= 22 THEN 2
                 WHEN pcs.age_at_stint_end <= 25 THEN 3
                 WHEN pcs.age_at_stint_end <= 28 THEN 4
                 WHEN pcs.age_at_stint_end <= 31 THEN 5
                 ELSE 6
               END AS age_band_order,
               COUNT(*) AS contributor_count,
               SUM(pcs.minutes_played)::BIGINT AS minutes_played
        FROM tm_analytics.fact_player_club_season pcs
        JOIN tm_analytics.dim_player p USING (player_key)
        WHERE {where}
        GROUP BY age_band, age_band_order
        ORDER BY age_band_order
        """,
        values,
    )

    benchmark_conditions = [
        "pcs.competition_key = %s",
        "pcs.season_key = %s",
        "pcs.valid_appearances > 0",
    ]
    benchmark_values: list[Any] = [filters["competition"], filters["season"]]
    if filters["position"]:
        benchmark_conditions.append("p.position_group = %s")
        benchmark_values.append(filters["position"])
    benchmark = fetch_all(
        cur,
        f"""
        WITH club_stats AS (
          SELECT pcs.club_key, COUNT(*) AS contributor_count,
                 SUM(pcs.minutes_played)::BIGINT AS total_minutes,
                 SUM(pcs.goals + pcs.assists)::BIGINT AS goal_contributions,
                 SUM(pcs.stint_end_market_value_eur) FILTER (
                   WHERE pcs.stint_end_market_value_eur > 0
                     AND pcs.stint_end_valuation_lag_days BETWEEN 0 AND 365
                 )::BIGINT AS aligned_squad_value_eur,
                 PERCENTILE_CONT(0.5) WITHIN GROUP (
                   ORDER BY pcs.stint_end_market_value_eur
                 ) FILTER (
                   WHERE pcs.stint_end_market_value_eur > 0
                     AND pcs.stint_end_valuation_lag_days BETWEEN 0 AND 365
                 )::NUMERIC(18,2) AS median_player_value_eur,
                 PERCENTILE_CONT(0.5) WITHIN GROUP (
                   ORDER BY pcs.age_at_stint_end
                 ) FILTER (WHERE pcs.age_at_stint_end IS NOT NULL)::NUMERIC(8,2) AS median_age
          FROM tm_analytics.fact_player_club_season pcs
          JOIN tm_analytics.dim_player p USING (player_key)
          WHERE {' AND '.join(benchmark_conditions)}
          GROUP BY pcs.club_key
        ), competition_benchmark AS (
          SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY contributor_count)::NUMERIC(12,2) AS competition_median_contributors,
                 PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total_minutes)::NUMERIC(18,2) AS competition_median_minutes,
                 PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY goal_contributions)::NUMERIC(18,2) AS competition_median_goal_contributions,
                 PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY aligned_squad_value_eur)::NUMERIC(18,2) AS competition_median_squad_value_eur,
                 PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY median_player_value_eur)::NUMERIC(18,2) AS competition_median_player_value_eur,
                 PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY median_age)::NUMERIC(8,2) AS competition_median_age,
                 COUNT(*) AS competition_club_count
          FROM club_stats
        )
        SELECT s.*, b.*
        FROM club_stats s CROSS JOIN competition_benchmark b
        WHERE s.club_key = %s
        """,
        [*benchmark_values, club_key],
    )[0]

    return {
        "filters": filters,
        "profile": profile_rows[0],
        "summary": summary,
        "byPosition": by_position,
        "byAge": by_age,
        "benchmark": benchmark,
        "roster": roster,
        "definitions": {
            "roster": "Players with at least one valid appearance for the selected club, competition, and season.",
            "value": "Latest positive player valuation on or before the player's last appearance for this club; totals use valuations no more than 365 days old.",
            "score": "Performance and value-efficiency scores use the full player-season and are shown only when the established score eligibility rules are met.",
        },
    }


def quality_payload(cur, params: dict[str, list[str]]) -> dict[str, Any]:
    snapshots = fetch_all(
        cur,
        """
        SELECT source_table, min_business_date, max_business_date, row_count
        FROM tm_analytics.source_snapshot
        ORDER BY source_table
        """,
    )
    coverage = fetch_all(
        cur,
        """
        SELECT competition_key, season_key, game_count, games_with_appearances,
               appearance_game_coverage_pct, appearance_coverage_status
        FROM tm_analytics.dim_competition_season
        WHERE is_v1_scope
        ORDER BY season_key, competition_key
        """,
    )
    validation = fetch_all(
        cur,
        """
        SELECT 'Phase 2' AS phase,
               COUNT(*) AS checks,
               COUNT(*) FILTER (WHERE status = 'PASS') AS passed,
               COUNT(*) FILTER (WHERE status = 'FAIL') AS failed,
               MAX(audited_at_utc) AS audited_at_utc
        FROM tm_audit.phase2_validation
        UNION ALL
        SELECT 'Phase 3', COUNT(*),
               COUNT(*) FILTER (WHERE status = 'PASS'),
               COUNT(*) FILTER (WHERE status = 'FAIL'),
               MAX(audited_at_utc)
        FROM tm_audit.phase3_validation
        ORDER BY phase
        """,
    )
    parameters = fetch_all(
        cur,
        """
        SELECT methodology_version, minimum_minutes,
               maximum_season_valuation_lag_days,
               minimum_peer_group_size, winsor_lower_percentile,
               winsor_upper_percentile, maximum_transfer_target_lag_days,
               transfer_horizons_months, notes
        FROM tm_analysis.methodology_parameters
        """,
    )[0]
    weights = fetch_all(
        cur,
        """
        SELECT position_group, metric_name, metric_weight, direction, rationale
        FROM tm_analysis.position_metric_weight
        ORDER BY position_group, metric_name
        """,
    )
    return {
        "snapshots": snapshots,
        "coverage": coverage,
        "validation": validation,
        "parameters": parameters,
        "weights": weights,
        "limitations": [
            "Market value is a dated estimate, not a transfer price.",
            "Value Efficiency is exploratory and does not replace scouting, medical, salary, or contract review.",
            "Available performance metrics omit defensive actions, expected goals, tactical role, and goalkeeper-specific quality.",
            "Post-transfer value change is not causal impact or financial ROI.",
            "FR1 2025 has appearance data for 305 of 306 games.",
        ],
    }


def meta_payload(cur, params: dict[str, list[str]]) -> dict[str, Any]:
    competitions = label_competitions(fetch_all(
        cur,
        """
        SELECT competition_key, competition_name, country_name
        FROM tm_analytics.dim_competition
        WHERE is_v1_competition
        ORDER BY competition_name
        """,
    ))
    return {
        "project": "Football Player Value Analytics",
        "dashboard": "Recruitment Intelligence Room",
        "competitions": competitions,
        "seasons": sorted(ALLOWED_SEASONS),
        "positions": ["Defender", "Midfielder", "Forward"],
        "methodologyVersion": "v1.0",
    }


ROUTES = {
    "/api/meta": meta_payload,
    "/api/overview": overview_payload,
    "/api/efficiency": efficiency_payload,
    "/api/players": players_payload,
    "/api/player": player_payload,
    "/api/transfers": transfers_payload,
    "/api/clubs": clubs_payload,
    "/api/team-options": team_options_payload,
    "/api/team": team_payload,
    "/api/quality": quality_payload,
}


def query_payload(path: str, params: dict[str, list[str]]) -> dict[str, Any]:
    if path == "/api/health":
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_setting('server_version')")
            database, version = cur.fetchone()
        return {"status": "ok", "database": database, "postgresqlVersion": version}
    handler = ROUTES.get(path)
    if not handler:
        raise LookupError("API route not found")
    with connect(row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute("SET LOCAL statement_timeout = '15s'")
        return handler(cur, params)


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "FootballAnalytics/1.0"

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(json_safe(payload), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:5173")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            # React cancels stale requests when filters change; the client no longer needs this response.
            return

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            try:
                self.send_json(query_payload(parsed.path, parse_qs(parsed.query)))
            except ValueError as error:
                self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            except LookupError as error:
                self.send_json({"error": str(error)}, HTTPStatus.NOT_FOUND)
            except Exception as error:  # Keep credentials and SQL details out of responses.
                print(f"API error on {parsed.path}: {type(error).__name__}: {error}")
                self.send_json(
                    {"error": "Dashboard query failed. Check the local API log."},
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            return
        self.serve_static(parsed.path)

    def serve_static(self, request_path: str) -> None:
        if not DIST_DIR.exists():
            self.send_json(
                {"error": "React build not found. Run npm run build in frontend/."},
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return
        relative = request_path.lstrip("/") or "index.html"
        target = (DIST_DIR / relative).resolve()
        dist_resolved = DIST_DIR.resolve()
        if dist_resolved not in target.parents and target != dist_resolved:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not target.is_file():
            target = DIST_DIR / "index.html"
        body = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache" if target.name == "index.html" else "public, max-age=3600")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"Dashboard available at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
