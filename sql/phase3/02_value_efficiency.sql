CREATE TABLE tm_analysis.fact_value_efficiency AS
WITH eligible AS (
    SELECT
        k.*,
        COUNT(*) OVER (
            PARTITION BY k.competition_key, k.season_key, k.position_group
        ) AS peer_group_size
    FROM tm_analysis.fact_player_season_kpi k
    WHERE k.is_phase3_score_eligible
), qualified AS (
    SELECT e.*
    FROM eligible e
    JOIN tm_analysis.methodology_parameters m
      ON e.methodology_version = m.methodology_version
    WHERE e.peer_group_size >= m.minimum_peer_group_size
), bounds AS (
    SELECT
        q.competition_key,
        q.season_key,
        q.position_group,
        q.methodology_version,
        PERCENTILE_CONT(m.winsor_lower_percentile) WITHIN GROUP (ORDER BY q.goals_per_90) AS goals_p_low,
        PERCENTILE_CONT(m.winsor_upper_percentile) WITHIN GROUP (ORDER BY q.goals_per_90) AS goals_p_high,
        PERCENTILE_CONT(m.winsor_lower_percentile) WITHIN GROUP (ORDER BY q.assists_per_90) AS assists_p_low,
        PERCENTILE_CONT(m.winsor_upper_percentile) WITHIN GROUP (ORDER BY q.assists_per_90) AS assists_p_high,
        PERCENTILE_CONT(m.winsor_lower_percentile) WITHIN GROUP (ORDER BY q.minutes_played) AS minutes_p_low,
        PERCENTILE_CONT(m.winsor_upper_percentile) WITHIN GROUP (ORDER BY q.minutes_played) AS minutes_p_high,
        PERCENTILE_CONT(m.winsor_lower_percentile) WITHIN GROUP (ORDER BY q.start_rate) AS start_rate_p_low,
        PERCENTILE_CONT(m.winsor_upper_percentile) WITHIN GROUP (ORDER BY q.start_rate) AS start_rate_p_high,
        PERCENTILE_CONT(m.winsor_lower_percentile) WITHIN GROUP (ORDER BY q.cards_per_90) AS cards_p_low,
        PERCENTILE_CONT(m.winsor_upper_percentile) WITHIN GROUP (ORDER BY q.cards_per_90) AS cards_p_high,
        PERCENTILE_CONT(m.winsor_lower_percentile) WITHIN GROUP (
            ORDER BY LN(1 + q.season_end_market_value_eur::NUMERIC)
        ) AS log_value_p_low,
        PERCENTILE_CONT(m.winsor_upper_percentile) WITHIN GROUP (
            ORDER BY LN(1 + q.season_end_market_value_eur::NUMERIC)
        ) AS log_value_p_high
    FROM qualified q
    JOIN tm_analysis.methodology_parameters m
      ON q.methodology_version = m.methodology_version
    GROUP BY q.competition_key, q.season_key, q.position_group, q.methodology_version,
             m.winsor_lower_percentile, m.winsor_upper_percentile
), winsorized AS (
    SELECT
        q.*,
        GREATEST(b.goals_p_low, LEAST(b.goals_p_high, q.goals_per_90)) AS w_goals_per_90,
        GREATEST(b.assists_p_low, LEAST(b.assists_p_high, q.assists_per_90)) AS w_assists_per_90,
        GREATEST(b.minutes_p_low, LEAST(b.minutes_p_high, q.minutes_played)) AS w_minutes_played,
        GREATEST(b.start_rate_p_low, LEAST(b.start_rate_p_high, q.start_rate)) AS w_start_rate,
        GREATEST(b.cards_p_low, LEAST(b.cards_p_high, q.cards_per_90)) AS w_cards_per_90,
        GREATEST(
            b.log_value_p_low,
            LEAST(b.log_value_p_high, LN(1 + q.season_end_market_value_eur::NUMERIC))
        ) AS w_log_market_value
    FROM qualified q
    JOIN bounds b USING (competition_key, season_key, position_group, methodology_version)
), metric_stats AS (
    SELECT
        competition_key,
        season_key,
        position_group,
        methodology_version,
        AVG(w_goals_per_90) AS mean_goals,
        STDDEV_SAMP(w_goals_per_90) AS sd_goals,
        AVG(w_assists_per_90) AS mean_assists,
        STDDEV_SAMP(w_assists_per_90) AS sd_assists,
        AVG(w_minutes_played) AS mean_minutes,
        STDDEV_SAMP(w_minutes_played) AS sd_minutes,
        AVG(w_start_rate) AS mean_start_rate,
        STDDEV_SAMP(w_start_rate) AS sd_start_rate,
        AVG(w_cards_per_90) AS mean_cards,
        STDDEV_SAMP(w_cards_per_90) AS sd_cards,
        AVG(w_log_market_value) AS mean_log_value,
        STDDEV_SAMP(w_log_market_value) AS sd_log_value
    FROM winsorized
    GROUP BY competition_key, season_key, position_group, methodology_version
), standardized AS (
    SELECT
        w.*,
        COALESCE((w.w_goals_per_90 - s.mean_goals) / NULLIF(s.sd_goals, 0), 0) AS goals_per_90_z,
        COALESCE((w.w_assists_per_90 - s.mean_assists) / NULLIF(s.sd_assists, 0), 0) AS assists_per_90_z,
        COALESCE((w.w_minutes_played - s.mean_minutes) / NULLIF(s.sd_minutes, 0), 0) AS minutes_played_z,
        COALESCE((w.w_start_rate - s.mean_start_rate) / NULLIF(s.sd_start_rate, 0), 0) AS start_rate_z,
        COALESCE((w.w_cards_per_90 - s.mean_cards) / NULLIF(s.sd_cards, 0), 0) AS cards_per_90_z,
        COALESCE((w.w_log_market_value - s.mean_log_value) / NULLIF(s.sd_log_value, 0), 0) AS market_value_z_score
    FROM winsorized w
    JOIN metric_stats s USING (competition_key, season_key, position_group, methodology_version)
), weight_matrix AS (
    SELECT
        methodology_version,
        position_group,
        MAX(metric_weight) FILTER (WHERE metric_name = 'goals_per_90') AS goals_weight,
        MAX(metric_weight) FILTER (WHERE metric_name = 'assists_per_90') AS assists_weight,
        MAX(metric_weight) FILTER (WHERE metric_name = 'minutes_played') AS minutes_weight,
        MAX(metric_weight) FILTER (WHERE metric_name = 'start_rate') AS start_rate_weight,
        MAX(metric_weight) FILTER (WHERE metric_name = 'cards_per_90') AS cards_weight
    FROM tm_analysis.position_metric_weight
    GROUP BY methodology_version, position_group
), composite AS (
    SELECT
        z.*,
        wm.goals_weight,
        wm.assists_weight,
        wm.minutes_weight,
        wm.start_rate_weight,
        wm.cards_weight,
        z.goals_per_90_z * wm.goals_weight
          + z.assists_per_90_z * wm.assists_weight
          + z.minutes_played_z * wm.minutes_weight
          + z.start_rate_z * wm.start_rate_weight
          - z.cards_per_90_z * wm.cards_weight AS raw_performance_score
    FROM standardized z
    JOIN weight_matrix wm USING (methodology_version, position_group)
), performance_stats AS (
    SELECT
        competition_key,
        season_key,
        position_group,
        methodology_version,
        AVG(raw_performance_score) AS mean_performance,
        STDDEV_SAMP(raw_performance_score) AS sd_performance
    FROM composite
    GROUP BY competition_key, season_key, position_group, methodology_version
), scored AS (
    SELECT
        c.*,
        COALESCE(
            (c.raw_performance_score - p.mean_performance) / NULLIF(p.sd_performance, 0),
            0
        ) AS performance_z_score,
        COALESCE(
            (c.raw_performance_score - p.mean_performance) / NULLIF(p.sd_performance, 0),
            0
        ) - c.market_value_z_score AS value_efficiency_score
    FROM composite c
    JOIN performance_stats p USING (competition_key, season_key, position_group, methodology_version)
), ranked AS (
    SELECT
        s.*,
        RANK() OVER (
            PARTITION BY competition_key, season_key, position_group
            ORDER BY value_efficiency_score DESC
        ) AS value_efficiency_rank,
        CUME_DIST() OVER (
            PARTITION BY competition_key, season_key, position_group
            ORDER BY value_efficiency_score
        ) * 100 AS value_efficiency_percentile
    FROM scored s
)
SELECT
    player_key,
    competition_key,
    season_key,
    primary_club_key,
    season_end_club_key,
    position_group,
    sub_position,
    age_at_season_end,
    age_band,
    appearances,
    starts,
    start_rate,
    minutes_played,
    goals,
    assists,
    goal_contributions,
    goals_per_90,
    assists_per_90,
    goal_contributions_per_90,
    cards_per_90,
    season_end_reference_date,
    season_end_valuation_date,
    season_end_market_value_eur,
    season_end_valuation_lag_days,
    peer_group_key,
    peer_group_size,
    ROUND(goals_per_90_z::NUMERIC, 6) AS goals_per_90_z,
    ROUND(assists_per_90_z::NUMERIC, 6) AS assists_per_90_z,
    ROUND(minutes_played_z::NUMERIC, 6) AS minutes_played_z,
    ROUND(start_rate_z::NUMERIC, 6) AS start_rate_z,
    ROUND(cards_per_90_z::NUMERIC, 6) AS cards_per_90_z,
    goals_weight,
    assists_weight,
    minutes_weight,
    start_rate_weight,
    cards_weight,
    ROUND(raw_performance_score::NUMERIC, 6) AS raw_performance_score,
    ROUND(performance_z_score::NUMERIC, 6) AS performance_z_score,
    ROUND(market_value_z_score::NUMERIC, 6) AS market_value_z_score,
    ROUND(value_efficiency_score::NUMERIC, 6) AS value_efficiency_score,
    value_efficiency_rank,
    ROUND(value_efficiency_percentile::NUMERIC, 2) AS value_efficiency_percentile,
    CASE
        WHEN value_efficiency_percentile >= 90 THEN 'high_relative_efficiency'
        WHEN value_efficiency_percentile >= 75 THEN 'above_peer_range'
        WHEN value_efficiency_percentile >= 25 THEN 'within_peer_range'
        ELSE 'low_relative_efficiency'
    END AS exploratory_efficiency_band,
    methodology_version,
    'exploratory_indicator_not_recruitment_recommendation'::TEXT AS interpretation_status
