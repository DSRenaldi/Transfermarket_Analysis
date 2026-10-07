CREATE TABLE tm_analytics.fact_player_appearance AS
WITH lineup AS (
    SELECT
        game_id,
        player_id,
        COUNT(*) AS lineup_row_count,
        BOOL_OR(type = 'starting_lineup') AS has_starting_lineup_record,
        BOOL_OR(type = 'substitutes') AS has_substitute_record
    FROM tm_raw.game_lineups
    GROUP BY game_id, player_id
)
SELECT
    a.appearance_id AS appearance_key,
    a.appearance_id AS source_appearance_id,
    dp.player_key,
    a.player_id::BIGINT AS source_player_id,
    dg.game_key,
    dc.club_key,
    CASE WHEN a.player_club_id ~ '^[0-9]+$' THEN a.player_club_id::BIGINT END AS source_club_id,
    CASE WHEN a.player_current_club_id ~ '^[0-9]+$' THEN a.player_current_club_id::BIGINT END AS source_current_club_id,
    dg.competition_key,
    dg.season_key,
    dg.date_key,
    dg.game_date AS appearance_date,
    a.player_name AS source_player_name,
    CASE
        WHEN a.minutes_played ~ '^[0-9]+(?:\.[0-9]+)?$'
         AND a.minutes_played::NUMERIC BETWEEN 0 AND 130
        THEN ROUND(a.minutes_played::NUMERIC)::SMALLINT
    END AS minutes_played,
    CASE WHEN a.minutes_played ~ '^[0-9]+(?:\.[0-9]+)?$' THEN a.minutes_played::NUMERIC END AS source_minutes_played,
    CASE WHEN a.goals ~ '^[0-9]+$' THEN a.goals::SMALLINT END AS goals,
    CASE WHEN a.assists ~ '^[0-9]+$' THEN a.assists::SMALLINT END AS assists,
    CASE WHEN a.yellow_cards ~ '^[0-9]+$' THEN a.yellow_cards::SMALLINT END AS yellow_cards,
    CASE WHEN a.red_cards ~ '^[0-9]+$' THEN a.red_cards::SMALLINT END AS red_cards,
    CASE
        WHEN l.lineup_row_count IS NULL THEN NULL
        WHEN l.has_starting_lineup_record THEN TRUE
        ELSE FALSE
    END AS is_starter,
    CASE
        WHEN l.lineup_row_count IS NULL THEN 'missing'
        WHEN l.lineup_row_count = 1 THEN 'matched_unique'
        WHEN l.has_starting_lineup_record AND l.has_substitute_record THEN 'duplicate_conflict'
        ELSE 'matched_duplicate'
    END AS lineup_match_status,
    COALESCE(l.lineup_row_count, 0) AS lineup_row_count,
    dp.player_key IS NOT NULL AS has_player_dimension,
    dc.club_key IS NOT NULL AS has_club_dimension,
    (
        dp.player_key IS NOT NULL
        AND dc.club_key IS NOT NULL
        AND a.minutes_played ~ '^[0-9]+(?:\.[0-9]+)?$'
        AND a.minutes_played::NUMERIC BETWEEN 0 AND 130
        AND a.goals ~ '^[0-9]+$'
        AND a.assists ~ '^[0-9]+$'
        AND a.yellow_cards ~ '^[0-9]+$'
        AND a.red_cards ~ '^[0-9]+$'
    ) AS is_valid_for_aggregation,
    CASE
        WHEN dp.player_key IS NULL THEN 'missing_player_dimension'
        WHEN dc.club_key IS NULL THEN 'missing_club_dimension'
        WHEN a.minutes_played !~ '^[0-9]+(?:\.[0-9]+)?$' THEN 'invalid_minutes_format'
        WHEN a.minutes_played::NUMERIC NOT BETWEEN 0 AND 130 THEN 'minutes_out_of_range'
        WHEN a.goals !~ '^[0-9]+$'
          OR a.assists !~ '^[0-9]+$'
          OR a.yellow_cards !~ '^[0-9]+$'
          OR a.red_cards !~ '^[0-9]+$' THEN 'invalid_metric_format'
        ELSE 'valid'
    END AS data_quality_status,
    dg.is_v1_scope
