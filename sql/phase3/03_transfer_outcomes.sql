CREATE TABLE tm_analysis.fact_transfer_value_outcome AS
WITH snapshot AS (
    SELECT max_business_date AS maximum_valuation_date
    FROM tm_analytics.source_snapshot
    WHERE source_table = 'player_valuations'
), horizons AS (
    SELECT
        m.methodology_version,
        m.maximum_season_valuation_lag_days,
        m.maximum_transfer_target_lag_days,
        UNNEST(m.transfer_horizons_months) AS horizon_months
    FROM tm_analysis.methodology_parameters m
), expanded AS (
    SELECT
        t.*,
        h.methodology_version,
        h.maximum_season_valuation_lag_days,
        h.maximum_transfer_target_lag_days,
        h.horizon_months,
        (t.transfer_date + MAKE_INTERVAL(months => h.horizon_months))::DATE AS target_date,
        s.maximum_valuation_date
    FROM tm_analytics.fact_transfer t
    CROSS JOIN horizons h
    CROSS JOIN snapshot s
    WHERE t.is_historical_analysis_eligible
)
SELECT
    e.transfer_key,
    e.horizon_months,
    e.player_key,
    e.source_player_id,
    e.transfer_date,
    e.target_date,
    e.maximum_valuation_date,
    e.from_club_key,
    e.to_club_key,
    e.fee_status,
    e.transfer_fee_eur,
    e.matched_valuation_key AS baseline_valuation_key,
    e.matched_valuation_date AS baseline_valuation_date,
    e.market_value_at_transfer_eur AS baseline_market_value_eur,
    e.valuation_lag_days AS baseline_valuation_lag_days,
    post.valuation_key AS post_valuation_key,
    post.valuation_date AS post_valuation_date,
    post.market_value_eur AS post_market_value_eur,
    post.club_key_at_valuation AS post_valuation_club_key,
    CASE WHEN post.valuation_date IS NOT NULL THEN e.target_date - post.valuation_date END AS post_valuation_target_lag_days,
    e.target_date <= e.maximum_valuation_date AS is_horizon_matured,
    e.market_value_at_transfer_eur > 0
        AND e.valuation_lag_days BETWEEN 0 AND e.maximum_season_valuation_lag_days AS has_eligible_baseline,
    post.market_value_eur > 0
        AND e.target_date - post.valuation_date BETWEEN 0 AND e.maximum_transfer_target_lag_days AS has_eligible_post_valuation,
    e.target_date <= e.maximum_valuation_date
        AND e.market_value_at_transfer_eur > 0
        AND e.valuation_lag_days BETWEEN 0 AND e.maximum_season_valuation_lag_days
        AND post.market_value_eur > 0
        AND e.target_date - post.valuation_date BETWEEN 0 AND e.maximum_transfer_target_lag_days AS is_value_change_eligible,
    CASE
        WHEN e.target_date <= e.maximum_valuation_date
         AND e.market_value_at_transfer_eur > 0
         AND e.valuation_lag_days BETWEEN 0 AND e.maximum_season_valuation_lag_days
         AND post.market_value_eur > 0
         AND e.target_date - post.valuation_date BETWEEN 0 AND e.maximum_transfer_target_lag_days
        THEN post.market_value_eur - e.market_value_at_transfer_eur
    END AS post_transfer_value_change_eur,
    CASE
        WHEN e.target_date <= e.maximum_valuation_date
         AND e.market_value_at_transfer_eur > 0
         AND e.valuation_lag_days BETWEEN 0 AND e.maximum_season_valuation_lag_days
         AND post.market_value_eur > 0
         AND e.target_date - post.valuation_date BETWEEN 0 AND e.maximum_transfer_target_lag_days
        THEN ROUND(
            (post.market_value_eur - e.market_value_at_transfer_eur)::NUMERIC
            / e.market_value_at_transfer_eur * 100,
            4
        )
    END AS post_transfer_value_growth_pct,
    CASE
        WHEN post.valuation_date IS NULL THEN 'no_post_valuation'
        WHEN e.target_date > e.maximum_valuation_date THEN 'horizon_not_matured'
        WHEN e.target_date - post.valuation_date > e.maximum_transfer_target_lag_days THEN 'post_valuation_too_old'
        WHEN post.market_value_eur <= 0 THEN 'post_value_nonpositive'
        ELSE 'post_valuation_eligible'
    END AS post_valuation_status,
    CASE
        WHEN post.club_key_at_valuation IS NULL OR e.to_club_key IS NULL THEN 'club_comparison_unavailable'
        WHEN post.club_key_at_valuation = e.to_club_key THEN 'matches_destination_club'
        ELSE 'different_club_at_post_valuation'
    END AS post_club_match_status,
    CASE
        WHEN p.date_of_birth IS NOT NULL AND e.transfer_date >= p.date_of_birth
        THEN EXTRACT(YEAR FROM AGE(e.transfer_date, p.date_of_birth))::SMALLINT
    END AS age_at_transfer,
    CASE
        WHEN p.date_of_birth IS NULL OR e.transfer_date < p.date_of_birth THEN 'Unknown'
        WHEN EXTRACT(YEAR FROM AGE(e.transfer_date, p.date_of_birth)) < 20 THEN 'Under 20'
        WHEN EXTRACT(YEAR FROM AGE(e.transfer_date, p.date_of_birth)) <= 22 THEN '20-22'
        WHEN EXTRACT(YEAR FROM AGE(e.transfer_date, p.date_of_birth)) <= 25 THEN '23-25'
        WHEN EXTRACT(YEAR FROM AGE(e.transfer_date, p.date_of_birth)) <= 28 THEN '26-28'
        WHEN EXTRACT(YEAR FROM AGE(e.transfer_date, p.date_of_birth)) <= 31 THEN '29-31'
        ELSE '32+'
    END AS age_band_at_transfer,
    e.methodology_version,
    'market_value_change_not_financial_roi'::TEXT AS interpretation_status
