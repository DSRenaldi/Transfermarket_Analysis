CREATE TABLE tm_analytics.fact_player_club_season AS
WITH aggregated AS (
    SELECT
        a.player_key,
        a.club_key,
        a.competition_key,
        a.season_key,
        COUNT(*) AS appearance_rows,
        COUNT(*) FILTER (WHERE a.is_valid_for_aggregation) AS valid_appearances,
        COUNT(*) FILTER (WHERE NOT a.is_valid_for_aggregation) AS rejected_appearance_rows,
        COUNT(*) FILTER (WHERE a.is_valid_for_aggregation AND a.is_starter) AS starts,
        COUNT(*) FILTER (WHERE a.is_valid_for_aggregation AND a.is_starter IS NULL) AS appearances_without_lineup_match,
        SUM(a.minutes_played) FILTER (WHERE a.is_valid_for_aggregation) AS minutes_played,
        SUM(a.goals) FILTER (WHERE a.is_valid_for_aggregation) AS goals,
        SUM(a.assists) FILTER (WHERE a.is_valid_for_aggregation) AS assists,
        SUM(a.yellow_cards) FILTER (WHERE a.is_valid_for_aggregation) AS yellow_cards,
        SUM(a.red_cards) FILTER (WHERE a.is_valid_for_aggregation) AS red_cards,
        MIN(a.appearance_date) AS first_appearance_date,
        MAX(a.appearance_date) AS last_appearance_date
    FROM tm_analytics.fact_player_appearance a
    WHERE a.is_v1_scope
      AND a.player_key IS NOT NULL
      AND a.club_key IS NOT NULL
      AND a.competition_key IS NOT NULL
      AND a.season_key IS NOT NULL
    GROUP BY a.player_key, a.club_key, a.competition_key, a.season_key
), ranked AS (
    SELECT
        a.*,
        ROW_NUMBER() OVER (
            PARTITION BY a.player_key, a.competition_key, a.season_key
            ORDER BY a.last_appearance_date DESC, a.minutes_played DESC NULLS LAST, a.club_key
        ) AS reverse_stint_order,
        COUNT(*) OVER (
            PARTITION BY a.player_key, a.competition_key, a.season_key
        ) AS club_count_in_competition_season
    FROM aggregated a
)
SELECT
    r.player_key,
    r.club_key,
    r.competition_key,
    r.season_key,
    r.appearance_rows,
    r.valid_appearances,
    r.rejected_appearance_rows,
    r.starts,
    r.appearances_without_lineup_match,
    COALESCE(r.minutes_played, 0)::BIGINT AS minutes_played,
    COALESCE(r.goals, 0)::INTEGER AS goals,
    COALESCE(r.assists, 0)::INTEGER AS assists,
    COALESCE(r.goals, 0)::INTEGER + COALESCE(r.assists, 0)::INTEGER AS goal_contributions,
    COALESCE(r.yellow_cards, 0)::INTEGER AS yellow_cards,
    COALESCE(r.red_cards, 0)::INTEGER AS red_cards,
    r.first_appearance_date,
    r.last_appearance_date,
    r.club_count_in_competition_season,
    r.reverse_stint_order = 1 AS is_latest_club_stint,
    CASE WHEN COALESCE(r.minutes_played, 0) > 0 THEN ROUND(r.goals::NUMERIC / r.minutes_played * 90, 4) END AS goals_per_90,
    CASE WHEN COALESCE(r.minutes_played, 0) > 0 THEN ROUND(r.assists::NUMERIC / r.minutes_played * 90, 4) END AS assists_per_90,
    CASE WHEN COALESCE(r.minutes_played, 0) > 0 THEN ROUND((r.goals + r.assists)::NUMERIC / r.minutes_played * 90, 4) END AS goal_contributions_per_90,
    CASE WHEN COALESCE(r.goals, 0) + COALESCE(r.assists, 0) > 0 THEN ROUND(r.minutes_played::NUMERIC / (r.goals + r.assists), 2) END AS minutes_per_goal_contribution,
    CASE WHEN COALESCE(r.minutes_played, 0) > 0 THEN ROUND((r.yellow_cards + r.red_cards)::NUMERIC / r.minutes_played * 90, 4) END AS cards_per_90,
    r.last_appearance_date AS stint_end_reference_date,
    sv.valuation_key AS stint_end_valuation_key,
    sv.valuation_date AS stint_end_valuation_date,
    sv.market_value_eur AS stint_end_market_value_eur,
    CASE WHEN sv.valuation_date IS NOT NULL THEN r.last_appearance_date - sv.valuation_date END AS stint_end_valuation_lag_days,
    CASE
        WHEN sv.valuation_date IS NULL THEN 'no_prior_valuation'
        WHEN r.last_appearance_date - sv.valuation_date <= 30 THEN 'within_30_days'
        WHEN r.last_appearance_date - sv.valuation_date <= 90 THEN 'within_90_days'
        WHEN r.last_appearance_date - sv.valuation_date <= 365 THEN 'within_365_days'
        ELSE 'stale_over_365_days'
    END AS stint_end_valuation_match_status,
    CASE
        WHEN dp.date_of_birth IS NOT NULL AND r.last_appearance_date >= dp.date_of_birth
        THEN EXTRACT(YEAR FROM AGE(r.last_appearance_date, dp.date_of_birth))::SMALLINT
    END AS age_at_stint_end,
    COALESCE(r.minutes_played, 0) >= p.minimum_minutes AS meets_minimum_minutes,
    cs.is_v1_scope AND dp.is_outfield AS is_v1_scope,
    cs.is_v1_scope
        AND dp.is_outfield
        AND COALESCE(r.minutes_played, 0) >= p.minimum_minutes
        AND sv.market_value_eur > 0 AS is_v1_stint_analysis_eligible