FROM tm_raw.appearances a
JOIN tm_analytics.dim_game dg
    ON a.game_id::BIGINT = dg.game_key
LEFT JOIN tm_analytics.dim_player dp
    ON a.player_id ~ '^[0-9]+$' AND a.player_id::BIGINT = dp.player_key
LEFT JOIN tm_analytics.dim_club dc
    ON a.player_club_id ~ '^[0-9]+$' AND a.player_club_id::BIGINT = dc.club_key
LEFT JOIN lineup l
    ON a.game_id = l.game_id AND a.player_id = l.player_id;

ALTER TABLE tm_analytics.fact_player_appearance
    ADD CONSTRAINT pk_fact_player_appearance PRIMARY KEY (appearance_key),
    ADD CONSTRAINT fk_fact_appearance_player
        FOREIGN KEY (player_key) REFERENCES tm_analytics.dim_player (player_key),
    ADD CONSTRAINT fk_fact_appearance_game
        FOREIGN KEY (game_key) REFERENCES tm_analytics.dim_game (game_key),
    ADD CONSTRAINT fk_fact_appearance_club
        FOREIGN KEY (club_key) REFERENCES tm_analytics.dim_club (club_key),
    ADD CONSTRAINT fk_fact_appearance_competition
        FOREIGN KEY (competition_key) REFERENCES tm_analytics.dim_competition (competition_key),
    ADD CONSTRAINT fk_fact_appearance_season
        FOREIGN KEY (season_key) REFERENCES tm_analytics.dim_season (season_key),
    ADD CONSTRAINT fk_fact_appearance_date
        FOREIGN KEY (date_key) REFERENCES tm_analytics.dim_date (date_key);

CREATE INDEX ix_fact_appearance_player
    ON tm_analytics.fact_player_appearance (player_key);
CREATE INDEX ix_fact_appearance_game
    ON tm_analytics.fact_player_appearance (game_key);
CREATE INDEX ix_fact_appearance_club_competition_season
    ON tm_analytics.fact_player_appearance (club_key, competition_key, season_key);
CREATE INDEX ix_fact_appearance_player_competition_season
    ON tm_analytics.fact_player_appearance (player_key, competition_key, season_key);
CREATE INDEX ix_fact_appearance_v1_valid
    ON tm_analytics.fact_player_appearance (is_v1_scope, is_valid_for_aggregation);

CREATE TABLE tm_analytics.fact_player_valuation AS
SELECT
    pv.player_id::BIGINT * 100000000
        + TO_CHAR(pv.date::DATE, 'YYYYMMDD')::BIGINT AS valuation_key,
    dp.player_key,
    pv.player_id::BIGINT AS source_player_id,
    pv.date::DATE AS valuation_date,
    TO_CHAR(pv.date::DATE, 'YYYYMMDD')::INTEGER AS date_key,
    CASE WHEN pv.market_value_in_eur ~ '^[0-9]+(?:\.[0-9]+)?$' THEN ROUND(pv.market_value_in_eur::NUMERIC)::BIGINT END AS market_value_eur,
    dc.club_key AS club_key_at_valuation,
    CASE WHEN pv.current_club_id ~ '^[0-9]+$' THEN pv.current_club_id::BIGINT END AS source_club_id_at_valuation,
    pv.current_club_name AS source_club_name_at_valuation,
    pv.player_club_domestic_competition_id AS source_domestic_competition_id,
    CASE
        WHEN dp.date_of_birth IS NOT NULL AND pv.date::DATE >= dp.date_of_birth
        THEN EXTRACT(YEAR FROM AGE(pv.date::DATE, dp.date_of_birth))::SMALLINT
    END AS age_at_valuation,
    dp.player_key IS NOT NULL AS has_player_dimension,
    dc.club_key IS NOT NULL AS has_club_dimension,
    pv.market_value_in_eur ~ '^[0-9]+(?:\.[0-9]+)?$'
        AND pv.market_value_in_eur::NUMERIC >= 0 AS is_valid_valuation
FROM tm_raw.player_valuations pv
LEFT JOIN tm_analytics.dim_player dp
    ON pv.player_id ~ '^[0-9]+$' AND pv.player_id::BIGINT = dp.player_key
