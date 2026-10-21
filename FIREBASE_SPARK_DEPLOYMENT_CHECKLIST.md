# Pilote Budget — Spark-only deployment checklist & Phase 1 gap report

Status: **Foundation + Phase 1 (read-only Firebase preview).** Nothing has been
deployed, pushed, migrated, or billed. The legacy FastAPI/SQLite app is
unchanged and remains the working fallback.

Companion docs: `FIREBASE_MIGRATION_PLAN.md` (design + capability matrix + STOP
list), `FIREBASE_DEPLOYMENT.md` (long-form guide),
`FIREBASE_SMOKE_TEST.md` (safe synthetic-data E2E smoke test).

---

## 1. Verification results (latest runs)

| Check | Result |
|---|---|
| Backend pytest | **289 passed**, 1 warning |
| Frontend vitest | **146 passed / 12 files** (legacy + Firebase model/mappers + balance derivation + read-only guard + config gate + emulator gate + routing gate) |
| Frontend typecheck (`tsc -b`) | **clean** |
| Frontend production build | **clean**; Firebase SDK splits into its own lazy chunk (`FirebaseApp-*.js`) |
| Firebase tests (emulator) | **37 passed / 37** (23 rules + 5 import + 9 smoke E2E) |
| Browser verification (local emulator, real Chrome) | **39/39 checks** — login/logout, dashboard, deep links + hard refresh on every `/firebase/*` subroute, signed-out redirects, owner reads, derived vs imported balances, loading + offline states (see `FIREBASE_SMOKE_TEST.md` §8–§9) |
| Synthetic-data smoke E2E (emulator) | fixture DRY-RUN/COMMIT, derived-balance check, owner-read + anon/cross-user denial, real DB hash unchanged |
| Read-path scoping (emulator) | owner list/get OK; anonymous + cross-user denied for accounts/categories/transactions |
| Secrets / credentials / DBs staged or tracked | **none found** (see §2) |
| Local API URL hard-coded in production bundle | **none** (see §3) |
| Deploy / push / billing change | **not performed** |

## 2. File & secret audit (point 1)

`git status`: only `.gitignore` modified (unstaged) + untracked the three MD
docs, `firebase/`, and the new frontend Firebase sources.

New Phase 1 files (all untracked, all scanned clean by pattern grep):

- `frontend/src/firebase/{config,runtime,auth,repo.model,LoginPage,FirebaseApp,...}.ts(x)`
- `frontend/src/firebase/model.test.ts`, `frontend/.env.example`
- edited: `frontend/src/App.tsx`, `frontend/src/components/auth/SignInOverlay.tsx`,
  `frontend/package.json` (`firebase@^11.10.0`), `firebase/firebase.json` (SPA rewrites)

Phase 2.2 files (emulator-gated browser verification; all untracked/edited, no secrets):

- new: `firebase/tools/make-fixture-user.mjs` (local Auth-emulator fixture user;
  refuses unless `FIREBASE_AUTH_EMULATOR_HOST` is set)
- edited: `firebase/firebase.json` (Auth emulator port 9099),
  `firebase/package.json` (`emulators:start`/`exec` now `--only firestore,auth`
  `--project demo-pilote-budget`, new `make-user`),
  `frontend/src/firebase/config.ts` (emulator gate + endpoints),
  `frontend/src/firebase/runtime.ts` (guarded emulator connect),
  `frontend/.env.example`, `frontend/src/firebase/config.test.ts` (+5 tests)

Phase 2.3 files (deep-link / hard-refresh routing fix; read-only, no data changes):

- new: `frontend/src/firebase/gate.ts` (pure gate + redirect decision),
  `frontend/src/firebase/gate.test.ts` (51 regression tests)
- edited: `frontend/src/firebase/auth.tsx` (`authResolved` + derived `gate`),
  `frontend/src/firebase/FirebaseApp.tsx` (gate-driven routing +
  `resolveFirebaseRedirect`)

Ignored/not staged (verified): `firebase/node_modules`, `frontend/node_modules`,
`frontend/.env*` (real values), emulator logs, `frontend/dist/`,
`backend/data/pilote_budget.db*`, `__pycache__`, `.venv*`. Secret-pattern scan
across every file git would add: **no matches** (no `AIza...` keys, no private
keys, no service-account content). `.gitignore` also matches Firebase-generated
admin JSON paths so the operator credential can never be committed.

## 3. Hosting build / output / rewrites (point 4)

