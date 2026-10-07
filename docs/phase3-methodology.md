# Phase 3: KPI and exploratory analysis methodology

Phase 3 builds reproducible KPI, peer-group, age-cohort, and transfer-outcome
models in PostgreSQL schema `tm_analysis`. It consumes the time-aligned Phase 2
facts and does not modify `tm_raw` or `tm_analytics`.

## Reproduce Phase 3

Run Phase 2 validation first, then:

```powershell
.\.venv\Scripts\python src\inspect_phase3_inputs.py
.\.venv\Scripts\python src\build_phase3.py --replace
.\.venv\Scripts\python src\validate_phase3.py
.\.venv\Scripts\python src\summarize_phase3.py
.\.venv\Scripts\python src\verify_phase3.py
.\.venv\Scripts\python -m unittest discover -s tests -v
```

`--replace` drops and recreates only `tm_analysis`. Phase 3 must be rebuilt after
rebuilding `tm_analytics` because its views depend on Phase 2 dimensions.

## Model outputs

| Table | Grain | Purpose |
| --- | --- | --- |
| `methodology_parameters` | one methodology version | Reproducible thresholds and horizons |
| `position_metric_weight` | methodology, position, metric | Versioned performance weights |
| `age_band_definition` | one age band | Ordered cohort definitions |
| `fact_player_season_kpi` | player, competition, season | KPI layer and eligibility reason |
| `fact_value_efficiency` | scored player, competition, season | Standardized metrics, scores, ranks, and required context |
| `agg_peer_group_benchmark` | competition, season, position | Market and performance benchmarks plus Spearman association |
| `fact_player_value_development` | player, season | One representative row per player-season and consecutive-season value change |
| `agg_market_value_by_age` | competition, season, position, age band | Median, quartiles, totals, dates, and sample size |
| `fact_transfer_value_outcome` | transfer, horizon | Time-aligned market-value outcomes at 6, 12, and 24 months |
| `agg_transfer_value_outcome` | horizon, fee status | Outcome coverage and descriptive summaries |

Convenience views enrich the score, development, and transfer facts with names.
The React dashboard API should still use shared dimensions and avoid ambiguous
fact-to-fact relationships.

## Score eligibility

A player-season is scored only when all conditions hold:

- the player is outfield;
- the row belongs to the confirmed five-league, 2023-2025 scope;
- minutes played are at least 900;
- aligned season-end market value is positive;
- the valuation is no more than 365 days before the competition-season end;
- required per-90 and start-rate inputs are available; and
- the peer group contains at least 30 eligible players.

The implemented peer group is `season x competition x position_group`. All 45
current peer groups pass the minimum sample rule, with 65-136 players. The model
scores 4,392 player-seasons. Twenty otherwise eligible Phase 2 rows are excluded
because their valuation lag exceeds 365 days.

## Performance metrics and weights

| Position | Goals/90 | Assists/90 | Minutes | Start rate | Cards/90 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Defender | 10% | 10% | 30% | 30% | 20% lower-is-better |
| Midfielder | 25% | 30% | 15% | 15% | 15% lower-is-better |
| Forward | 45% | 25% | 10% | 10% | 10% lower-is-better |

Minutes and start rate are proxies for observed availability and sustained
selection, not direct measures of quality. This limitation is especially
important for defenders because tackles, interceptions, aerial duels, expected
goals, and other role-specific events are unavailable. Goalkeepers remain
excluded until reliable goalkeeper metrics exist.

## Standardization and score

Within each peer group:

1. Winsorize each input and log market value at the 5th and 95th percentiles.
2. Standardize every metric with the sample mean and sample standard deviation.
3. Apply position weights; reverse the sign of cards per 90.
4. Standardize the weighted performance composite again to form Performance
   Z-Score.
5. Standardize `ln(1 + market_value_eur)` to form Market Value Z-Score.
6. Calculate:

```text
Value Efficiency Score = Performance Z-Score - Market Value Z-Score
```

The top cumulative 10% receive the label `high_relative_efficiency`. That label
is an exploration aid, not a claim that the player is objectively undervalued
or should be recruited. Every score retains minutes, sample size, season,
competition, position, market value, valuation date, and valuation lag.

## Age and value development

Age bands are Under 20, 20-22, 23-25, 26-28, 29-31, 32+, and Unknown. Age is
calculated at the aligned season-end reference date. One eligible row has no
valid birth date and remains Unknown; age is never imputed.

For players appearing in more than one selected competition in a season, the
development fact chooses the competition with the most minutes as the single
representative row. Value change is calculated only across consecutive seasons
when both values pass the freshness and positivity rules. The result is an
association with age, not proof that aging caused the change.

## Post-transfer value outcomes

For every historical transfer, Phase 3 creates 6-, 12-, and 24-month targets.
The outcome uses the latest valuation after the transfer and on or before the
target date. An outcome is eligible only if:

- the horizon is mature relative to the valuation snapshot (`2026-06-12`);
- the baseline value is positive and no more than 365 days old; and
- the post value is positive and no more than 90 days before the target.

The table retains whether the post-valuation club matches the destination club.
A later move does not delete the observation, so users must apply this status
when evaluating a specific destination club. Market-value change is not
sporting or financial ROI, and the summaries are exposed with coverage counts
because survivorship and missingness are material.

## Evidence

- `reports/analysis/phase3_validation.csv`: 51 automated checks.
- `reports/analysis/phase3_top_efficiency.csv`: top ten rows per peer group with
  mandatory context.
- `reports/analysis/phase3_peer_group_summary.csv`: peer benchmarks and
  performance/value associations.
- `reports/analysis/phase3_age_summary.csv`: cohort sample sizes and value
  distribution.
- `reports/analysis/phase3_transfer_outcome_summary.csv`: coverage by horizon
  and fee status.
- `reports/analysis/phase3-analysis.md`: reproducible descriptive summary and
  interpretation guardrails.
