# Deploying Pilote Budget to Render

This guide makes the app reachable from your phone (even when your PC is off)
using **one Render Docker web service** that serves both the web app and the
API from a single HTTPS origin, plus a **managed Render PostgreSQL** database.

The whole stack is already wired up and verified:

| Thing              | Where it lives / how it works                                                        |
| ------------------ | ------------------------------------------------------------------------------------ |
| Web app + API      | One uvicorn process (`backend/app/main.py`) serves `/api/v1/*` **and** `frontend/dist` (same origin ⇒ automatic HTTPS, no CORS). Enabled by `PILOTE_SERVE_FRONTEND=true`. |
| Database           | Managed Postgres on Render. `DATABASE_URL` is injected automatically and honoured by the app (see `backend/app/config.py`). |
| Schema on Postgres | Built from the SQLAlchemy models at startup (`create_all`) then stamped to Alembic `head`. The SQLite-only migration chain is never replayed on Postgres. |
| Auth               | Optional shared token: set `PILOTE_ACCESS_TOKEN`, and every API route except `/api/v1/health` and `/api/v1/config` refuses requests without `Authorization: Bearer <token>`. The web app shows a sign-in screen when `auth_required` is true. |
| Data import        | Operator-run tool (`app/tools/import_sqlite.py`). **Never automatic.** It copies everything from your SQLite file into Postgres preserving IDs and relationships, then re-arms sequences. |
| PWA                | Minimal installable app (`public/manifest.webmanifest`, `public/sw.js`, icons). Service worker only caches the app shell/assets — never `/api/*` financial data. |

---

## 1. Prerequisites

