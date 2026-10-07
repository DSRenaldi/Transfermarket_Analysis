CREATE TABLE tm_analysis.fact_player_season_kpi AS
SELECT
    ps.player_key,
    ps.competition_key,
    ps.season_key,
    ps.primary_club_key,
    ps.season_end_club_key,
    ps.position_group,
    ps.sub_position,
    ps.age_at_season_end,
    CASE
        WHEN ps.age_at_season_end IS NULL THEN 'Unknown'
        WHEN ps.age_at_season_end < 20 THEN 'Under 20'
        WHEN ps.age_at_season_end <= 22 THEN '20-22'
        WHEN ps.age_at_season_end <= 25 THEN '23-25'
        WHEN ps.age_at_season_end <= 28 THEN '26-28'
        WHEN ps.age_at_season_end <= 31 THEN '29-31'
        ELSE '32+'
    END AS age_band,
    ps.appearance_rows,
    ps.appearances,
    ps.starts,
    CASE WHEN ps.appearances > 0 THEN ROUND(ps.starts::NUMERIC / ps.appearances, 6) END AS start_rate,
    ps.minutes_played,
    ps.goals,
    ps.assists,
    ps.goal_contributions,
    ps.yellow_cards,
    ps.red_cards,
    ps.goals_per_90,
    ps.assists_per_90,
    ps.goal_contributions_per_90,
    ps.minutes_per_goal_contribution,
    ps.cards_per_90,
    CASE WHEN ps.cards_per_90 IS NOT NULL THEN -ps.cards_per_90 END AS discipline_score,
    ps.season_end_reference_date,
    ps.season_end_valuation_key,
    ps.season_end_valuation_date,
    ps.season_end_market_value_eur,
    ps.season_end_valuation_lag_days,
    ps.season_end_valuation_match_status,
    peak.peak_market_value_to_season_end_eur,
    peak.peak_market_value_date,
    ps.appearance_game_coverage_pct,
    ps.appearance_coverage_status,
    CONCAT_WS('|', ps.season_key::TEXT, ps.competition_key, ps.position_group) AS peer_group_key,
    ps.is_outfield
        AND ps.minutes_played >= m.minimum_minutes
        AND ps.season_end_market_value_eur > 0
        AND ps.season_end_valuation_lag_days BETWEEN 0 AND m.maximum_season_valuation_lag_days
        AND ps.appearances > 0
        AND ps.goals_per_90 IS NOT NULL
        AND ps.assists_per_90 IS NOT NULL
        AND ps.cards_per_90 IS NOT NULL AS is_phase3_score_eligible,
    CASE
        WHEN NOT ps.is_outfield THEN 'goalkeeper_excluded'
        WHEN ps.minutes_played < m.minimum_minutes THEN 'below_minimum_minutes'
        WHEN ps.season_end_market_value_eur IS NULL THEN 'missing_market_value'
        WHEN ps.season_end_market_value_eur <= 0 THEN 'nonpositive_market_value'
        WHEN ps.season_end_valuation_lag_days IS NULL THEN 'missing_valuation_date'
        WHEN ps.season_end_valuation_lag_days > m.maximum_season_valuation_lag_days THEN 'stale_valuation_over_365_days'
        WHEN ps.appearances <= 0 THEN 'no_valid_appearances'
        WHEN ps.goals_per_90 IS NULL OR ps.assists_per_90 IS NULL OR ps.cards_per_90 IS NULL THEN 'missing_score_metric'
        ELSE 'eligible'
    END AS score_eligibility_status,
    m.methodology_version
FROM tm_analytics.fact_player_season ps
CROSS JOIN tm_analysis.methodology_parameters m
LEFT JOIN LATERAL (
    SELECT
        v.market_value_eur AS peak_market_value_to_season_end_eur,
        v.valuation_date AS peak_market_value_date
    FROM tm_analytics.fact_player_valuation v
    WHERE v.player_key = ps.player_key
      AND v.is_valid_valuation
      AND v.valuation_date <= ps.season_end_reference_date
    ORDER BY v.market_value_eur DESC, v.valuation_date ASC
    LIMIT 1
) peak ON TRUE;

ALTER TABLE tm_analysis.fact_player_season_kpi
    ADD CONSTRAINT pk_fact_player_season_kpi
        PRIMARY KEY (player_key, competition_key, season_key),
    ADD CONSTRAINT ck_phase3_valuation_not_after_reference
        CHECK (season_end_valuation_date IS NULL OR season_end_valuation_date <= season_end_reference_date);