FROM ranked;

ALTER TABLE tm_analysis.fact_value_efficiency
    ADD CONSTRAINT pk_fact_value_efficiency
        PRIMARY KEY (player_key, competition_key, season_key),
    ADD CONSTRAINT ck_value_efficiency_minimum_minutes CHECK (minutes_played >= 900),
    ADD CONSTRAINT ck_value_efficiency_positive_value CHECK (season_end_market_value_eur > 0),
    ADD CONSTRAINT ck_value_efficiency_temporal_alignment
        CHECK (season_end_valuation_date <= season_end_reference_date),
    ADD CONSTRAINT ck_value_efficiency_freshness
        CHECK (season_end_valuation_lag_days BETWEEN 0 AND 365);

CREATE INDEX ix_value_efficiency_peer_rank
    ON tm_analysis.fact_value_efficiency (
        competition_key, season_key, position_group, value_efficiency_rank
    );
CREATE INDEX ix_value_efficiency_player
    ON tm_analysis.fact_value_efficiency (player_key, season_key);

CREATE TABLE tm_analysis.agg_peer_group_benchmark AS
WITH ranked_inputs AS (
    SELECT
        v.*,
        ROW_NUMBER() OVER (
            PARTITION BY competition_key, season_key, position_group
            ORDER BY season_end_market_value_eur DESC, player_key
        ) AS market_value_order,
        RANK() OVER (
            PARTITION BY competition_key, season_key, position_group
            ORDER BY performance_z_score
        ) AS performance_rank_for_correlation,
        RANK() OVER (
            PARTITION BY competition_key, season_key, position_group
            ORDER BY season_end_market_value_eur
        ) AS market_value_rank_for_correlation
    FROM tm_analysis.fact_value_efficiency v
)
SELECT
    competition_key,
    season_key,
    position_group,
    COUNT(*) AS player_count,
    SUM(season_end_market_value_eur)::BIGINT AS total_market_value_eur,
    ROUND(AVG(season_end_market_value_eur), 2) AS average_market_value_eur,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY season_end_market_value_eur)::NUMERIC(18,2) AS median_market_value_eur,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY season_end_market_value_eur)::NUMERIC(18,2) AS p25_market_value_eur,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY season_end_market_value_eur)::NUMERIC(18,2) AS p75_market_value_eur,
    ROUND(
        SUM(season_end_market_value_eur) FILTER (WHERE market_value_order <= 10)::NUMERIC
        / NULLIF(SUM(season_end_market_value_eur), 0) * 100,
        4
    ) AS top_10_value_concentration_pct,
    ROUND(AVG(goals_per_90), 4) AS average_goals_per_90,
    ROUND(AVG(assists_per_90), 4) AS average_assists_per_90,
    ROUND(AVG(goal_contributions_per_90), 4) AS average_goal_contributions_per_90,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY goal_contributions_per_90)::NUMERIC(12,4) AS median_goal_contributions_per_90,
    ROUND(CORR(
        performance_rank_for_correlation::NUMERIC,
        market_value_rank_for_correlation::NUMERIC
    )::NUMERIC, 4) AS spearman_performance_value_correlation,
    MIN(season_end_valuation_date) AS earliest_valuation_date,
    MAX(season_end_valuation_date) AS latest_valuation_date,
    methodology_version
FROM ranked_inputs
GROUP BY competition_key, season_key, position_group, methodology_version;

ALTER TABLE tm_analysis.agg_peer_group_benchmark
    ADD CONSTRAINT pk_agg_peer_group_benchmark
        PRIMARY KEY (competition_key, season_key, position_group);