FROM ranked r
CROSS JOIN tm_analytics.project_parameters p
JOIN tm_analytics.dim_player dp
    ON r.player_key = dp.player_key
JOIN tm_analytics.dim_competition_season cs
    ON r.competition_key = cs.competition_key AND r.season_key = cs.season_key
LEFT JOIN LATERAL (
    SELECT v.valuation_key, v.valuation_date, v.market_value_eur
    FROM tm_analytics.fact_player_valuation v
    WHERE v.player_key = r.player_key
      AND v.valuation_date <= r.last_appearance_date
      AND v.is_valid_valuation
    ORDER BY v.valuation_date DESC
    LIMIT 1
) sv ON TRUE;

ALTER TABLE tm_analytics.fact_player_club_season
    ADD CONSTRAINT pk_fact_player_club_season
        PRIMARY KEY (player_key, club_key, competition_key, season_key),
    ADD CONSTRAINT fk_fact_player_club_season_player
        FOREIGN KEY (player_key) REFERENCES tm_analytics.dim_player (player_key),
    ADD CONSTRAINT fk_fact_player_club_season_club
        FOREIGN KEY (club_key) REFERENCES tm_analytics.dim_club (club_key),
    ADD CONSTRAINT fk_fact_player_club_season_competition
        FOREIGN KEY (competition_key) REFERENCES tm_analytics.dim_competition (competition_key),
    ADD CONSTRAINT fk_fact_player_club_season_season
        FOREIGN KEY (season_key) REFERENCES tm_analytics.dim_season (season_key),
    ADD CONSTRAINT ck_fact_player_club_season_valuation_date
        CHECK (stint_end_valuation_date IS NULL OR stint_end_valuation_date <= stint_end_reference_date);

CREATE INDEX ix_fact_player_club_season_scope
    ON tm_analytics.fact_player_club_season (competition_key, season_key, is_v1_stint_analysis_eligible);
CREATE INDEX ix_fact_player_club_season_club
    ON tm_analytics.fact_player_club_season (club_key, season_key);

