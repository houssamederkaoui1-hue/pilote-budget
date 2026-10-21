# Pilote Budget — Firebase synthetic-data smoke test

A repeatable, **safe**, end-to-end check of the read-only Firebase path that
uses **only fabricated data**. It never touches the real ledger, adds no write
APIs, and requires no deployment, push, billing change or Firebase Console
access.

Companion docs: `FIREBASE_MIGRATION_PLAN.md`, `FIREBASE_DEPLOYMENT.md`,
`FIREBASE_SPARK_DEPLOYMENT_CHECKLIST.md`.

---

## 1. What it does

1. **Generates a disposable fixture DB** — `firebase/tools/make-fixture-db.mjs`
   builds a throwaway SQLite file (default: `os.tmpdir()`) containing fake
   accounts, categories, transactions and transfers, and prints the expected
   balances computed independently from the seed rows.
2. **Imports it with the real operator tool** — first a DRY-RUN (must write
   nothing), then a COMMIT against the **Firestore emulator** under a fresh
   test UID.
3. **Reads the data back as the owner through the real Security Rules** and
   re-derives every account balance from the imported documents.
4. **Verifies** the derived balances against both the fixture's expected values
   and hard-coded constants, then asserts owner-read, anonymous-denial and
   cross-user-denial.

The automated version is `firebase/tests/smoke.e2e.test.js` (part of `npm test`).

## 2. Safety guarantees (no real data)

- The fixture generator **refuses** to write to
  `backend/data/pilote_budget.db` or anywhere under `backend/data/`
  (`assertSafeDbPath`), and its default output lives in the OS temp directory.
- The operator importer opens the source DB **read-only**
  (`new Database(path, { readonly: true })` + `PRAGMA query_only = true`); the
  smoke test asserts the fixture file hash is unchanged after import.
- The smoke test hashes the real DB before and after the run and asserts it is
  unchanged (and that its existence is unchanged).
- No test reads real credentials; the emulator target needs none.

## 3. Prerequisites (all local)

- Node 22+.
- A JDK 17 for the emulator. Rootless Temurin works:
  `/tmp/jre` (see checklist §7).
- `firebase/node_modules` installed (`cd firebase && npm install` if missing).

## 4. Run it (local only)

```bash
cd firebase

# Terminal A — start the emulators (leave running)
export JAVA_HOME=/tmp/jre
export PATH="$JAVA_HOME/bin:$PATH"
npm run emulators:start          # Firestore 127.0.0.1:8080 + Auth 127.0.0.1:9099

# Terminal B — generate a fixture and inspect the expected balances
npm run make-fixture             # prints JSON: dbPath / counts / expectedBalances
# or with an explicit disposable path:
node tools/make-fixture-db.mjs --out /tmp/pilote-budget-smoke/fixture.sqlite

# Run just the smoke test (emulator must be up)
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 npm run test:smoke

# Or the full Firebase suite (rules + import + smoke)
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 npm test
```

If the emulator is not running, the smoke test **skips cleanly** (it does not
fail). Everything above is local; no Console step is required.

### Manual import/verify (what the automated test does)

```bash
cd firebase
UID="smoke-$(date +%s)"
FIX=/tmp/pilote-budget-smoke/fixture.sqlite
node tools/make-fixture-db.mjs --out "$FIX"

# 1) DRY-RUN — review the plan; nothing is written
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 GOOGLE_CLOUD_PROJECT=demo-pilote-budget \
  node tools/import-sqlite-to-firestore.mjs --db "$FIX" --uid "$UID"

# 2) COMMIT to the emulator
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 GOOGLE_CLOUD_PROJECT=demo-pilote-budget \
  node tools/import-sqlite-to-firestore.mjs --db "$FIX" --uid "$UID" --yes

# 3) Inspect in the emulator UI (optional)
firebase emulators:start --only firestore   # then browse users/$UID/...
```

## 5. Fixture contents and expected balances

Three fake accounts, three categories, seven transactions (two `void`) and four
transfers (two `cancelled`). Account `current_balance` values are deliberately
wrong so the test proves the imported snapshot is stale and derivation is
authoritative.

| Account | opening | posted effects | expected (cents) | expected |
|---|---:|---|---:|---:|
| 1 Smoke Checking | 100.00 | +1000.00 income, −42.50 expense, −10.00 expense (pending), −200.00, −50.00 transfers out | `79750` | 797.50 |
| 2 Smoke Savings | 500.00 | +25.00 income (reconciled), +200.00, +50.00 transfers in | `77500` | 775.00 |
| 3 Smoke Cash | 0.00 | −30.00 expense | `-3000` | −30.00 |