- Vite `outDir = dist` ↔ `firebase.json → hosting.public: ../frontend/dist` ✓
- **SPA rewrites are now present**: `"rewrites": [{ "source": "**",
  "destination": "/index.html" }]` — deep links to `/transactions`,
  `/firebase/*`, etc. serve the shell on Firebase Hosting ✓
- ⚠️ **The catch-all rewrite also catches `/api/**`.** Because Firebase only
  rewrites when no static file matches, `/api/v1/*` on Hosting returns
  `index.html` (200) — not a JSON error — so **the legacy FastAPI-facing routes
  cannot run against Firebase Hosting without a real backend** (also a Phase 2
  trust-model blocker). Phase 1 is unaffected: `/firebase/*` needs the rewrite
  and never calls `/api`. Before any full-app Hosting release this must be
  resolved (owner choice: own domain + FastAPI host, or Blaze + Cloud Functions
  proxy — never a static proxy around the DB).
- No API proxy configured on Hosting (none can exist on Spark without a backend)
- Production bundle contains **no** `127.0.0.1` / `:8000` / absolute API URL;
  the `/api/v1` base is relative and belongs to the legacy path. `localhost`
  strings in the bundle are dependency-internal URL-parser placeholders only
- SSL: Firebase Hosting provisions a managed certificate automatically

## 4. Auth + Firestore client (points 2, 3, 5)

- Firebase client SDK added **only** to the separate `/firebase/*` path,
  lazy-loaded so the legacy bundle never includes it.
- Auth: `firebase/auth` email/password with `onAuthStateChanged` + session
  persistence (`browserLocalPersistence`). The legacy bearer-token flow
  (`src/lib/auth.ts`) is untouched and still guards every `/api/*` call.
- Data: typed read-only hooks under `users/{uid}/...` for accounts, categories,
  transactions and the profile doc; offline persistence enabled via
  `persistentLocalCache()`; UI states are explicit — loading, empty,
  permission-denied, and offline (navigator events + `metadata.fromCache`).
- Rules deploy wiring unchanged and intact (`firestore.rules` +
  `firestore.indexes.json`). No service-account content is reachable from the
  browser (all admin access stays in the operator CLI with env credentials).
- 23 emulator rule tests now cover list+get scoping, imported-row immutability
  and denial for the Phase 1/2.1 read paths.
- **Phase 1 audit hardening (this review):**
  - Runtime init now steps down from `persistentLocalCache()` to an in-memory
    Firestore if the browser blocks IndexedDB, instead of failing to load.
  - A genuine runtime init failure renders a discrete error screen; previously
    it left an indefinite "Starting Firebase…" spinner.
  - The offline banner now subscribes to `online`/`offline` events (previously
    it read `navigator.onLine` once and could go stale).
  - Dashboard metric cards show `…` while loading (no misleading zeros), and the
    account total is labelled **"Imported balance"** because it is the imported
    cached projection, not a live re-derivation.
  - `signOut()` rejections are caught (no unhandled promise rejections).
  - Config-gate unit tests lock in: the path enables only with the three
    identity keys, ignores whitespace, and requires no optional keys.

## 5. What is REALLY wired to Firebase vs still FastAPI/SQLite

| Part of the product | Today |
|---|---|
| Firestore Security Rules + indexes + emulator tests | **Yes** (37 tests green) |
| SQLite→Firestore operator importer + E2E | **Yes** (5 import + 9 smoke E2E green) |
| `/firebase/*` read-only preview: login, dashboard, accounts, categories, transactions | **Yes (Phase 1, read-only)** — 11 unit tests + emulator scoping |
| All legacy screens + sign-in + data | **No — 100% on FastAPI/SQLite** (`/api/v1`) |
| Transaction writes, transfers, recurring materialisation, balance mutation, CSV commit, backup restore, assistant | **No — disabled & labelled unavailable in Phase 1** (class C — plan §4) |

The product is **not** migrated. It is a FastAPI app plus a separate read-only
Firebase preview; every guarantee-affecting operation is intentionally absent
there.

## 6. Decision & minimum safe remaining work (point 7)

STOP maintained: a full Firebase publish still requires the owner decision on
the trust model (accept single-device B-mode **or** Blaze+Cloud Functions),
then the auth/data rewiring of the full app (plan §4 C-1..C-6). Phase 1 does
not claim to replace any of that. Before a real Hosting release of the whole
app, item 1..4 of the previous report still apply (owner decision, full-auth
port, data-layer rewiring of every screen, revisit business guarantees).

