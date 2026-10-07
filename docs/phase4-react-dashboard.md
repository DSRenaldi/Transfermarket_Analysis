# Phase 4: React analytics dashboard

The project dashboard is implemented as a React and TypeScript single-page
application. React replaces the previously planned Power BI delivery. A small
read-only Python API queries PostgreSQL; database credentials never enter the
browser bundle.

## Architecture

```text
React + TypeScript (browser)
          |
          | JSON over local HTTP
          v
Python read-only dashboard API
          |
          | parameterized psycopg queries
          v
PostgreSQL: tm_analytics + tm_analysis + tm_audit
```

The API also serves the production React build, so one local process is enough
after compilation. It binds to `127.0.0.1` by default and implements GET-only
dashboard routes.

## Install and run

The existing `.env` continues to provide PostgreSQL credentials.

```powershell
cd frontend
npm install
npm run build
cd ..
.\.venv\Scripts\python src\dashboard_api.py
```

Open `http://127.0.0.1:8000`.

For frontend development, run the API on port 8000 and Vite in a second shell:

```powershell
cd frontend
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` to the Python service.

## Dashboard pages

1. **Market overview** — aligned total and median market value, competition
   allocation, position benchmark, and age curve.
2. **Value & performance** — interactive performance/value scatter and the
   contextual Value Efficiency ranking.
3. **Player journey** — player search, full dated valuation history, selected
   season records, and recorded transfers.
4. **Team analysis** — appearance-defined historical rosters, aligned squad
   value, role/age composition, competition benchmarks, searchable team
   selection, and player drill-through. Search matches club or competition
   names without case/diacritic sensitivity. Goalkeepers and limited-minute
   contributors remain visible; score eligibility is disclosed separately.
5. **Transfer analysis** — 6/12/24-month outcomes, fee-state separation,
   coverage, and post-valuation club status.
6. **Club development** — consecutive-season value cohorts with at least ten
   comparable players per club.
7. **Quality & method** — validation status, source freshness, coverage,
   methodology parameters, score weights, and limitations.

Global season, competition, and position filters apply to overview, efficiency,
team, and club pages. Team analysis requires one season and uses a page-local
team selector. The remaining pages provide controls specific to their grain.

## API routes

| Route | Purpose |
| --- | --- |
| `/api/health` | Database connectivity without credentials |
| `/api/meta` | Filter values and methodology version |
| `/api/overview` | Market KPIs and aggregates |
| `/api/efficiency` | Context-rich score rows and scatter data |
| `/api/players` | Player search |
| `/api/player` | Dated player journey |
| `/api/transfers` | Horizon and fee-state outcomes |
| `/api/clubs` | Club development cohorts |
| `/api/team-options` | Teams observed in the selected season/competition |
| `/api/team` | Historical roster, composition, benchmark, and aligned values |
| `/api/quality` | Audit, freshness, coverage, parameters, and weights |

All filters are validated against allowlists, row limits are capped, SQL values
are parameterized, and the transaction is marked read-only. Internal exceptions
are logged locally but SQL and credential details are not returned to clients.
The API also applies a conservative display-only repair for common UTF-8 text
that was double-encoded upstream. Raw values and stable identifiers remain
unchanged.

## Visual system

The dashboard uses a recruitment-room visual language rather than a generic
admin template: ink-blue surfaces, chalk-white typography, field cyan for
analytical signal, and amber for caveats. A pitch-derived navigation mark is the
single decorative signature. Charts use lightweight accessible SVG rather than
an additional charting runtime.

The interface includes keyboard focus states, semantic navigation and tables,
responsive layouts down to 390 px, explicit loading/error/empty states, and a
`prefers-reduced-motion` fallback. No club logo, player photo, remote font, or
unverified visual asset is used.

Team rosters are derived from valid match appearances at the
`player x club x competition x season` grain. Team value uses each player's
latest positive valuation on or before their last appearance for that club and
excludes valuations older than 365 days from aggregates. It is therefore a
reproducible aligned contributor-value measure, not an official published squad
valuation.

## Verification

```powershell
cd frontend
npm run build
cd ..
.\.venv\Scripts\python src\validate_phase4.py
.\.venv\Scripts\python -m unittest discover -s tests -v
```

Phase 4 has 32 automated dashboard/API checks and seven API integration tests.
The full repository suite contains 22 tests. Browser checks cover every page,
team/position filter interaction, player drill-through,
desktop 1280x720, mobile 390x844, and console errors/warnings.

## Deployment boundary

This implementation is a local portfolio dashboard. Before exposing it to an
untrusted network, add authentication, a production reverse proxy, HTTPS,
request throttling, structured logs, and a least-privilege PostgreSQL account.
The current local server deliberately binds to loopback only.