Excluded on purpose: transaction `void` rows and `cancelled` transfers.

## 6. Checks performed

| Check | Where |
|---|---|
| Fixture generator refuses the real DB path | `assertSafeDbPath` unit test |
| Fixture expectation == hard-coded values | `expectedBalances()` test |
| DRY-RUN writes nothing | smoke test |
| Importer opens the fixture read-only (hash unchanged) | smoke test |
| COMMIT writes 3 accounts / 3 categories / 7 transactions / 4 transfers / profile | smoke test |
| Derived Firestore balances == fixture expectation == hard-coded | smoke test |
| Owner can list accounts / transactions / transfers | smoke test |
| Anonymous reads denied | smoke test |
| Cross-user reads denied | smoke test |
| Real DB unchanged (hash + existence) | smoke test `before`/`after` |

## 7. Steps that require Firebase Console vs local

**Local only (everything in this document):**

- Starting the emulator, generating fixtures, importing, reading back, running
  rules/import/smoke tests, TypeScript checks and builds, and the browser
  verification in §8.

**Firebase Console (manual, only for a REAL deployment — not part of this
smoke test):**

- Create the Firebase project (Spark), enable Email/Password auth, create the
  Firestore database, register the web app and copy the public config, create a
  **fixture** test user, and (only if testing production) generate a
  service-account key stored outside the repo.

---

## 8. Browser verification (Phase 2.2) — PASSED, fully local

The Firebase preview can now be exercised end-to-end **in a real browser with no
Firebase project and no deploy**, using the local Auth + Firestore emulators.
This required a small, env-gated code change (previously it was impossible):

- `frontend/src/firebase/config.ts` — new `firebaseEmulatorsEnabled` gate
  (`VITE_FIREBASE_USE_EMULATORS`, accepts `1/true/yes`, **default OFF**) plus
  `FIREBASE_AUTH_EMULATOR_URL` (`http://<host>:9099`) and
  `FIREBASE_FIRESTORE_EMULATOR` (`{ host, port: 8080 }`, host override
  `VITE_FIREBASE_EMULATOR_HOST`, default `127.0.0.1`).
- `frontend/src/firebase/runtime.ts` — when the gate is on, calls
  `connectAuthEmulator(auth, …, { disableWarnings: true })` (before
  `setPersistence`) and `connectFirestoreEmulator(db, host, 8080)` (after
  `initializeFirestore`). With the gate off, behaviour is byte-for-byte the
  previous production path.
- `firebase/firebase.json` — Auth emulator port `9099` added.
- `firebase/package.json` — `emulators:start`/`emulators:exec` now
  `--only firestore,auth --project demo-pilote-budget`; new `make-user` script.
- `firebase/tools/make-fixture-user.mjs` — creates a fixture user in the
  **local Auth emulator only**; **refuses** unless `FIREBASE_AUTH_EMULATOR_HOST`
  is set (verified: exits non-zero without it).
- `frontend/.env.example` — documents both the emulator flag and the host
  override.

### Exact commands used

```bash
# Terminal A — emulator (Firestore 8080 + Auth 9099, project demo-pilote-budget)
cd firebase
export JAVA_HOME=/tmp/jre
export PATH="$JAVA_HOME/bin:$PATH"
npm run emulators:start

# Terminal B — fixture Auth user (local emulator only)
cd firebase
FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099 npm run make-user
#   defaults: project demo-pilote-budget, smoke@example.invalid / smokepass123
#   printed UID: 1QaRVG1nNRw58bQKychonGrvW7Ff

# Terminal B — generate + import the synthetic fixture under that UID
FIX=/tmp/pilote-2.2/fixture.sqlite
node tools/make-fixture-db.mjs --out "$FIX"
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 GOOGLE_CLOUD_PROJECT=demo-pilote-budget \
  node tools/import-sqlite-to-firestore.mjs --db "$FIX" --uid 1QaRVG1nNRw58bQKychonGrvW7Ff            # DRY-RUN
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 GOOGLE_CLOUD_PROJECT=demo-pilote-budget \
  node tools/import-sqlite-to-firestore.mjs --db "$FIX" --uid 1QaRVG1nNRw58bQKychonGrvW7Ff --yes      # COMMIT

# frontend/.env.local (git-ignored; demo values only — never a real key)
#   VITE_FIREBASE_API_KEY=demo-api-key
#   VITE_FIREBASE_AUTH_DOMAIN=demo-pilote-budget.firebaseapp.com
#   VITE_FIREBASE_PROJECT_ID=demo-pilote-budget
#   VITE_FIREBASE_USE_EMULATORS=true

cd frontend && npm run dev        # http://127.0.0.1:5173
# then drive a real headless Chrome via CDP (no project, no deploy)
```

