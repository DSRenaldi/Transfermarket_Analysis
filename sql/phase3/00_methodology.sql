CREATE SCHEMA IF NOT EXISTS tm_analysis;

CREATE TABLE tm_analysis.methodology_parameters (
    methodology_version TEXT PRIMARY KEY,
    minimum_minutes INTEGER NOT NULL CHECK (minimum_minutes > 0),
    maximum_season_valuation_lag_days INTEGER NOT NULL CHECK (maximum_season_valuation_lag_days > 0),
    minimum_peer_group_size INTEGER NOT NULL CHECK (minimum_peer_group_size >= 2),
    winsor_lower_percentile NUMERIC(5,4) NOT NULL CHECK (winsor_lower_percentile BETWEEN 0 AND 1),
    winsor_upper_percentile NUMERIC(5,4) NOT NULL CHECK (winsor_upper_percentile BETWEEN 0 AND 1),
    maximum_transfer_target_lag_days INTEGER NOT NULL CHECK (maximum_transfer_target_lag_days > 0),
    transfer_horizons_months INTEGER[] NOT NULL,
    created_at_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes TEXT NOT NULL
);

INSERT INTO tm_analysis.methodology_parameters (
    methodology_version,
    minimum_minutes,
    maximum_season_valuation_lag_days,
    minimum_peer_group_size,
    winsor_lower_percentile,
    winsor_upper_percentile,
    maximum_transfer_target_lag_days,
    transfer_horizons_months,
    notes
)
SELECT
    'v1.0',
    p.minimum_minutes,
    365,
    30,
    0.05,
    0.95,
    90,
    ARRAY[6, 12, 24]::INTEGER[],
    'Exploratory association model; not a causal estimate or automatic recruitment recommendation.'
FROM tm_analytics.project_parameters p
WHERE p.parameter_set_id = 1;

CREATE TABLE tm_analysis.position_metric_weight (
    methodology_version TEXT NOT NULL,
    position_group TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_weight NUMERIC(6,5) NOT NULL CHECK (metric_weight >= 0 AND metric_weight <= 1),
    direction TEXT NOT NULL CHECK (direction IN ('higher_is_better', 'lower_is_better')),
    rationale TEXT NOT NULL,
    PRIMARY KEY (methodology_version, position_group, metric_name)
);

INSERT INTO tm_analysis.position_metric_weight VALUES
    ('v1.0', 'Defender',   'goals_per_90',    0.10, 'higher_is_better', 'Small attacking contribution component; not the primary defender signal.'),
    ('v1.0', 'Defender',   'assists_per_90',  0.10, 'higher_is_better', 'Small creative contribution component.'),
    ('v1.0', 'Defender',   'minutes_played',  0.30, 'higher_is_better', 'Observed availability and sustained selection proxy.'),
    ('v1.0', 'Defender',   'start_rate',      0.30, 'higher_is_better', 'Observed consistency of selection proxy.'),
    ('v1.0', 'Defender',   'cards_per_90',    0.20, 'lower_is_better',  'Discipline proxy; lower card rate scores higher.'),
    ('v1.0', 'Midfielder', 'goals_per_90',    0.25, 'higher_is_better', 'Scoring contribution.'),
    ('v1.0', 'Midfielder', 'assists_per_90',  0.30, 'higher_is_better', 'Creative contribution.'),
    ('v1.0', 'Midfielder', 'minutes_played',  0.15, 'higher_is_better', 'Observed availability and sustained selection proxy.'),
    ('v1.0', 'Midfielder', 'start_rate',      0.15, 'higher_is_better', 'Observed consistency of selection proxy.'),
    ('v1.0', 'Midfielder', 'cards_per_90',    0.15, 'lower_is_better',  'Discipline proxy; lower card rate scores higher.'),
    ('v1.0', 'Forward',    'goals_per_90',    0.45, 'higher_is_better', 'Primary available scoring-output signal.'),
    ('v1.0', 'Forward',    'assists_per_90',  0.25, 'higher_is_better', 'Creative contribution.'),
    ('v1.0', 'Forward',    'minutes_played',  0.10, 'higher_is_better', 'Observed availability and sustained selection proxy.'),
    ('v1.0', 'Forward',    'start_rate',      0.10, 'higher_is_better', 'Observed consistency of selection proxy.'),
    ('v1.0', 'Forward',    'cards_per_90',    0.10, 'lower_is_better',  'Discipline proxy; lower card rate scores higher.');

CREATE TABLE tm_analysis.age_band_definition (
    age_band TEXT PRIMARY KEY,
    age_band_order SMALLINT NOT NULL UNIQUE,
    minimum_age SMALLINT,
    maximum_age SMALLINT,
    CHECK (minimum_age IS NULL OR maximum_age IS NULL OR minimum_age <= maximum_age)
);

INSERT INTO tm_analysis.age_band_definition VALUES
    ('Under 20', 1, NULL, 19),
    ('20-22',    2, 20, 22),
    ('23-25',    3, 23, 25),
    ('26-28',    4, 26, 28),
    ('29-31',    5, 29, 31),
    ('32+',      6, 32, NULL),
    ('Unknown',  7, NULL, NULL);