CREATE TABLE tm_analytics.fact_player_season AS
WITH aggregated AS (
    SELECT
        pcs.player_key,
        pcs.competition_key,
        pcs.season_key,
        COUNT(*) AS club_count,
        SUM(pcs.appearance_rows) AS appearance_rows,
        SUM(pcs.valid_appearances) AS appearances,
        SUM(pcs.rejected_appearance_rows) AS rejected_appearance_rows,
        SUM(pcs.starts) AS starts,
        SUM(pcs.appearances_without_lineup_match) AS appearances_without_lineup_match,
        SUM(pcs.minutes_played) AS minutes_played,
        SUM(pcs.goals) AS goals,
        SUM(pcs.assists) AS assists,
        SUM(pcs.yellow_cards) AS yellow_cards,
        SUM(pcs.red_cards) AS red_cards,
        MIN(pcs.first_appearance_date) AS first_appearance_date,
        MAX(pcs.last_appearance_date) AS last_appearance_date
    FROM tm_analytics.fact_player_club_season pcs
    GROUP BY pcs.player_key, pcs.competition_key, pcs.season_key
)
SELECT
    a.player_key,
    a.competition_key,
    a.season_key,
    primary_club.club_key AS primary_club_key,
    latest_club.club_key AS season_end_club_key,
    a.club_count,
    a.club_count > 1 AS changed_club_within_competition_season,
    a.appearance_rows,
    a.appearances,
    a.rejected_appearance_rows,
    a.starts,
    a.appearances_without_lineup_match,
    a.minutes_played,
    a.goals,
    a.assists,
    a.goals + a.assists AS goal_contributions,
    a.yellow_cards,
    a.red_cards,
    a.first_appearance_date,
    a.last_appearance_date,
    CASE WHEN a.minutes_played > 0 THEN ROUND(a.goals::NUMERIC / a.minutes_played * 90, 4) END AS goals_per_90,
    CASE WHEN a.minutes_played > 0 THEN ROUND(a.assists::NUMERIC / a.minutes_played * 90, 4) END AS assists_per_90,
    CASE WHEN a.minutes_played > 0 THEN ROUND((a.goals + a.assists)::NUMERIC / a.minutes_played * 90, 4) END AS goal_contributions_per_90,
    CASE WHEN a.goals + a.assists > 0 THEN ROUND(a.minutes_played::NUMERIC / (a.goals + a.assists), 2) END AS minutes_per_goal_contribution,
    CASE WHEN a.minutes_played > 0 THEN ROUND((a.yellow_cards + a.red_cards)::NUMERIC / a.minutes_played * 90, 4) END AS cards_per_90,
    cs.season_end_date AS season_end_reference_date,
    sev.valuation_key AS season_end_valuation_key,
    sev.valuation_date AS season_end_valuation_date,
    sev.market_value_eur AS season_end_market_value_eur,
    CASE WHEN sev.valuation_date IS NOT NULL THEN cs.season_end_date - sev.valuation_date END AS season_end_valuation_lag_days,
    CASE
        WHEN sev.valuation_date IS NULL THEN 'no_prior_valuation'
        WHEN cs.season_end_date - sev.valuation_date <= 30 THEN 'within_30_days'
        WHEN cs.season_end_date - sev.valuation_date <= 90 THEN 'within_90_days'
        WHEN cs.season_end_date - sev.valuation_date <= 365 THEN 'within_365_days'
        ELSE 'stale_over_365_days'
    END AS season_end_valuation_match_status,
    CASE
        WHEN dp.date_of_birth IS NOT NULL AND cs.season_end_date >= dp.date_of_birth
        THEN EXTRACT(YEAR FROM AGE(cs.season_end_date, dp.date_of_birth))::SMALLINT
    END AS age_at_season_end,
    dp.position_group,
    dp.sub_position,
    dp.is_outfield,
    a.minutes_played >= p.minimum_minutes AS meets_minimum_minutes,
    cs.is_v1_scope AND dp.is_outfield AS is_v1_scope,
    cs.is_v1_scope
        AND dp.is_outfield
        AND a.minutes_played >= p.minimum_minutes
        AND sev.market_value_eur > 0 AS is_v1_value_analysis_eligible,
    cs.appearance_game_coverage_pct,
    cs.appearance_coverage_status
FROM aggregated a
CROSS JOIN tm_analytics.project_parameters p
JOIN tm_analytics.dim_player dp
    ON a.player_key = dp.player_key
JOIN tm_analytics.dim_competition_season cs
    ON a.competition_key = cs.competition_key AND a.season_key = cs.season_key