## 7. Spark-only deployment checklist (exact commands + Console)

Prereqs: Node 22+, a JDK 17 for the emulator (rootless `/tmp/jre` works).

```bash
# A. Local parity gate (repeat on every change)
cd firebase
export JAVA_HOME=/path/to/jre          # existing: /tmp/jre
export PATH="$JAVA_HOME/bin:$PATH"
npm run emulators:start &              # Firestore 127.0.0.1:8080 + Auth 127.0.0.1:9099
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 npm test     # expect 37/37 green

# B. Frontend + legacy gate
cd ../frontend
npm test                               # 146/146
npm run typecheck && npm run build     # produces firebase/../frontend/dist

# C. Rules + indexes (safe, no app release)
cd ../firebase
firebase use <REAL_PROJECT_ID>         # replaces placeholder pilote-budget
firebase deploy --only firestore:rules
firebase deploy --only firestore:indexes
```

Console actions (Spark only; never attach a card):
1. console.firebase.google.com → Add project (id = `<REAL_PROJECT_ID>`), skip
   Analytics, stay free Spark.
2. Authentication → Sign-in method → Email/Password → **Enable**.
3. Firestore → Create database (Production mode), pick region.
4. Project settings → Your apps → Add web app → copy the **public** config
   (`apiKey`, `authDomain`, `projectId`, `storageBucket`,
   `messagingSenderId`, `appId`).
5. Create a test user manually (Authentication → Users → Add user) with a
   **fixture email** — never use real credentials.
6. To run the operator import against production (only with a fixture DB for
   tests): Project settings → Service accounts → generate a private key, store
   OUTSIDE the repo (e.g. `~/.secure/pilote-budget-sa.json`), import via
   `GOOGLE_APPLICATION_CREDENTIALS=...` env only.

Public web config → frontend (these are browser-safe):
```bash
cd frontend
cp .env.example .env
# fill in the six VITE_FIREBASE_* values, then rebuild
npm run build
```
The Firebase preview only activates when the three identity-critical values
(`VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`,
`VITE_FIREBASE_PROJECT_ID`) are present. Real `.env` is git-ignored;
`.env.example` is committed (no secrets).

### No-real-data test plan (operators)
1. `cd firebase && export JAVA_HOME=/tmp/jre; PATH=$JAVA_HOME/bin:$PATH &&
   npm test` → green (37/37). See `FIREBASE_SMOKE_TEST.md` for the fixture-based
   E2E (generator, import, derived-balance verification, denial checks).
2. Importer against a **schema-only fixture** (never the real DB):
   `node tools/import-sqlite-to-firestore.mjs --db /tmp/fixture.db --uid test-uid`
   → verify DRY-RUN prints counts and writes nothing.
3. Re-run `--yes` → verify cents totals, FK warnings, id mappings, and the
   `users/test-uid/imports/{runId}` fingerprint doc.
4. Browser walk-through against the **local emulators** (no real project): set
   `VITE_FIREBASE_USE_EMULATORS=true` in `frontend/.env.local`, `npm run dev`,
   open `/firebase/login`, sign in as the fixture user, confirm
   accounts/categories/transactions render read-only and the "unavailable
   operations" list is visible; confirm the legacy routes still work against the
   running FastAPI backend. Also deep-link / hard-refresh each `/firebase/*`
   sub-route (it must stay on that route) and confirm signed-out deep links land
   on `/firebase/login`. Full commands + expected values: `FIREBASE_SMOKE_TEST.md`
   §8–§9.
5. Emulator rules playground as anonymous → all reads denied; as the fixture
   user → only `users/test-uid/...`.

### Rollback
- Rules: Console → Firestore → Rules → Revert, or
  `git checkout <old> -- firebase/firestore.rules && firebase deploy --only firestore:rules`.
- Indexes: Console → Firestore → Indexes.
- Hosting (future): Console → Hosting → Release history.
- Phase 1 frontend: remove the `/firebase/*` route/lazy import and rebuild, or
  simply unset the `VITE_FIREBASE_*` variables — the legacy app is untouched.
- Imported data: additive under `users/{uid}`; remove with a one-off admin
  script, never via the app.

### Unsupported features users must NOT rely on (Phase 1 explicitly labels these)
- Two-row transfer atomicity; balance single-source-of-truth; server-scheduled
  recurring materialisation; transactional/duplicate-proof CSV import; validated
  backup/restore; financial assistant; any money **writes** in the Firebase path;
  cross-device consistency guarantees on money math.