FROM expanded e
LEFT JOIN tm_analytics.dim_player p ON e.player_key = p.player_key
LEFT JOIN LATERAL (
    SELECT
        v.valuation_key,
        v.valuation_date,
        v.market_value_eur,
        v.club_key_at_valuation
    FROM tm_analytics.fact_player_valuation v
    WHERE v.player_key = e.player_key
      AND v.is_valid_valuation
      AND v.valuation_date > e.transfer_date
      AND v.valuation_date <= e.target_date
    ORDER BY v.valuation_date DESC
    LIMIT 1
) post ON TRUE;

ALTER TABLE tm_analysis.fact_transfer_value_outcome
    ADD CONSTRAINT pk_fact_transfer_value_outcome PRIMARY KEY (transfer_key, horizon_months),
    ADD CONSTRAINT ck_transfer_outcome_horizon CHECK (horizon_months IN (6, 12, 24)),
    ADD CONSTRAINT ck_transfer_outcome_post_date
        CHECK (post_valuation_date IS NULL OR (post_valuation_date > transfer_date AND post_valuation_date <= target_date));

CREATE INDEX ix_transfer_outcome_eligibility
    ON tm_analysis.fact_transfer_value_outcome (horizon_months, is_value_change_eligible);
CREATE INDEX ix_transfer_outcome_destination
    ON tm_analysis.fact_transfer_value_outcome (to_club_key, horizon_months);
CREATE INDEX ix_transfer_outcome_player
    ON tm_analysis.fact_transfer_value_outcome (player_key, transfer_date);

CREATE TABLE tm_analysis.agg_transfer_value_outcome AS
SELECT
    horizon_months,
    fee_status,
    COUNT(*) AS transfer_count,
    COUNT(*) FILTER (WHERE is_horizon_matured) AS matured_transfer_count,
    COUNT(*) FILTER (WHERE has_eligible_baseline) AS eligible_baseline_count,
    COUNT(*) FILTER (WHERE has_eligible_post_valuation) AS eligible_post_valuation_count,
    COUNT(*) FILTER (WHERE is_value_change_eligible) AS value_change_eligible_count,
    ROUND(
        COUNT(*) FILTER (WHERE is_value_change_eligible)::NUMERIC
        / NULLIF(COUNT(*), 0) * 100,
        4
    ) AS value_change_coverage_pct,
    ROUND(AVG(post_transfer_value_change_eur) FILTER (WHERE is_value_change_eligible), 2) AS average_value_change_eur,
    PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY post_transfer_value_change_eur
    ) FILTER (WHERE is_value_change_eligible)::NUMERIC(18,2) AS median_value_change_eur,
    ROUND(AVG(post_transfer_value_growth_pct) FILTER (WHERE is_value_change_eligible), 4) AS average_value_growth_pct,
    PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY post_transfer_value_growth_pct
    ) FILTER (WHERE is_value_change_eligible)::NUMERIC(18,4) AS median_value_growth_pct,
    MIN(post_valuation_date) FILTER (WHERE is_value_change_eligible) AS earliest_post_valuation_date,
    MAX(post_valuation_date) FILTER (WHERE is_value_change_eligible) AS latest_post_valuation_date,
    methodology_version
FROM tm_analysis.fact_transfer_value_outcome
GROUP BY horizon_months, fee_status, methodology_version;

ALTER TABLE tm_analysis.agg_transfer_value_outcome
    ADD CONSTRAINT pk_agg_transfer_value_outcome PRIMARY KEY (horizon_months, fee_status);

CREATE VIEW tm_analysis.vw_value_efficiency_ranking AS
SELECT
    v.*,
    p.player_name,
    p.country_of_citizenship,
    c.competition_name,
    pc.club_name AS primary_club_name,
    ec.club_name AS season_end_club_name
FROM tm_analysis.fact_value_efficiency v
JOIN tm_analytics.dim_player p ON v.player_key = p.player_key
JOIN tm_analytics.dim_competition c ON v.competition_key = c.competition_key
LEFT JOIN tm_analytics.dim_club pc ON v.primary_club_key = pc.club_key
LEFT JOIN tm_analytics.dim_club ec ON v.season_end_club_key = ec.club_key;

CREATE VIEW tm_analysis.vw_player_value_development AS
SELECT
    d.*,
    p.player_name,
    c.competition_name,
    club.club_name AS season_end_club_name
FROM tm_analysis.fact_player_value_development d
JOIN tm_analytics.dim_player p ON d.player_key = p.player_key
JOIN tm_analytics.dim_competition c ON d.competition_key = c.competition_key
LEFT JOIN tm_analytics.dim_club club ON d.season_end_club_key = club.club_key;

CREATE VIEW tm_analysis.vw_transfer_value_outcomes AS
SELECT
    o.*,
    p.player_name,
    fc.club_name AS from_club_name,
    tc.club_name AS to_club_name
FROM tm_analysis.fact_transfer_value_outcome o
LEFT JOIN tm_analytics.dim_player p ON o.player_key = p.player_key
LEFT JOIN tm_analytics.dim_club fc ON o.from_club_key = fc.club_key
LEFT JOIN tm_analytics.dim_club tc ON o.to_club_key = tc.club_key;

ANALYZE tm_analysis.fact_player_season_kpi;
ANALYZE tm_analysis.fact_player_value_development;
ANALYZE tm_analysis.fact_value_efficiency;
ANALYZE tm_analysis.fact_transfer_value_outcome;