LEFT JOIN LATERAL (
    SELECT pcs.club_key
    FROM tm_analytics.fact_player_club_season pcs
    WHERE pcs.player_key = a.player_key
      AND pcs.competition_key = a.competition_key
      AND pcs.season_key = a.season_key
    ORDER BY pcs.minutes_played DESC, pcs.last_appearance_date DESC, pcs.club_key
    LIMIT 1
) primary_club ON TRUE
LEFT JOIN LATERAL (
    SELECT pcs.club_key
    FROM tm_analytics.fact_player_club_season pcs
    WHERE pcs.player_key = a.player_key
      AND pcs.competition_key = a.competition_key
      AND pcs.season_key = a.season_key
    ORDER BY pcs.last_appearance_date DESC, pcs.minutes_played DESC, pcs.club_key
    LIMIT 1
) latest_club ON TRUE
LEFT JOIN LATERAL (
    SELECT v.valuation_key, v.valuation_date, v.market_value_eur
    FROM tm_analytics.fact_player_valuation v
    WHERE v.player_key = a.player_key
      AND v.valuation_date <= cs.season_end_date
      AND v.is_valid_valuation
    ORDER BY v.valuation_date DESC
    LIMIT 1
) sev ON TRUE;

ALTER TABLE tm_analytics.fact_player_season
    ADD CONSTRAINT pk_fact_player_season
        PRIMARY KEY (player_key, competition_key, season_key),
    ADD CONSTRAINT fk_fact_player_season_player
        FOREIGN KEY (player_key) REFERENCES tm_analytics.dim_player (player_key),
    ADD CONSTRAINT fk_fact_player_season_competition
        FOREIGN KEY (competition_key) REFERENCES tm_analytics.dim_competition (competition_key),
    ADD CONSTRAINT fk_fact_player_season_season
        FOREIGN KEY (season_key) REFERENCES tm_analytics.dim_season (season_key),
    ADD CONSTRAINT fk_fact_player_season_primary_club
        FOREIGN KEY (primary_club_key) REFERENCES tm_analytics.dim_club (club_key),
    ADD CONSTRAINT fk_fact_player_season_end_club
        FOREIGN KEY (season_end_club_key) REFERENCES tm_analytics.dim_club (club_key),
    ADD CONSTRAINT ck_fact_player_season_valuation_date
        CHECK (season_end_valuation_date IS NULL OR season_end_valuation_date <= season_end_reference_date);

CREATE INDEX ix_fact_player_season_scope
    ON tm_analytics.fact_player_season (competition_key, season_key, is_v1_value_analysis_eligible);
CREATE INDEX ix_fact_player_season_player
    ON tm_analytics.fact_player_season (player_key, season_key);
CREATE INDEX ix_fact_player_season_primary_club
    ON tm_analytics.fact_player_season (primary_club_key, season_key);

CREATE VIEW tm_analytics.vw_v1_player_season AS
SELECT
    ps.*,
    p.player_name,
    p.date_of_birth,
    p.country_of_citizenship,
    c.competition_name,
    c.country_name AS competition_country,
    pc.club_name AS primary_club_name,
    ec.club_name AS season_end_club_name
FROM tm_analytics.fact_player_season ps
JOIN tm_analytics.dim_player p ON ps.player_key = p.player_key
JOIN tm_analytics.dim_competition c ON ps.competition_key = c.competition_key
LEFT JOIN tm_analytics.dim_club pc ON ps.primary_club_key = pc.club_key
LEFT JOIN tm_analytics.dim_club ec ON ps.season_end_club_key = ec.club_key
WHERE ps.is_v1_scope;

CREATE VIEW tm_analytics.vw_v1_player_club_season AS
SELECT
    pcs.*,
    p.player_name,
    p.position_group,
    p.sub_position,
    c.club_name,
    comp.competition_name
FROM tm_analytics.fact_player_club_season pcs
JOIN tm_analytics.dim_player p ON pcs.player_key = p.player_key
JOIN tm_analytics.dim_club c ON pcs.club_key = c.club_key
JOIN tm_analytics.dim_competition comp ON pcs.competition_key = comp.competition_key
WHERE pcs.is_v1_scope;

CREATE VIEW tm_analytics.vw_historical_transfers AS
SELECT
    t.*,
    p.player_name,
    fc.club_name AS from_club_name,
    tc.club_name AS to_club_name
FROM tm_analytics.fact_transfer t
JOIN tm_analytics.dim_player p ON t.player_key = p.player_key
LEFT JOIN tm_analytics.dim_club fc ON t.from_club_key = fc.club_key
LEFT JOIN tm_analytics.dim_club tc ON t.to_club_key = tc.club_key
WHERE t.is_historical_analysis_eligible;

CREATE VIEW tm_analytics.vw_data_freshness AS
SELECT source_table, min_business_date, max_business_date, row_count, recorded_at_utc
FROM tm_analytics.source_snapshot;
