CREATE SCHEMA IF NOT EXISTS tm_analytics;

CREATE TABLE tm_analytics.project_parameters (
    parameter_set_id SMALLINT PRIMARY KEY CHECK (parameter_set_id = 1),
    analysis_cutoff_date DATE NOT NULL,
    minimum_minutes INTEGER NOT NULL CHECK (minimum_minutes > 0),
    v1_competition_keys TEXT[] NOT NULL,
    v1_season_keys INTEGER[] NOT NULL,
    created_at_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO tm_analytics.project_parameters (
    parameter_set_id,
    analysis_cutoff_date,
    minimum_minutes,
    v1_competition_keys,
    v1_season_keys
)
SELECT
    1,
    MAX(date::date),
    900,
    ARRAY['GB1', 'ES1', 'IT1', 'L1', 'FR1']::TEXT[],
    ARRAY[2023, 2024, 2025]::INTEGER[]
FROM tm_raw.games;

CREATE TABLE tm_analytics.source_snapshot (
    source_table TEXT PRIMARY KEY,
    min_business_date DATE,
    max_business_date DATE,
    row_count BIGINT NOT NULL,
    recorded_at_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO tm_analytics.source_snapshot (source_table, min_business_date, max_business_date, row_count)
SELECT 'games', MIN(date::date), MAX(date::date), COUNT(*) FROM tm_raw.games
UNION ALL
SELECT 'appearances', MIN(date::date), MAX(date::date), COUNT(*) FROM tm_raw.appearances
UNION ALL
SELECT 'player_valuations', MIN(date::date), MAX(date::date), COUNT(*) FROM tm_raw.player_valuations
UNION ALL
SELECT 'game_events', MIN(date::date), MAX(date::date), COUNT(*) FROM tm_raw.game_events
UNION ALL
SELECT 'game_lineups', MIN(date::date), MAX(date::date), COUNT(*) FROM tm_raw.game_lineups
UNION ALL
SELECT 'transfers', MIN(transfer_date::date), MAX(transfer_date::date), COUNT(*) FROM tm_raw.transfers;

CREATE TABLE tm_analytics.dim_competition AS
WITH combined AS (
    SELECT
        c.competition_id AS competition_key,
        c.competition_code,
        c.name AS competition_name,
        c.sub_type,
        c.type AS source_type,
        CASE WHEN c.country_id ~ '^[0-9]+$' THEN c.country_id::BIGINT END AS country_id,
        c.country_name,
        c.domestic_league_code,
        c.confederation,
        CASE WHEN c.total_clubs ~ '^[0-9]+$' THEN c.total_clubs::INTEGER END AS total_clubs,
        c.url,
        FALSE AS is_reference_override,
        NULL::TEXT AS override_evidence
    FROM tm_raw.competitions c
    UNION ALL
    SELECT
        o.competition_id,
        o.competition_id,
        o.competition_name,
        NULL,
        o.source_type,
        NULL::BIGINT,
        o.country_name,
        NULL,
        CASE WHEN o.country_name = 'International' THEN 'International' END,
        NULL::INTEGER,
        NULL,
        TRUE,
        o.evidence
    FROM tm_ref.competition_id_overrides o
    WHERE NOT EXISTS (
        SELECT 1
        FROM tm_raw.competitions c
        WHERE c.competition_id = o.competition_id
    )
)
SELECT
    c.competition_key,
    c.competition_code,
    c.competition_name,
    c.sub_type,
    c.source_type,
    COALESCE(o.competition_group, m.competition_group, 'Unknown') AS competition_group,
    c.country_id,
    c.country_name,
    c.domestic_league_code,
    c.confederation,
    c.total_clubs,
    c.url,
    c.is_reference_override,
    c.override_evidence,
    c.competition_key = ANY(p.v1_competition_keys) AS is_v1_competition
FROM combined c
CROSS JOIN tm_analytics.project_parameters p
LEFT JOIN tm_ref.competition_id_overrides o
    ON c.competition_key = o.competition_id
LEFT JOIN tm_ref.competition_type_mapping m
    ON COALESCE(c.source_type, '') = COALESCE(m.source_type, '');

ALTER TABLE tm_analytics.dim_competition
    ADD CONSTRAINT pk_dim_competition PRIMARY KEY (competition_key);

CREATE TABLE tm_analytics.dim_club AS
SELECT
    c.club_id::BIGINT AS club_key,
    c.club_id::BIGINT AS source_club_id,
    c.club_code,
    c.name AS club_name,
    dc.competition_key AS domestic_competition_key,
    c.domestic_competition_id AS source_domestic_competition_id,
    CASE WHEN c.squad_size ~ '^[0-9]+$' THEN c.squad_size::INTEGER END AS profile_squad_size,
    CASE WHEN c.average_age ~ '^[0-9]+(?:\.[0-9]+)?$' THEN c.average_age::NUMERIC(5,2) END AS profile_average_age,
    CASE WHEN c.foreigners_number ~ '^[0-9]+$' THEN c.foreigners_number::INTEGER END AS profile_foreigners,
    CASE WHEN c.national_team_players ~ '^[0-9]+$' THEN c.national_team_players::INTEGER END AS profile_national_team_players,
    c.stadium_name,
    CASE WHEN c.stadium_seats ~ '^[0-9]+$' THEN c.stadium_seats::INTEGER END AS stadium_seats,
    c.net_transfer_record AS source_net_transfer_record,
    c.coach_name AS profile_coach_name,
    CASE WHEN c.last_season ~ '^[0-9]+$' THEN c.last_season::INTEGER END AS profile_last_season,
    c.url,
    dc.competition_key IS NOT NULL AS has_domestic_competition_dimension
FROM tm_raw.clubs c
LEFT JOIN tm_analytics.dim_competition dc
    ON c.domestic_competition_id = dc.competition_key
WHERE c.club_id ~ '^[0-9]+$';

ALTER TABLE tm_analytics.dim_club
    ADD CONSTRAINT pk_dim_club PRIMARY KEY (club_key),
    ADD CONSTRAINT fk_dim_club_domestic_competition
        FOREIGN KEY (domestic_competition_key)
        REFERENCES tm_analytics.dim_competition (competition_key);

CREATE INDEX ix_dim_club_domestic_competition
    ON tm_analytics.dim_club (domestic_competition_key);

CREATE TABLE tm_analytics.dim_player AS
SELECT
    p.player_id::BIGINT AS player_key,
    p.player_id::BIGINT AS source_player_id,
    p.first_name,
    p.last_name,
    p.name AS player_name,
    p.player_code,
    CASE
        WHEN p.date_of_birth ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
        THEN LEFT(p.date_of_birth, 10)::DATE
    END AS date_of_birth,
    p.country_of_birth,
    p.city_of_birth,
    p.country_of_citizenship,
    p.position AS source_position,
    p.sub_position,
    COALESCE(pm.position_group, 'Unknown') AS position_group,
    p.foot,
    CASE
        WHEN p.height_in_cm ~ '^[0-9]+(?:\.[0-9]+)?$'
         AND p.height_in_cm::NUMERIC BETWEEN 100 AND 230
        THEN ROUND(p.height_in_cm::NUMERIC)::SMALLINT
    END AS height_cm,
    CASE
        WHEN p.height_in_cm IS NULL THEN 'missing'
        WHEN p.height_in_cm !~ '^[0-9]+(?:\.[0-9]+)?$' THEN 'invalid_format'
        WHEN p.height_in_cm::NUMERIC NOT BETWEEN 100 AND 230 THEN 'out_of_range'
        ELSE 'valid'
    END AS height_quality_status,
    CASE
        WHEN p.contract_expiration_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
        THEN LEFT(p.contract_expiration_date, 10)::DATE
    END AS contract_expiration_date,
    p.agent_name,
    p.image_url,
    CASE WHEN p.international_caps ~ '^[0-9]+$' THEN p.international_caps::INTEGER END AS international_caps,
    CASE WHEN p.international_goals ~ '^[0-9]+$' THEN p.international_goals::INTEGER END AS international_goals,
    CASE WHEN p.current_national_team_id ~ '^[0-9]+$' THEN p.current_national_team_id::BIGINT END AS current_national_team_id,
    dc.club_key AS current_club_key,
    CASE WHEN p.current_club_id ~ '^[0-9]+$' THEN p.current_club_id::BIGINT END AS source_current_club_id,
    p.current_club_name AS source_current_club_name,
    p.current_club_domestic_competition_id,
    CASE WHEN p.last_season ~ '^[0-9]+$' THEN p.last_season::INTEGER END AS profile_last_season,
    CASE WHEN p.market_value_in_eur ~ '^[0-9]+(?:\.[0-9]+)?$' THEN ROUND(p.market_value_in_eur::NUMERIC)::BIGINT END AS undated_profile_market_value_eur,
    CASE WHEN p.highest_market_value_in_eur ~ '^[0-9]+(?:\.[0-9]+)?$' THEN ROUND(p.highest_market_value_in_eur::NUMERIC)::BIGINT END AS highest_market_value_eur,
    p.url,
    COALESCE(pm.position_group, 'Unknown') <> 'Goalkeeper' AS is_outfield,
    pm.position_group IS NOT NULL AS has_position_mapping,
    dc.club_key IS NOT NULL AS has_current_club_dimension
FROM tm_raw.players p
LEFT JOIN tm_ref.position_mapping pm
    ON p.position = pm.source_position
   AND COALESCE(p.sub_position, '') = COALESCE(pm.source_sub_position, '')
LEFT JOIN tm_analytics.dim_club dc
    ON p.current_club_id ~ '^[0-9]+$'
   AND p.current_club_id::BIGINT = dc.club_key
WHERE p.player_id ~ '^[0-9]+$';

ALTER TABLE tm_analytics.dim_player
    ADD CONSTRAINT pk_dim_player PRIMARY KEY (player_key),
    ADD CONSTRAINT fk_dim_player_current_club
        FOREIGN KEY (current_club_key)
        REFERENCES tm_analytics.dim_club (club_key);

CREATE INDEX ix_dim_player_position_group
    ON tm_analytics.dim_player (position_group);
CREATE INDEX ix_dim_player_current_club
    ON tm_analytics.dim_player (current_club_key);

CREATE TABLE tm_analytics.dim_date AS
WITH bounds AS (
    SELECT
        LEAST(
            (SELECT MIN(date::date) FROM tm_raw.games),
            (SELECT MIN(date::date) FROM tm_raw.player_valuations),
            (SELECT MIN(transfer_date::date) FROM tm_raw.transfers)
        ) AS min_date,
        GREATEST(
            (SELECT MAX(date::date) FROM tm_raw.games),
            (SELECT MAX(date::date) FROM tm_raw.player_valuations),
            (SELECT MAX(transfer_date::date) FROM tm_raw.transfers)
        ) AS max_date
), dates AS (
    SELECT generate_series(min_date, max_date, INTERVAL '1 day')::DATE AS full_date
    FROM bounds
)
SELECT
    TO_CHAR(full_date, 'YYYYMMDD')::INTEGER AS date_key,
    full_date,
    EXTRACT(YEAR FROM full_date)::SMALLINT AS calendar_year,
    EXTRACT(QUARTER FROM full_date)::SMALLINT AS calendar_quarter,
    EXTRACT(MONTH FROM full_date)::SMALLINT AS month_number,
    TO_CHAR(full_date, 'Mon') AS month_name_short,
    EXTRACT(DAY FROM full_date)::SMALLINT AS day_of_month,
    EXTRACT(ISODOW FROM full_date)::SMALLINT AS iso_day_of_week,
    TO_CHAR(full_date, 'Dy') AS day_name_short,
    EXTRACT(WEEK FROM full_date)::SMALLINT AS iso_week,
    full_date >= DATE_TRUNC('year', full_date)::DATE AS is_valid_date
FROM dates;

ALTER TABLE tm_analytics.dim_date
    ADD CONSTRAINT pk_dim_date PRIMARY KEY (date_key),
    ADD CONSTRAINT uq_dim_date_full_date UNIQUE (full_date);

CREATE TABLE tm_analytics.dim_season AS
SELECT
    g.season::INTEGER AS season_key,
    CONCAT(g.season, '/', RIGHT((g.season::INTEGER + 1)::TEXT, 2)) AS season_label,
    MIN(g.date::DATE) AS first_observed_game_date,
    MAX(g.date::DATE) AS last_observed_game_date,
    COUNT(*) AS observed_game_count,
    g.season::INTEGER = ANY(p.v1_season_keys) AS is_v1_season
FROM tm_raw.games g
CROSS JOIN tm_analytics.project_parameters p
WHERE g.season ~ '^[0-9]{4}$'
GROUP BY g.season, p.v1_season_keys;

ALTER TABLE tm_analytics.dim_season
    ADD CONSTRAINT pk_dim_season PRIMARY KEY (season_key);

CREATE TABLE tm_analytics.dim_game AS
WITH appearance_games AS (
    SELECT DISTINCT game_id
    FROM tm_raw.appearances
)
SELECT
    g.game_id::BIGINT AS game_key,
    g.game_id::BIGINT AS source_game_id,
    dc.competition_key,
    g.competition_id AS source_competition_id,
    g.season::INTEGER AS season_key,
    g.date::DATE AS game_date,
    TO_CHAR(g.date::DATE, 'YYYYMMDD')::INTEGER AS date_key,
    g.round AS round_name,
    hc.club_key AS home_club_key,
    CASE WHEN g.home_club_id ~ '^[0-9]+$' THEN g.home_club_id::BIGINT END AS source_home_club_id,
    ac.club_key AS away_club_key,
    CASE WHEN g.away_club_id ~ '^[0-9]+$' THEN g.away_club_id::BIGINT END AS source_away_club_id,
    g.home_club_name,
    g.away_club_name,
    g.home_club_goals::SMALLINT AS home_goals,
    g.away_club_goals::SMALLINT AS away_goals,
    CASE WHEN g.home_club_position ~ '^[0-9]+$' THEN g.home_club_position::SMALLINT END AS home_league_position,
    CASE WHEN g.away_club_position ~ '^[0-9]+$' THEN g.away_club_position::SMALLINT END AS away_league_position,
    g.home_club_manager_name,
    g.away_club_manager_name,
    g.stadium,
    CASE WHEN g.attendance ~ '^[0-9]+$' THEN g.attendance::INTEGER END AS attendance,
    g.referee,
    g.home_club_formation,
    g.away_club_formation,
    g.aggregate AS aggregate_score,
    dc.competition_group,
    g.url,
    ag.game_id IS NOT NULL AS has_appearance_data,
    hc.club_key IS NOT NULL AND ac.club_key IS NOT NULL AS has_both_club_dimensions,
    dc.competition_key = ANY(p.v1_competition_keys)
        AND g.season::INTEGER = ANY(p.v1_season_keys) AS is_v1_scope
FROM tm_raw.games g
CROSS JOIN tm_analytics.project_parameters p
JOIN tm_analytics.dim_competition dc
    ON g.competition_id = dc.competition_key
LEFT JOIN tm_analytics.dim_club hc
    ON g.home_club_id ~ '^[0-9]+$' AND g.home_club_id::BIGINT = hc.club_key
LEFT JOIN tm_analytics.dim_club ac
    ON g.away_club_id ~ '^[0-9]+$' AND g.away_club_id::BIGINT = ac.club_key
LEFT JOIN appearance_games ag
    ON g.game_id = ag.game_id
WHERE g.game_id ~ '^[0-9]+$'
  AND g.season ~ '^[0-9]{4}$'
  AND g.date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$';

ALTER TABLE tm_analytics.dim_game
    ADD CONSTRAINT pk_dim_game PRIMARY KEY (game_key),
    ADD CONSTRAINT fk_dim_game_competition
        FOREIGN KEY (competition_key) REFERENCES tm_analytics.dim_competition (competition_key),
    ADD CONSTRAINT fk_dim_game_season
        FOREIGN KEY (season_key) REFERENCES tm_analytics.dim_season (season_key),
    ADD CONSTRAINT fk_dim_game_date
        FOREIGN KEY (date_key) REFERENCES tm_analytics.dim_date (date_key),
    ADD CONSTRAINT fk_dim_game_home_club
        FOREIGN KEY (home_club_key) REFERENCES tm_analytics.dim_club (club_key),
    ADD CONSTRAINT fk_dim_game_away_club
        FOREIGN KEY (away_club_key) REFERENCES tm_analytics.dim_club (club_key);

CREATE INDEX ix_dim_game_competition_season
    ON tm_analytics.dim_game (competition_key, season_key);
CREATE INDEX ix_dim_game_date
    ON tm_analytics.dim_game (game_date);

CREATE TABLE tm_analytics.dim_competition_season AS
SELECT
    g.competition_key,
    g.season_key,
    MIN(g.game_date) AS season_start_date,
    MAX(g.game_date) AS season_end_date,
    COUNT(*) AS game_count,
    COUNT(*) FILTER (WHERE g.has_appearance_data) AS games_with_appearances,
    ROUND(
        COUNT(*) FILTER (WHERE g.has_appearance_data)::NUMERIC
        / NULLIF(COUNT(*), 0) * 100,
        4
    ) AS appearance_game_coverage_pct,
    CASE
        WHEN COUNT(*) FILTER (WHERE g.has_appearance_data) = COUNT(*) THEN 'FULL'
        WHEN COUNT(*) FILTER (WHERE g.has_appearance_data)::NUMERIC / NULLIF(COUNT(*), 0) >= 0.99 THEN 'HIGH'
        ELSE 'REVIEW'
    END AS appearance_coverage_status,
    BOOL_OR(g.is_v1_scope) AS is_v1_scope
FROM tm_analytics.dim_game g
GROUP BY g.competition_key, g.season_key;

ALTER TABLE tm_analytics.dim_competition_season
    ADD CONSTRAINT pk_dim_competition_season PRIMARY KEY (competition_key, season_key),
    ADD CONSTRAINT fk_dim_competition_season_competition
        FOREIGN KEY (competition_key) REFERENCES tm_analytics.dim_competition (competition_key),
    ADD CONSTRAINT fk_dim_competition_season_season
        FOREIGN KEY (season_key) REFERENCES tm_analytics.dim_season (season_key);