- A [GitHub](https://github.com) account (free).
- A [Render](https://render.com) account (the Starter/free tiers are enough to try it).
- The `render` URLs you'll need below come from the Render dashboard.

> 📦 TL;DR — everything is ready to deploy. If you want to fully reproduce,
> these were verified: `docker build` passes, the image runs with health checks
> `healthy`, the SPA/API/auth/manifest all answer correctly, and the full test
> suites pass (see §10).

---

## 2. Put the code in a GitHub repo

The project is not yet a git repo. From the project root:

```bash
cd "/home/zowa/Desktop/Pilote Budget"
git init
git add -A
git commit -m "Pilote Budget: ready for cloud deployment"
```

Create an empty **private** repo on GitHub (no README/gitignore, those are
already present), then:

```bash
git remote add origin git@github.com:<you>/pilote-budget.git
git branch -M main
git push -u origin main
```

> Never push `.env`, the SQLite data file, keys or tokens. `.gitignore` and
> `.dockerignore` already exclude **`**/.env*`**, `backend/data`, `node_modules`
> and caches.

---

## 3. Create the database

1. Render dashboard → **New** → **PostgreSQL**.
2. Name: `pilote-budget-db`. Keep the defaults (free/Starter plan is fine to try).
3. Create it and note the **Internal Database URL** (it looks like
   `postgres://user:password@host:5432/pilote_budget` and is only shown once;
   Render also exposes it to services as `DATABASE_URL`).

---

## 4. Create the web service

1. Render dashboard → **New** → **Web Service**.
2. Connect your GitHub repo.
3. Settings:
   - **Environment:** `Docker`
   - **Build & Deploy:** leave "Use Build Context from `./`" (the Dockerfile is at the repo root; it builds the frontend, installs the backend, and runs it).
   - **Branch:** `main`
4. Under **Advanced**:
   - **Port:** `10000`
   - **Health Check Path:** `/api/v1/health`
   - **Instance Type:** Free/web service (or Starter for no spin-down).

### Environment variables

Set these on the web service:

| Variable                          | Value                                                                                          | Required? |
| --------------------------------- | ---------------------------------------------------------------------------------------------- | --------- |
| `DATABASE_URL`                    | Render injects this automatically for the linked DB — leave it set (the app uses it).          | yes       |
| `PILOTE_ENVIRONMENT`              | `production`                                                                                   | yes       |
| `PILOTE_SERVE_FRONTEND`           | `true` (already defaulted in the image, but explicit is clearer)                               | no        |
| `PILOTE_ACCESS_TOKEN`             | a long random string, e.g. `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`     | recommended |
| `PILOTE_AUTO_MIGRATE`             | `true` (default)                                                                               | no        |
| `PILOTE_DEBUG`                    | `false` (default)                                                                              | no        |

> Setting `PILOTE_ACCESS_TOKEN` turns on auth. Without it the app is open to
> anyone who knows the URL — for a personal finance app use a token or protect
> the URL. `PILOTE_CORS_ORIGINS` is **not needed** (everything is same-origin);
> the backend already rejects `"*"` anyway.

5. Deploy, wait for the build (~2–3 min). Verify:

```bash
curl https://<your-service>.onrender.com/api/v1/health
curl https://<your-service>.onrender.com/
curl https://<your-service>.onrender.com/manifest.webmanifest
```

Health returns `{"status":"ok",...}`; `/` returns the app's HTML.

---

## 5. First run on the empty database

- The app creates the Postgres schema from its models and stamps Alembic to
  `head` during startup (`ensure_schema` in `backend/app/db/schema.py`).
- The dashboard is empty until you import your data (next section) or start
  using it fresh.

---

## 6. Move your existing SQLite data into Postgres

This is deliberate and operator-driven: the app **never** imports your SQLite
data on its own.

On your PC (use the local `backend/` checkout), **after** the Postgres DB
exists:

```bash
cd backend
# 1) dry run — checks the target is reachable and empty, changes nothing
uv run python -m app.tools.import_sqlite \
  --sqlite data/pilote_budget.db \
  --target "$DATABASE_URL" --check

# 2) real import (prints a per-table row count, then copies inside one transaction)
uv run python -m app.tools.import_sqlite \
  --sqlite data/pilote_budget.db \
  --target "$DATABASE_URL" --yes
```

Where `$DATABASE_URL` is the **Internal Database URL** from §3. Safety rules:

- It redacts the password from all console output.
- It refuses a non-empty target unless you pass `--force` (you almost never want that).
- It refuses to treat the same database as both source and target.
- It preserves every primary key and foreign key, then re-arms Postgres
  sequences so new records don't collide.

> If the app is already running against this DB, take a backup first (§9), then
> import, then let it restart.

---

## 7. Install on your Android phone (Chrome)

1. Open `https://<your-service>.onrender.com` in Chrome, sign in with your token.
2. Tap the ⋮ menu → **Add to Home screen** (or the “Install app” prompt / banner —
   Chrome shows it because the `manifest.webmanifest` + service worker are served).
3. It’s now an installed app on your home screen (icon: blue wallet).
   - Because the service worker caches the app shell, it opens even offline;
     live data still requires the network.
   - No financial data is stored by the service worker (`/api/*` is never cached).

If Chrome doesn’t propose install, tap Menu → **Install app** manually. iOS
users: use Safari → Share → **Add to Home Screen** (PWA basics apply).

---

## 8. Updating the app

Push to `main`; Render redeploys automatically (manual “Deploy” button also
available). Each deploy:

- rebuilds and re-serves the new frontend,
- idles out database connections safely (`pool_pre_ping` + `pool_recycle`),
- runs the (cheap, idempotent) schema check on startup.

Alembic revisions you add later run on top of the stamped `head`.

---

## 9. Backups & restore (managed Postgres)

**Automatic:** Render’s managed Postgres takes nightly snapshots; enable
**“Automatic Backup”** in its settings.

**On-demand `pg_dump`** (from any machine with `pg_dump`):

```bash
pg_dump "$DATABASE_URL" -Fc -f pilote-$(date +%F).dump
```

**Restore:**
```bash
pg_restore -d "$DATABASE_URL" --clean --if-exists pilote-2026-xx-xx.dump
```

> The on-disk SQLite file is your original source of truth and remains a
> second backup — keep `backend/data/pilote_budget.db` somewhere safe.

---

## 10. Costs & limitations (be honest before clicking)

- **Free tier:** web services idle after ~15 min of inactivity (first load
  after sleeping is slow), and free Postgres databases expire after 30 days.
  The Starter plan removes sleep; paid Postgres keeps data. For a personal app
  this is a coin toss you should decide in the Render dashboard.
- **Single user.** Auth is one shared token; there are no per-user accounts.
  Don’t share the URL+token with strangers.
- **Postgres vs SQLite.** `create_all` builds the schema from the models, so
  the two stores are kept in sync by the codebase itself. The SQLite-only
  Alembic chain is not executed against Postgres (its server defaults are
  SQLite-flavoured).
- **No local Postgres on the dev machine** — the Postgres-specific code paths
  (`ensure_postgres`, sequence re-arming) are verified by tests and in the
  Docker image, not against a live local PG. The importer’s `--check` gives
  you a pre-flight confirmation against the real database.
- **Offline:** quick edits are not queued; the app needs the network for data.

---

## 11. Keeping things safe (checklist)

- [ ] Private GitHub repo; `.gitignore`/`.dockerignore` exclude env + data.
- [ ] `PILOTE_ACCESS_TOKEN` is a fresh, random, long string set only in the Render dashboard.
- [ ] Health check is `/api/v1/health` (it must stay unauthenticated).
- [ ] Backups enabled; keep the SQLite file as a second copy.
- [ ] Confirm the app shows the **“Sign in”** screen with your token, rejects a wrong token, and that `/` loads.

---

## 12. Local development is unchanged

- Frontend dev: `npm run dev` in `frontend/` (Vite on `:5173`, proxies `/api` to `:8000`, `serve_frontend` defaults to **off**).
- Backend dev: `uv run uvicorn app.main:app` in `backend/`.
- To preview the production stack locally (needs a `npm run build` first):

```bash
cd backend
PILOTE_DATABASE_URL=sqlite:////tmp/preview.db \
PILOTE_SERVE_FRONTEND=true \
PILOTE_ACCESS_TOKEN=dev-secret \
uv run uvicorn app.main:app --port 8010
# open http://127.0.0.1:8010
```