CREATE INDEX ix_player_season_kpi_peer
    ON tm_analysis.fact_player_season_kpi (competition_key, season_key, position_group, is_phase3_score_eligible);
CREATE INDEX ix_player_season_kpi_player
    ON tm_analysis.fact_player_season_kpi (player_key, season_key);
CREATE INDEX ix_player_season_kpi_age
    ON tm_analysis.fact_player_season_kpi (age_band, position_group);

CREATE TABLE tm_analysis.fact_player_value_development AS
WITH representative AS (
    SELECT
        k.*,
        ROW_NUMBER() OVER (
            PARTITION BY k.player_key, k.season_key
            ORDER BY k.minutes_played DESC, k.competition_key
        ) AS season_row_order
    FROM tm_analysis.fact_player_season_kpi k
), sequenced AS (
    SELECT
        r.*,
        LAG(r.season_key) OVER player_history AS previous_season_key,
        LAG(r.competition_key) OVER player_history AS previous_competition_key,
        LAG(r.season_end_market_value_eur) OVER player_history AS previous_season_end_market_value_eur,
        LAG(r.season_end_valuation_date) OVER player_history AS previous_season_end_valuation_date,
        LAG(r.is_phase3_score_eligible) OVER player_history AS previous_season_is_fresh_eligible
    FROM representative r
    WHERE r.season_row_order = 1
    WINDOW player_history AS (PARTITION BY r.player_key ORDER BY r.season_key)
)
SELECT
    player_key,
    season_key,
    competition_key,
    primary_club_key,
    season_end_club_key,
    position_group,
    sub_position,
    age_at_season_end,
    age_band,
    minutes_played,
    season_end_reference_date,
    season_end_valuation_date,
    season_end_market_value_eur,
    season_end_valuation_lag_days,
    previous_season_key,
    previous_competition_key,
    previous_season_end_valuation_date,
    previous_season_end_market_value_eur,
    season_key - previous_season_key AS observed_season_gap,
    previous_season_key = season_key - 1
        AND is_phase3_score_eligible
        AND previous_season_is_fresh_eligible
        AND previous_season_end_market_value_eur > 0 AS has_consecutive_value_comparison,
    CASE
        WHEN previous_season_key = season_key - 1
         AND is_phase3_score_eligible
         AND previous_season_is_fresh_eligible
         AND previous_season_end_market_value_eur > 0
        THEN season_end_market_value_eur - previous_season_end_market_value_eur
    END AS season_value_change_eur,
    CASE
        WHEN previous_season_key = season_key - 1
         AND is_phase3_score_eligible
         AND previous_season_is_fresh_eligible
         AND previous_season_end_market_value_eur > 0
        THEN ROUND(
            (season_end_market_value_eur - previous_season_end_market_value_eur)::NUMERIC
            / previous_season_end_market_value_eur * 100,
            4
        )
    END AS season_value_growth_pct,
    is_phase3_score_eligible,
    methodology_version
FROM sequenced;

ALTER TABLE tm_analysis.fact_player_value_development
    ADD CONSTRAINT pk_fact_player_value_development PRIMARY KEY (player_key, season_key);

CREATE INDEX ix_player_value_development_age
    ON tm_analysis.fact_player_value_development (position_group, age_band, season_key);

CREATE TABLE tm_analysis.agg_market_value_by_age AS
SELECT
    k.competition_key,
    k.season_key,
    k.position_group,
    k.age_band,
    a.age_band_order,
    COUNT(*) AS player_count,
    SUM(k.season_end_market_value_eur)::BIGINT AS total_market_value_eur,
    ROUND(AVG(k.season_end_market_value_eur), 2) AS average_market_value_eur,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY k.season_end_market_value_eur)::NUMERIC(18,2) AS median_market_value_eur,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY k.season_end_market_value_eur)::NUMERIC(18,2) AS p25_market_value_eur,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY k.season_end_market_value_eur)::NUMERIC(18,2) AS p75_market_value_eur,
    ROUND(AVG(k.age_at_season_end), 2) AS average_age,
    MIN(k.season_end_valuation_date) AS earliest_valuation_date,
    MAX(k.season_end_valuation_date) AS latest_valuation_date
FROM tm_analysis.fact_player_season_kpi k
JOIN tm_analysis.age_band_definition a ON k.age_band = a.age_band
WHERE k.is_phase3_score_eligible
GROUP BY k.competition_key, k.season_key, k.position_group, k.age_band, a.age_band_order;

ALTER TABLE tm_analysis.agg_market_value_by_age
    ADD CONSTRAINT pk_agg_market_value_by_age
        PRIMARY KEY (competition_key, season_key, position_group, age_band);