The browser was driven with a CDP script (Node 22 global `WebSocket` + real
`google-chrome --headless=new --remote-debugging-port=9223`), which performed
real login, navigation, refresh and Offline-mode toggling. **Result: 18/18
checks passed.**

### Checks performed and observed (18/18)

| # | Check | Observed |
|---|---|---|
| 1 | `/firebase/login` renders the sign-in form | pass |
| 2 | Transient loading state observed during init | `["Loading Firebase…","Starting Firebase…"]` |
| 3 | Login lands on `/firebase/dashboard` | pass |
| 4 | Derived balance rendered | `MAD 1,542.50` (= 79750+77500−3000 cents) |
| 5 | Imported snapshot rendered | `MAD 2,232.56` (= 99900−100+123456 cents) |
| 6 | Currency title / formatting | `MAD` |
| 7 | Signed-in user email shown | `smoke@example.invalid` |
| 8 | Accounts nav link present | pass |
| 9 | Accounts row derived balance | `MAD 797.50` |
| 10 | Accounts row imported snapshot | `MAD 999.00` |
| 11 | Snapshot-vs-derived difference flagged | `amountSnapshotDiffers` |
| 12 | Session persists on refresh (`/firebase/dashboard`) | pass |
| 13 | Offline detected | `navigator.onLine === false` |
| 14 | Offline banner shown | pass |
| 15 | Cached data still rendered offline | pass |
| 16 | Recovers when back online | pass |
| 17 | Sign out returns to `/firebase/login` | pass |
| 18 | Login page exposes no ledger data | pass |

### Data imported for the run (synthetic)

Fixture at `/tmp/pilote-2.2/fixture.sqlite`: 3 accounts, 3 categories,
7 transactions, 4 transfers; independently-computed balances
`{1:79750, 2:77500, 3:-3000}`; deliberately-stale snapshots `99900 / -100 /
123456`. Imported under UID `1QaRVG1nNRw58bQKychonGrvW7Ff`.

### Missing-config gate (re-verified in a real browser)

With **no** `frontend/.env.local`, `/firebase/login` renders the **"Not
configured"** screen — confirmed both before the work and again in the final
cleaned state. The production build (no `.env.local`) keeps the emulator flag
off: the emulator URLs are present as inert constants but
`firebaseEmulatorsEnabled` is dynamically read, so it is `false` and no emulator
connection is attempted.

### Test-suite results (final)

| Suite | Result |
|---|---|
| Firebase (emulator) `npm test` | **37 passed / 0 failed** (23 rules + 5 import + 9 smoke E2E) |
| Frontend `npm run test` | **146 passed / 12 files** (`config.test.ts` = 10 incl. emulator-default-OFF gate; `gate.test.ts` = 51 for the Phase 2.3 routing fix) |
| Frontend `npm run typecheck` / `npm run build` | clean |
| Backend `pytest` | **289 passed / 1 warning** |
| Real DB `sha256` before/after | `c7c22d61…4f4c` **unchanged** |
| `no-writes` guard | passes (no financial write APIs) |

### Known limitation found in Phase 2.2 — FIXED in Phase 2.3

Phase 2.2 observed that a **hard refresh or deep link on a non-dashboard
`/firebase/*` subroute** (e.g. `/firebase/accounts`) returned to
`/firebase/dashboard`. The session was preserved (not sent back to login), but
the subroute itself was not honoured on cold load. That auth-initialisation race
is now fixed and re-verified — see §9.

### Not verified in a browser (and why)

- **Real Firebase project path** — would require deploying rules/hosting to a
  disposable project, i.e. an actual deploy, which is out of scope for this
  task.
- **Cross-user / anonymous denial UI** — the permission logic is proven by the
  emulator Rules tests (§6); no browser surface exposes a "permission denied"
  toast, so it was not driven through the UI.