LEFT JOIN tm_analytics.dim_club dc
    ON pv.current_club_id ~ '^[0-9]+$' AND pv.current_club_id::BIGINT = dc.club_key
WHERE pv.player_id ~ '^[0-9]+$'
  AND pv.date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$';

ALTER TABLE tm_analytics.fact_player_valuation
    ADD CONSTRAINT pk_fact_player_valuation PRIMARY KEY (valuation_key),
    ADD CONSTRAINT uq_fact_player_valuation_player_date UNIQUE (source_player_id, valuation_date),
    ADD CONSTRAINT fk_fact_valuation_player
        FOREIGN KEY (player_key) REFERENCES tm_analytics.dim_player (player_key),
    ADD CONSTRAINT fk_fact_valuation_date
        FOREIGN KEY (date_key) REFERENCES tm_analytics.dim_date (date_key),
    ADD CONSTRAINT fk_fact_valuation_club
        FOREIGN KEY (club_key_at_valuation) REFERENCES tm_analytics.dim_club (club_key);

CREATE INDEX ix_fact_valuation_player_date_desc
    ON tm_analytics.fact_player_valuation (source_player_id, valuation_date DESC);
CREATE INDEX ix_fact_valuation_player_key_date_desc
    ON tm_analytics.fact_player_valuation (player_key, valuation_date DESC);
CREATE INDEX ix_fact_valuation_club_date
    ON tm_analytics.fact_player_valuation (club_key_at_valuation, valuation_date);

CREATE TABLE tm_analytics.fact_transfer AS
SELECT
    t._source_row_number AS transfer_key,
    dp.player_key,
    t.player_id::BIGINT AS source_player_id,
    t.player_name AS source_player_name,
    t.transfer_date::DATE,
    TO_CHAR(t.transfer_date::DATE, 'YYYYMMDD')::INTEGER AS date_key,
    t.transfer_season,
    fc.club_key AS from_club_key,
    CASE WHEN t.from_club_id ~ '^[0-9]+$' THEN t.from_club_id::BIGINT END AS source_from_club_id,
    t.from_club_name AS source_from_club_name,
    tc.club_key AS to_club_key,
    CASE WHEN t.to_club_id ~ '^[0-9]+$' THEN t.to_club_id::BIGINT END AS source_to_club_id,
    t.to_club_name AS source_to_club_name,
    CASE WHEN t.transfer_fee ~ '^-?[0-9]+(?:\.[0-9]+)?$' THEN ROUND(t.transfer_fee::NUMERIC)::BIGINT END AS transfer_fee_eur,
    CASE
        WHEN t.transfer_fee IS NULL THEN 'unknown_or_undisclosed'
        WHEN t.transfer_fee !~ '^-?[0-9]+(?:\.[0-9]+)?$' THEN 'invalid_format'
        WHEN t.transfer_fee::NUMERIC < 0 THEN 'invalid_negative'
        WHEN t.transfer_fee::NUMERIC = 0 THEN 'recorded_zero_ambiguous'
        ELSE 'numeric_fee'
    END AS fee_status,
    t.transfer_fee ~ '^[0-9]+(?:\.[0-9]+)?$'
        AND t.transfer_fee::NUMERIC > 0 AS is_fee_analysis_eligible,
    CASE WHEN t.market_value_in_eur ~ '^[0-9]+(?:\.[0-9]+)?$' THEN ROUND(t.market_value_in_eur::NUMERIC)::BIGINT END AS source_reported_market_value_eur,
    mv.valuation_key AS matched_valuation_key,
    mv.valuation_date AS matched_valuation_date,
    mv.market_value_eur AS market_value_at_transfer_eur,
    CASE WHEN mv.valuation_date IS NOT NULL THEN t.transfer_date::DATE - mv.valuation_date END AS valuation_lag_days,
    CASE
        WHEN mv.valuation_date IS NULL THEN 'no_prior_valuation'
        WHEN t.transfer_date::DATE - mv.valuation_date = 0 THEN 'same_day'
        WHEN t.transfer_date::DATE - mv.valuation_date <= 30 THEN 'within_30_days'
        WHEN t.transfer_date::DATE - mv.valuation_date <= 90 THEN 'within_90_days'
        WHEN t.transfer_date::DATE - mv.valuation_date <= 365 THEN 'within_365_days'
        ELSE 'stale_over_365_days'
    END AS valuation_match_status,
    CASE
        WHEN t.transfer_fee ~ '^[0-9]+(?:\.[0-9]+)?$'
         AND t.transfer_fee::NUMERIC > 0
         AND mv.market_value_eur > 0
        THEN ROUND(t.transfer_fee::NUMERIC)::BIGINT - mv.market_value_eur
    END AS fee_vs_market_value_eur,
    CASE
        WHEN t.transfer_fee ~ '^[0-9]+(?:\.[0-9]+)?$'
         AND t.transfer_fee::NUMERIC > 0
         AND mv.market_value_eur > 0
        THEN ROUND((t.transfer_fee::NUMERIC - mv.market_value_eur) / mv.market_value_eur * 100, 4)
    END AS fee_premium_pct,
    t.transfer_date::DATE > p.analysis_cutoff_date AS is_after_analysis_cutoff,
    t.transfer_date::DATE <= p.analysis_cutoff_date AS is_historical_analysis_eligible,
    dp.player_key IS NOT NULL AS has_player_dimension,
    fc.club_key IS NOT NULL AS has_from_club_dimension,
    tc.club_key IS NOT NULL AS has_to_club_dimension,
    'not_available_in_source'::TEXT AS transfer_type_status
