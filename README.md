# Pilote Budget

Pilote Budget is a local-first personal finance application. The browser talks to a FastAPI server on the same desktop, and the server stores the ledger in a local SQLite file. It runs without internet access, cloud services, or sign-in once the dependencies are available locally.

## Features

- Manage transactions, accounts, transfers, and income and expense categories. Import and preview CSV files, filter the ledger, and export transactions as CSV.
- Plan category budgets, track savings goals and debts, and record or skip scheduled transactions.
- Review cash flow, spending trends, forecasts, and Safe-to-Spend calculations.
- Ask the financial assistant supported questions. It uses deterministic rules and calculations over the local ledger.
- Export, validate, and restore a full JSON backup from Settings. Restoring replaces the existing data.

## Setup

Use Python 3.11 or newer, `uv`, and Node.js 24 LTS with npm. The commands below use locally cached packages. On an offline desktop, the locked packages and build tools must be preinstalled or supplied in local `uv` and npm caches. A dependency cache is unnecessary if `backend/.venv` and `frontend/node_modules` are already prepared for that desktop.

From the project root:

```bash
(cd backend && uv sync --offline --locked)
(cd frontend && npm ci --offline --no-audit --no-fund)
```

To use caches supplied in a different location, set `UV_CACHE_DIR` and `npm_config_cache` to their respective cache paths before running the commands. The caches must contain the locked packages and any native wheels or binaries for the desktop's operating system, CPU architecture, and runtime versions. A cache miss stops the offline installation. Installations from local caches were verified on Linux x86-64 with Python 3.14.6, `uv` 0.11.29, Node.js 24.22.0, and npm 11.19.1.

If the sandbox reports `EPERM` when esbuild checks its binary version, rerun the npm command with `--ignore-scripts`. The locked platform-specific esbuild package must be available in the npm cache for this to work.

## Run locally

Start the API in one terminal:

```bash
cd backend
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Start Vite in another terminal:

```bash
cd frontend
npm run dev
```

Open [Pilote Budget](http://127.0.0.1:5173). Vite proxies `/api` to the loopback backend. The [health endpoint](http://127.0.0.1:8000/api/v1/health) reports API and SQLite status. Keep both servers bound to loopback.

The API creates `backend/data/pilote_budget.db` and applies Alembic migrations on startup. For an isolated demo database, set `PILOTE_DATABASE_URL` to `sqlite:///./data/demo.db` when starting the API. Use the onboarding flow to create synthetic accounts and categories, then add sample transactions. In this project workspace, use synthetic entries, imports, and backups only.

To apply and inspect migrations without starting the API, run these commands from `backend/` with the same `PILOTE_DATABASE_URL` setting:

```bash
.venv/bin/alembic upgrade head
.venv/bin/alembic current
```

`PILOTE_DEBUG=true` exposes the OpenAPI JSON at `/openapi.json` on the API server.

To preview the production build locally, with the API still running, run `npm run build` and `npm run preview` from `frontend/` and open [the production preview](http://127.0.0.1:4173).

## Tests

Run these commands from the project root after setup:

```bash
(cd backend && .venv/bin/python -m pytest)
(cd frontend && npm test)
(cd frontend && npm run typecheck)
(cd frontend && npm run build)
```

Backend tests cover migrations, API workflows, and financial calculations using synthetic records in temporary SQLite databases. Frontend tests cover the API client, formatting, chart rendering, quick entry, and dashboard and assistant helpers.

## Architecture

| Location | Responsibility |
| --- | --- |
| `frontend/src/` | React and TypeScript pages, reusable components, data hooks, and the local API client |
| `backend/app/api/v1/` | FastAPI routes and request handling |
| `backend/app/services/` | Application workflows and SQLAlchemy queries |
| `backend/app/domain/` | Ledger calculations, budget periods, schedules, Safe-to-Spend, and assistant rules |
| `backend/app/models/`, `backend/app/schemas/` | Database models and API contracts |
| `backend/alembic/` | Versioned SQLite migrations |

## License

Pilote Budget and its original SVG icons are available under the MIT license. Third-party dependencies retain their own licenses. See [LICENSE](LICENSE).
