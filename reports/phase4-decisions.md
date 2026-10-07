# Phase 4 Decisions

## Platform change

- React is now the confirmed dashboard platform and replaces Power BI.
- Use React 19, TypeScript, and Vite for the browser application.
- Keep PostgreSQL as the analytical source. React never connects to PostgreSQL
  directly; a local read-only Python/psycopg API owns credentials and queries.
- Serve the compiled SPA and API from one loopback service for a simple local
  portfolio workflow.

## Product structure

- Deliver seven analytical pages: market overview, player value/performance,
  player journey, team analysis, transfer analysis, club development, and data
  quality/methodology.
- Use global season, competition, and position filters only where those fields
  operate at a consistent grain.
- Define a team roster from valid player appearances for one club, competition,
  and season. Keep goalkeepers and players below 900 minutes visible while
  exposing score eligibility separately.
- Calculate aligned contributor value from the latest positive valuation on or
  before each player's last appearance for the club. Exclude values older than
  365 days from team aggregates and never describe the result as an official
  published squad valuation.
- Keep transfer horizons and fee states as page-local controls.
- Require at least ten consecutive-season player comparisons before a club
  appears in the development ranking.

## Visual and interaction decisions

- Use a recruitment-room identity with an ink, chalk, cyan, and amber palette.
- Use system-hosted condensed, body, and monospace font roles so the dashboard
  has no external font dependency.
- Use custom SVG charts for the current small chart set and Lucide for interface
  icons. Do not use logos, player photos, or unverified copyrighted assets.
- Repair recognizable double-encoded UTF-8 sequences only in API display text;
  preserve raw/model values and all identifiers unchanged.
- Implement responsive navigation, visible keyboard focus, semantic tables,
  loading/error/empty states, and reduced-motion support.
- Filter the Team Analysis selector locally by club or competition name with
  case/diacritic-tolerant matching; do not issue a new database query per
  keystroke.

## Analytical guardrails

- Every efficiency row exposes minutes, peer size, season, competition,
  valuation date, and valuation lag.
- Use the term `high relative efficiency`, never an objective `undervalued`
  recommendation.
- Keep transfer fee statuses separate and show coverage before outcome tables.
- Label club development as an association with the season-end club, not causal
  value creation.
- Surface audit counts, source snapshot dates, coverage, methodology parameters,
  position weights, and limitations inside the dashboard.

## Security and deployment

- API queries are GET-only, use validated filters and parameterized values, run
  in read-only transactions, and cap result sizes.
- PostgreSQL credentials remain in ignored `.env`/environment variables and are
  absent from the React bundle.
- The local server binds to `127.0.0.1`. Authentication, HTTPS, throttling, and a
  production reverse proxy are required before any public deployment.

## Confirmed verification

- The production build completes with one approximately 267 KB JavaScript
  bundle before gzip and no dependency vulnerabilities reported by npm.
- All 32 Phase 4 validation checks pass.
- All 22 repository unit/integration tests pass.
- Playwright verified all seven pages at desktop and mobile viewport sizes with
  zero browser console errors or warnings.
