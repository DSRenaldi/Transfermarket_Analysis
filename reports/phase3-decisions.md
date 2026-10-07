# Phase 3 Decisions

## Eligibility and freshness

- Keep the existing 900-minute, outfield, positive-value requirements.
- Add a maximum 365-day season-end valuation lag. This excludes 20 of the 4,412
  Phase 2 value-eligible rows and leaves 4,392 scored player-seasons.
- Require at least 30 eligible players per peer group. The current 45 peer
  groups all pass, with observed sizes from 65 to 136.
- Keep the minimum peer group at `season x competition x position_group`.
  Subposition-plus-age groups are retained as a future sensitivity analysis
  because they can fragment samples and require more role-specific metrics.

## Value Efficiency Score

- Winsorize each metric and log market value at the peer-group 5th and 95th
  percentiles before z-standardization.
- Use versioned position weights stored in PostgreSQL, not hidden dashboard
  calculations.
- Standardize the weighted performance composite a second time so both terms
  in `Performance Z-Score - Market Value Z-Score` are on comparable scales.
- Reverse cards per 90 so fewer cards score higher.
- Use only the label `high_relative_efficiency` for the top cumulative 10%; do
  not store an objective `undervalued` flag.
- Exclude goalkeepers because saves, goals prevented, and reliable clean-sheet
  context are unavailable.

## Position limitations

- Defender weights emphasize minutes and start rate rather than goals, but
  these remain selection/availability proxies, not defensive-action quality.
- Forward and midfielder scores use the limited observed goal, assist,
  selection, and discipline metrics. Expected goals, progression, pressing,
  tactical role, salary, injury, and contract context are absent.
- Age is not included in performance score. It is analyzed separately so the
  score does not silently favor a recruitment strategy.

## Age analysis

- Use the documented six numeric age bands plus Unknown.
- Correct the Phase 2 birth-date parser to accept the source timestamp format
  and rebuild both phases. One score-eligible row still lacks a usable birth
  date and remains Unknown without imputation.
- Resolve multiple competitions in the same player-season by selecting the row
  with the most minutes only for the longitudinal development fact.
- Calculate value growth only for consecutive seasons where both aligned values
  are positive and no more than 365 days old.

## Transfer outcomes

- Use 6-, 12-, and 24-month target dates.
- Require the post valuation to occur after the transfer, on or before the
  target, and within 90 days of the target.
- Retain all historical transfers and expose eligibility flags; do not silently
  drop incomplete outcomes.
- Keep fee status separate and preserve post-valuation destination-club match
  status.
- Call the result market-value change, never ROI or causal transfer impact.

## Confirmed results

- PostgreSQL schema `tm_analysis` contains 10 tables and 3 views.
- The scoring population has 4,392 player-seasons across 45 peer groups; 463
  rows fall in the exploratory high-relative-efficiency band.
- The longitudinal table contains 8,103 player-seasons and 1,886 valid
  consecutive-season comparisons.
- Transfer outcome facts contain 523,935 transfer-horizon rows, of which 185,003
  satisfy the complete value-change rules across all three horizons.
- Median peer-group Spearman association between performance and market value is
  0.4156, ranging from 0.0670 to 0.7218. This is association, not causation.
- Median top-ten value concentration is 37.55%, with a peer-group range of
  19.93%-58.10%.
- All 51 Phase 3 validation checks and all repository unit tests pass.