FROM tm_raw.transfers t
CROSS JOIN tm_analytics.project_parameters p
LEFT JOIN tm_analytics.dim_player dp
    ON t.player_id ~ '^[0-9]+$' AND t.player_id::BIGINT = dp.player_key
LEFT JOIN tm_analytics.dim_club fc
    ON t.from_club_id ~ '^[0-9]+$' AND t.from_club_id::BIGINT = fc.club_key
LEFT JOIN tm_analytics.dim_club tc
    ON t.to_club_id ~ '^[0-9]+$' AND t.to_club_id::BIGINT = tc.club_key
LEFT JOIN LATERAL (
    SELECT
        v.valuation_key,
        v.valuation_date,
        v.market_value_eur
    FROM tm_analytics.fact_player_valuation v
    WHERE v.source_player_id = t.player_id::BIGINT
      AND v.valuation_date <= t.transfer_date::DATE
      AND v.is_valid_valuation
    ORDER BY v.valuation_date DESC
    LIMIT 1
) mv ON TRUE
WHERE t.player_id ~ '^[0-9]+$'
  AND t.transfer_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$';

ALTER TABLE tm_analytics.fact_transfer
    ADD CONSTRAINT pk_fact_transfer PRIMARY KEY (transfer_key),
    ADD CONSTRAINT fk_fact_transfer_player
        FOREIGN KEY (player_key) REFERENCES tm_analytics.dim_player (player_key),
    ADD CONSTRAINT fk_fact_transfer_date
        FOREIGN KEY (date_key) REFERENCES tm_analytics.dim_date (date_key),
    ADD CONSTRAINT fk_fact_transfer_from_club
        FOREIGN KEY (from_club_key) REFERENCES tm_analytics.dim_club (club_key),
    ADD CONSTRAINT fk_fact_transfer_to_club
        FOREIGN KEY (to_club_key) REFERENCES tm_analytics.dim_club (club_key),
    ADD CONSTRAINT ck_fact_transfer_valuation_not_after_transfer
        CHECK (matched_valuation_date IS NULL OR matched_valuation_date <= transfer_date);

CREATE INDEX ix_fact_transfer_player_date
    ON tm_analytics.fact_transfer (player_key, transfer_date);
CREATE INDEX ix_fact_transfer_from_club
    ON tm_analytics.fact_transfer (from_club_key);
CREATE INDEX ix_fact_transfer_to_club
    ON tm_analytics.fact_transfer (to_club_key);
CREATE INDEX ix_fact_transfer_historical_fee
    ON tm_analytics.fact_transfer (is_historical_analysis_eligible, is_fee_analysis_eligible);

ANALYZE tm_analytics.fact_player_appearance;
ANALYZE tm_analytics.fact_player_valuation;
ANALYZE tm_analytics.fact_transfer;
