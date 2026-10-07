# Phase 3 Analysis Summary

Generated from methodology version `v1.0` in PostgreSQL schema `tm_analysis`.

## Population and peer groups

- Scored player-seasons: **4,392**.
- Peer groups (`season x competition x position_group`): **45**.
- Observed peer-group size: **65-136** players.
- Rows in the exploratory high-relative-efficiency band: **463**.
- Goalkeepers are excluded because goalkeeper-specific performance metrics are
  unavailable.

The Spearman association between performance score and market value ranges from
**0.0670** to **0.7218** across peer groups, with a median of
**0.4156**. This is an association, not evidence that performance causes
market value. The top ten players hold between **19.93%** and
**58.10%** of peer-group value; the median concentration is
**37.55%**.

## Market value by age and position

| Position | Age band | Player-seasons | Median value (EUR) | Median efficiency |
| --- | --- | --- | --- | --- |
| Defender | Under 20 | 30 | 15000000 | -1.136 |
| Defender | 20-22 | 229 | 12000000 | -0.613 |
| Defender | 23-25 | 473 | 10000000 | -0.284 |
| Defender | 26-28 | 501 | 10000000 | -0.085 |
| Defender | 29-31 | 327 | 5000000 | 0.284 |
| Defender | 32+ | 258 | 2000000 | 1.126 |
| Forward | Under 20 | 32 | 29000000 | -0.987 |
| Forward | 20-22 | 163 | 18000000 | -0.486 |
| Forward | 23-25 | 372 | 15500000 | -0.216 |
| Forward | 26-28 | 299 | 14000000 | -0.002 |
| Forward | 29-31 | 173 | 7000000 | 0.300 |
| Forward | 32+ | 117 | 3000000 | 1.247 |
| Midfielder | Under 20 | 29 | 18000000 | -0.657 |
| Midfielder | 20-22 | 252 | 15000000 | -0.438 |
| Midfielder | 23-25 | 339 | 15000000 | -0.178 |
| Midfielder | 26-28 | 380 | 10000000 | -0.093 |
| Midfielder | 29-31 | 273 | 7000000 | 0.449 |
| Midfielder | 32+ | 144 | 3000000 | 0.924 |
| Midfielder | Unknown | 1 | 300000 | 0.582 |

These are cross-sectional player-season comparisons. Repeated observations of
the same player and differences among clubs, roles, and competitions prevent a
causal interpretation of the age pattern.

## Consecutive-season value development

| Position | Age band | Comparisons | Median change (EUR) | Median growth % |
| --- | --- | --- | --- | --- |
| Defender | Under 20 | 5 | 15000000 | 140.00 |
| Defender | 20-22 | 57 | 5000000 | 33.33 |
| Defender | 23-25 | 189 | 2000000 | 18.18 |
| Defender | 26-28 | 251 | 0 | 0.00 |
| Defender | 29-31 | 151 | -1000000 | -16.67 |
| Defender | 32+ | 140 | -1000000 | -25.00 |
| Forward | Under 20 | 4 | 30000000 | 103.33 |
| Forward | 20-22 | 38 | 9000000 | 40.00 |
| Forward | 23-25 | 168 | 2000000 | 11.56 |
| Forward | 26-28 | 126 | 0 | 0.00 |
| Forward | 29-31 | 85 | -1500000 | -18.18 |
| Forward | 32+ | 56 | -1000000 | -22.50 |
| Midfielder | Under 20 | 2 | 10000000 | 33.33 |
| Midfielder | 20-22 | 82 | 5000000 | 42.26 |
| Midfielder | 23-25 | 146 | 2250000 | 20.00 |
| Midfielder | 26-28 | 177 | 0 | 0.00 |
| Midfielder | 29-31 | 137 | -2000000 | -20.00 |
| Midfielder | 32+ | 72 | -1100000 | -28.57 |

Only consecutive seasons with positive, time-aligned values no more than 365
days old are included. A change in estimated market value is not financial ROI.

## Post-transfer market-value coverage

| Horizon (months) | Transfers | Matured | Eligible | Coverage of matured % | Median change (EUR) | Median growth % |
| --- | --- | --- | --- | --- | --- | --- |
| 6 | 174645 | 166220 | 67813 | 40.80 | 0 | 0.00 |
| 12 | 174645 | 156105 | 63008 | 40.36 | 25000 | 11.11 |
| 24 | 174645 | 139211 | 54182 | 38.92 | 125000 | 40.00 |

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
