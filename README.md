# Pilote Budget

Local-first personal finance manager.

- **Backend:** FastAPI + SQLAlchemy + SQLite (Alembic migrations), `backend/`
- **Frontend:** React + TypeScript + Vite, `frontend/`

No cloud services, no authentication, no external integrations.

## Run

### Backend

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

On startup the SQLite database is created and migrated automatically
(`backend/data/pilote_budget.db`). Health check: <http://127.0.0.1:8000/api/v1/health>,
OpenAPI docs: <http://127.0.0.1:8000/docs>.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The dev server proxies `/api` to the backend on
port 8000.

## Tests

```bash
cd backend && uv run pytest      # db initialization, API health, domain logic
cd frontend && npm run build     # typecheck (tsc -b) + production build
```

## Architecture

```
backend/app/
  api/v1/       HTTP layer (thin routes, response models)
  services/     application/workflow layer (takes a Session)
  domain/       pure logic: enums, period math, calculations
  models/       SQLAlchemy models (full schema, see below)
  schemas/      Pydantic request/response contracts
  db/           engine, session, base/mixins, migration helpers
  config.py     pydantic-settings (PILOTE_ env prefix, .env support)
backend/alembic/  migrations (source of truth for the schema)
```

Database schema (foundation for later phases): `profiles`, `accounts`,
`categories`, `transactions`, `transfers`, `budgets`, `goals`,
`recurring_transactions`, `debts`.

Frontend keeps business logic out of components: `lib/` (API client, nav
config, formatting, dashboard view model), `hooks/` (data fetching states),
`components/` (reusable shell/cards/charts/states), `pages/`.
