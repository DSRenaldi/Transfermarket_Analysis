# Phase 4 Browser Validation

Validated locally against the production React build served by
`src/dashboard_api.py` on 7 October 2026.

## Environment

- Chromium via Playwright CLI.
- Desktop viewport: 1280x720.
- Mobile viewport: 390x844.
- URL: `http://127.0.0.1:8011` (isolated validation port; default remains 8000).

## Checks completed

- All seven navigation destinations open and render their database-backed content.
- Overview displays 2025 market KPIs and human-readable competition labels.
- Competition filter changes the overview to the selected league.
- Value/performance page renders the SVG scatter and ranking table.
- Player journey loads search results, 41 dated valuations for the sampled
  player, season records, and transfer history.
- Team analysis loads 96 observed 2025 club/competition options across the five
  leagues, an appearance-defined roster, role/age composition, and competition
  benchmarks. The sampled roster includes goalkeepers and limited-minute players.
- Team search matches `koln` to `1.FC Köln`, matches all 20 Premier League teams
  by competition name, and exposes a clear disabled-selector empty state when
  no club matches.
- Selecting the Forward position reduced the sampled roster to ten forwards;
  selecting another team refreshed its identity and 27-player roster.
- A roster player drill-through opened the correct Player Journey.
- Transfer analysis renders 12-month fee-state coverage and eligible outcomes.
- Club development renders cohorts above the minimum sample.
- Quality page renders Phase 2/3 audit status, methodology controls, weights,
  source freshness, and 15 competition-season coverage records.
- Mobile navigation retains all seven accessible names and remains fixed within
  the viewport. Wide roster tables scroll locally without user-driven page-level
  horizontal movement.
- Browser console: 0 errors, 0 warnings.
