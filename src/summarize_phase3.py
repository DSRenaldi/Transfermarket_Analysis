"""Generate a reproducible, non-causal Phase 3 analytical summary."""

from __future__ import annotations

from pathlib import Path

from db_connection import connect


REPORT_PATH = Path("reports/analysis/phase3-analysis.md")


def markdown_table(headers: list[str], rows: list[tuple[object, ...]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join("" if value is None else str(value) for value in row)
            + " |"
        )
    return "\n".join(lines)


def main() -> int:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS scored_player_seasons,
                   COUNT(DISTINCT (competition_key, season_key, position_group)) AS peer_groups,
                   MIN(peer_group_size) AS minimum_peer_size,
                   MAX(peer_group_size) AS maximum_peer_size,
                   COUNT(*) FILTER (WHERE exploratory_efficiency_band = 'high_relative_efficiency') AS high_efficiency_rows
            FROM tm_analysis.fact_value_efficiency
            """
        )
        scored, peer_groups, min_peer, max_peer, high_rows = cur.fetchone()

        cur.execute(
            """
            SELECT ROUND(MIN(spearman_performance_value_correlation), 4),
                   ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                     ORDER BY spearman_performance_value_correlation
                   )::NUMERIC, 4),
                   ROUND(MAX(spearman_performance_value_correlation), 4),
                   ROUND(MIN(top_10_value_concentration_pct), 2),
                   ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                     ORDER BY top_10_value_concentration_pct
                   )::NUMERIC, 2),
                   ROUND(MAX(top_10_value_concentration_pct), 2)
            FROM tm_analysis.agg_peer_group_benchmark
            """
        )
        corr_min, corr_median, corr_max, concentration_min, concentration_median, concentration_max = cur.fetchone()

        cur.execute(
            """
            SELECT k.position_group, k.age_band, a.age_band_order,
                   COUNT(*) AS player_seasons,
                   ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                     ORDER BY k.season_end_market_value_eur
                   )::NUMERIC, 0) AS median_market_value_eur,
                   ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                     ORDER BY k.value_efficiency_score
                   )::NUMERIC, 3) AS median_efficiency_score
            FROM tm_analysis.fact_value_efficiency k
            JOIN tm_analysis.age_band_definition a ON k.age_band = a.age_band
            GROUP BY k.position_group, k.age_band, a.age_band_order
            ORDER BY k.position_group, a.age_band_order
            """
        )
        age_rows = [
            (position, age_band, count, median_value, median_efficiency)
            for position, age_band, _, count, median_value, median_efficiency in cur.fetchall()
        ]

        cur.execute(
            """
            SELECT position_group, age_band,
                   COUNT(*) AS comparisons,
                   ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                     ORDER BY season_value_change_eur
                   )::NUMERIC, 0) AS median_value_change_eur,
                   ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                     ORDER BY season_value_growth_pct
                   )::NUMERIC, 2) AS median_value_growth_pct
            FROM tm_analysis.fact_player_value_development
            WHERE has_consecutive_value_comparison
            GROUP BY position_group, age_band
            ORDER BY position_group,
                     CASE age_band
                       WHEN 'Under 20' THEN 1 WHEN '20-22' THEN 2
                       WHEN '23-25' THEN 3 WHEN '26-28' THEN 4
                       WHEN '29-31' THEN 5 WHEN '32+' THEN 6 ELSE 7
                     END
            """
        )
        development_rows = cur.fetchall()

        cur.execute(
            """
            SELECT horizon_months,
                   COUNT(*) AS transfer_rows,
                   COUNT(*) FILTER (WHERE is_horizon_matured) AS matured_rows,
                   COUNT(*) FILTER (WHERE is_value_change_eligible) AS eligible_rows,
                   ROUND(
                     COUNT(*) FILTER (WHERE is_value_change_eligible)::NUMERIC
                     / NULLIF(COUNT(*) FILTER (WHERE is_horizon_matured), 0) * 100,
                     2
                   ) AS coverage_of_matured_pct,
                   ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                     ORDER BY post_transfer_value_change_eur
                   ) FILTER (WHERE is_value_change_eligible)::NUMERIC, 0) AS median_value_change_eur,
                   ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                     ORDER BY post_transfer_value_growth_pct
                   ) FILTER (WHERE is_value_change_eligible)::NUMERIC, 2) AS median_value_growth_pct
            FROM tm_analysis.fact_transfer_value_outcome
            GROUP BY horizon_months
            ORDER BY horizon_months
            """
        )
        transfer_rows = cur.fetchall()

    report = f"""# Phase 3 Analysis Summary

Generated from methodology version `v1.0` in PostgreSQL schema `tm_analysis`.

## Population and peer groups

- Scored player-seasons: **{scored:,}**.
- Peer groups (`season x competition x position_group`): **{peer_groups}**.
- Observed peer-group size: **{min_peer}-{max_peer}** players.
- Rows in the exploratory high-relative-efficiency band: **{high_rows:,}**.
- Goalkeepers are excluded because goalkeeper-specific performance metrics are
  unavailable.

The Spearman association between performance score and market value ranges from
**{corr_min}** to **{corr_max}** across peer groups, with a median of
**{corr_median}**. This is an association, not evidence that performance causes
market value. The top ten players hold between **{concentration_min}%** and
**{concentration_max}%** of peer-group value; the median concentration is
**{concentration_median}%**.

## Market value by age and position

{markdown_table(
    ["Position", "Age band", "Player-seasons", "Median value (EUR)", "Median efficiency"],
    age_rows,
)}

These are cross-sectional player-season comparisons. Repeated observations of
the same player and differences among clubs, roles, and competitions prevent a
causal interpretation of the age pattern.

## Consecutive-season value development

{markdown_table(
    ["Position", "Age band", "Comparisons", "Median change (EUR)", "Median growth %"],
    development_rows,
)}

Only consecutive seasons with positive, time-aligned values no more than 365
days old are included. A change in estimated market value is not financial ROI.

## Post-transfer market-value coverage

{markdown_table(
    ["Horizon (months)", "Transfers", "Matured", "Eligible", "Coverage of matured %", "Median change (EUR)", "Median growth %"],
    transfer_rows,
)}

Post-transfer values use the latest valuation on or before each 6-, 12-, or
24-month target and require that valuation to be within 90 days of the target.
Results are subject to survivorship and valuation-coverage bias. They do not
establish transfer impact, sporting ROI, or financial ROI.

## Interpretation guardrails

- `Value Efficiency Score = Performance Z-Score - Market Value Z-Score` is an
  exploratory within-peer indicator, not an objective statement that a player
  is undervalued.
- Defender inputs are limited to observed minutes, start rate, discipline, and
  small goal/assist components; defensive actions are unavailable.
- Salary, contract detail, injury, tactical role, league strength, scouting,
  and medical evidence are not included.
- Rankings must always expose minutes, peer size, season, competition,
  valuation date, and valuation lag.
"""

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"Phase 3 analysis summary written to {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
