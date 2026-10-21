# Pilote Budget — Firebase Spark deployment guide

Spark-only. **Never** attach a billing account. If a step would require Blaze,
it is deliberately not described here — see `FIREBASE_MIGRATION_PLAN.md` §4.

---

## 0. What this deliverable contains

| Artifact | Location | Purpose |
|---|---|---|
| Migration plan + capability matrix + STOP list | `FIREBASE_MIGRATION_PLAN.md` | Decisions, honest limitations |
| Firestore security rules | `firebase/firestore.rules` | UID-scoped access + shape enforcement |
| Composite indexes | `firebase/firestore.indexes.json` | Feed/ledger queries |
| Emulator + tooling config | `firebase/firebase.json`, `.firebaserc` | Local test + deploy context |
| Rules tests (14) | `firebase/tests/rules.test.js` | Auth/ownership/shape guarantees |
| Import tool E2E (5) | `firebase/tests/import.test.js` | SQLite → Firestore operator migration |
| Operator import CLI | `firebase/tools/import-sqlite-to-firestore.mjs` | One-way, manual, validated migration |

Nothing has been deployed or pushed to Firebase. The pipelined repo commit
`f6398a6` (Render deployment) is untouched.

## 1. Local emulator + tests

Firestore emulator is a Java jar; the developer machine here has **no system
Java** and **no passwordless sudo**, so a rootless Temurin 17 JRE is used
(extracted to `/tmp/jre` — re-extract anywhere and point `JAVA_HOME` at it).

```bash
cd firebase
export JAVA_HOME=/path/to/jre   # e.g. /tmp/jre
export PATH="$JAVA_HOME/bin:$PATH"

# One terminal: start the emulator
npm run emulators:start
#   Firestore emulator: http://127.0.0.1:8080

# Another terminal: run all 19 firebase tests (rules + import)
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 npm test
```

Expected: `# tests 19 # pass 19 # fail 0`.

## 2. Create the Firebase project (Console, Spark only)

1. https://console.firebase.google.com → Add project (name e.g. `pilote-budget`).
   Skip Analytics. **Do not** confirm any paid plan; the free Spark tier has no
   card required.
2. **Authentication → Sign-in method → Email/Password → Enable.**
3. **Firestore Database → Create database** in production mode. Location EU or
   your region. The rules below are per-user scoped regardless of mode.
4. **Add a web app** (Hosting): Take note of the `appId`, `apiKey`,
   `authDomain`, `projectId`, `storageBucket`, `messagingSenderId`.
   This web config is **public client config** — it is safe to embed in the
   frontend; it is NOT a service-account key.

## 3. Deploy rules + indexes (no code, no billing impact)

```bash
cd firebase
firebase login
firebase use pilote-budget          # or edit .firebaserc before deploying

# Deploy ONLY the security layer (rules are the migration's core deliverable)
firebase deploy --only firestore:rules
firebase deploy --only firestore:indexes
```

Sanity check in the Console: *Firestore → Rules* should show the UID-scoped
rules; try the rules playground as an unauthenticated user → all reads/writes
denied; as your user → only your own `users/{uid}/…` paths allowed.

> Only deploy `firestore:rules`/`firestore:indexes`. The shipped frontend is
> still wired to the FastAPI/Render API, **not** yet to Firestore (full app port
> is on the STOP list — plan §4 C-7), so do **not** deploy Hosting for a
> functioning Firebase-integrated app yet.

## 4. Operator-run data migration (SQLite → Firestore)

The importer is **manual and one-way**. It never runs automatically, never
writes unless told, and never accepts credentials as arguments.

```bash
# 1. Get the Firebase Auth UID of the target user (manual Console step)
#    Authentication → Users → copy the UID (or use a custom Token Service).

# 2. Create a service-account JSON for the import ONLY (Console:
#    Project settings → Service accounts → Generate new private key).
#    Password-protect it, keep it out of the repo (git-ignored under
#    firebase/), delete it after the migration if you prefer.

export GOOGLE_APPLICATION_CREDENTIALS=/secure/path/service-account.json
export GOOGLE_CLOUD_PROJECT=pilote-budget

npx is not required for the tool; it uses the project's `firebase-admin`
dependency. Prefer importing against the **emulator first**, then production:

```bash
cd firebase

# Dry-run first (writes nothing)
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 \
  node tools/import-sqlite-to-firestore.mjs \
  --db ../backend/data/pilote_budget.db --uid UID

# Review counts, cents totals, warnings (stale cached balances are warned).

# Commit (requires --yes on an operator terminal)
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 \
  node tools/import-sqlite-to-firestore.mjs \
  --db ../backend/data/pilote_budget.db --uid UID --yes
```

For production migration set the service-account env (above) **instead of**
`FIRESTORE_EMULATOR_HOST`. The tool:

- stores every amount as integer cents;
- marks imported ledger rows `imported: true` → rules make them immutable
  against edits by the app;
- verifies FK references and re-derives account balances, printing drift vs the
  cached `current_balance` as warnings (derived value is authoritative);
- writes an `users/{uid}/imports/{runId}` fingerprint document (sha256 over the
  plan: counts + cents sums + schema version);
- is idempotent on re-run (merge semantics) but still requires `--yes`.

## 5. Rolling back

- **Rules:** Console → Firestore → Rules shows the previous deployment; press
  *Revert*. Or `git checkout <old> -- firebase/firestore.rules && firebase
  deploy --only firestore:rules`.
- **Data:** the migration is additive to `users/{uid}/…`; delete docs with a
  one-off admin script if a mistake is made. There is no automatic wipe.
- **Hosting:** if ever deployed, previous versions remain in Console →
  Hosting → Release history.

## 6. Security checklist (post-deploy)

- [ ] Anonymous/unauthenticated requests return `PERMISSION_DENIED`.
- [ ] A second authenticated user cannot read another user's documents (tested
      in `rules.test.js`, cross-UID isolation).
- [ ] Money fields are integer cents; float values are rejected by rules.
- [ ] Imported ledger rows can't be edited by the app (immutable).
- [ ] No service-account key appears in `git status` output (gitignore covers
      `firebase/node_modules`, `*.log`, and any `*.json` secrets via `.env*` /
      `credentials` patterns — verify with `git check-ignore`).
- [ ] Billing remains **Spark**; no Functions/Cloud Run/Paid services exist.