## 9. Routing fix (Phase 2.3) — deep links + hard refresh

### Root cause

`frontend/src/firebase/auth.tsx` had a two-effect initialisation race:

1. State started `initializing = true`, `runtime = null`.
2. The second effect ran on mount with `runtime === null` and called
   `setInitializing(false)`.
3. `getRuntime()` then resolved and `setRuntime(rt)` rendered a frame where
   **`runtime` was set but `initializing` was already `false`** while
   `onAuthStateChanged` had not yet fired, so `user` was still `null`.
4. In that frame `FirebaseAppInner` rendered the router; `RequireAuth` saw no
   user and redirected the requested URL to `/firebase/login`, destroying the
   deep link. The restored session then reached `LoginPage`, which redirected to
   `/firebase/dashboard` — the observed symptom.

### Fix (read-only; no financial or data-model changes)

- **`frontend/src/firebase/gate.ts`** (new, pure): `resolveFirebaseGate()`
  returns `not-configured | error | loading | ready`, and
  `resolveFirebaseRedirect(pathname, gate, isSignedIn)` returns the redirect
  target or `null`. Crucially it **never redirects while the gate is not
  `ready`**, so the intended URL is preserved until auth is known.
- **`frontend/src/firebase/auth.tsx`**: replaced the premature
  `initializing` state with an `authResolved` flag that flips to `true` only when
  the first `onAuthStateChanged` callback fires, and exposed a derived
  `gate`. The loading gate now holds through the runtime→auth gap.
- **`frontend/src/firebase/FirebaseApp.tsx`**: `FirebaseAppInner` now switches
  on the gate (`NotConfigured` / error / loading) and, once ready, computes a
  single redirect via `resolveFirebaseRedirect` before rendering the routes.
  Sign-in, sign-out, loading/error states and the legacy routes are unchanged.
- **`frontend/src/firebase/gate.test.ts`** (new): 51 focused regression tests
  covering the gate states, deep links, trailing slashes, home/login redirects,
  and the full cold-load auth-init race sequences.

No changes to `firestore.rules`, data models, import logic, SQLite, or any
financial write path.

### Verification (local emulator, real headless Chrome)

Driver: `/tmp/opencode/cdp-verify23.mjs` (Node 22 `WebSocket` +
`google-chrome --headless=new`, port 9225). Same synthetic fixture user/data as
§8. **Result: 39/39 checks passed**, including the new deep-link/refresh checks:

| Check | Observed |
|---|---|
| Deep link to each of `/firebase/dashboard\|accounts\|categories\|transactions` stays on that route | pass (all 4) |
| Loading gate rendered before auth resolved on each deep link | pass (all 4) |
| Hard refresh on each sub-route stays on that route | pass (all 4) |
| `/firebase` (signed in) → `/firebase/dashboard` | pass |
| `/firebase/login` (signed in) → `/firebase/dashboard` | pass |
| Signed-out deep links (`/firebase`, `/firebase/dashboard`, `.../accounts`, `.../categories`, `.../transactions`) → `/firebase/login` | pass (all 5) |
| `/firebase/login` (signed out) stays login | pass |
| Core Phase 2.2 checks (login, balances 1542.50 / 2232.56, accounts 797.50 / 999.00, offline banner + recovery, sign-out) | pass |

A 37/39 interim run exposed two **driver** timing bugs (asserting before the
loading gate settled); the driver was corrected to wait for the area to settle
before asserting — no product change resulted from them.

Missing-config re-verified after the refactor: with no `frontend/.env.local`,
`/firebase/login` renders **"Not configured"** (no login form, no loader).

## 10. Remaining manual steps (not automated)

- Optional GUI walk-through by a human: `cd frontend && npm run dev`, set
  `VITE_FIREBASE_USE_EMULATORS=true` in `frontend/.env.local`, open
  `/firebase/login`, sign in as the fixture user, and confirm the read-only
  rendering + "unavailable operations" notice by eye (the CDP run in §8 already
  covers this programmatically).
- Optional emulator-UI inspection of `users/<test-uid>/...` documents.
- Path A (§8's predecessor) — a disposable **real** project walk-through —
  remains available when a deploy is explicitly authorised; it is not part of
  this no-deploy smoke test.
- No step in this document deploys, pushes, commits, enables billing, or
  changes the legacy FastAPI/SQLite app.
