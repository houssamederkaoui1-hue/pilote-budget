# Pilote Budget — Firebase Spark Migration Plan

Status: **planning** (switched to Firebase after the Render deployment was
committed and pushed as `f6398a6`). FastAPI/SQLite backend stays intact; this
is the design for a Spark-only migration path.

Hard constraints (from product owner):

1. **Firebase Spark free tier only.** No payment method, no Blaze, no Cloud
   Functions, no Cloud Run, no App Engine, no paid services. If a backend is
   effectively required, the feature is **stopped and reported**, never faked.
2. Clients talk to Firestore **directly**. Never embed service-account / admin
   keys in frontend bundles. Operators may use firebase-admin **only** in an
   operator-run import tool, with credentials supplied via env at runtime, never
   committed.
3. The FastAPI/SQLite implementation remains the reference for formulas and
   invariants. The frontend's service worker must keep **not** caching `/api/*`
   or Firestore responses.
4. Never deploy, push, or import personal data automatically.

The current Firestore backend (emulator) is a stand-in used to *prove*
rules/auth behaviour; nothing below is deployed.

---

## 1. What the app does today (backend surface)

All routes below were pulled from `backend/app/api/v1/`. Every router except
`/health` and `/config` is behind `require_auth` when `PILOTE_ACCESS_TOKEN` is
set (an app-level bearer token — **no per-user identity** today).

### 1.1 Endpoint inventory

| Method | Path | Purpose | Server-enforced work |
|---|---|---|---|
| GET | `/api/v1/health` | liveness | — |
| GET | `/api/v1/config` | public bootstrap (auth flag, currency, features) | — |
| GET | `/api/v1/profile` | profile | read |
| PUT-like | `/api/v1/profile` (PATCH) | update | validate + persist |
| GET/PUT | `/api/v1/settings` | settings | read/validate |
| GET/PUT | `/api/v1/settings/onboarding` | onboarding flags | read/validate |
| GET/POST | `/api/v1/accounts` | list/create account | create + **BalanceService.sync** |
| GET/PATCH/DELETE | `/api/v1/accounts/{id}` | get/update/delete | FK guard, recompute balances |
| POST | `/api/v1/accounts/{id}/archive` | archive | recompute = 0? re-derive |
| POST | `/api/v1/accounts/{id}/activate` | restore | recompute |
| GET/POST | `/api/v1/categories` | list/create | persistence |
| GET/PATCH/DELETE | `/api/v1/categories/{id}` | get/update/delete | reparent guard, cascade |
| POST | `/api/v1/categories/{id}/archive`, `/activate` | lifecycle | guard default category |
| GET/POST | `/api/v1/budgets`, PUT `/api/v1/budgets` | budget + allocations | validate allocation sums |
| POST | `/api/v1/transactions` | create tx | insert in **DB transaction** |
| GET | `/api/v1/transactions` | list (paging 50/500, filters) | UNION ALL tx+transfer, page |
| GET | `/api/v1/transactions/summary` | income/expense/net | `BalanceService.summary` |
| GET | `/api/v1/transactions/export.csv` | CSV export | build CSV |
| GET/PATCH/... | `/api/v1/transactions/{id}` | get/update/delete | recompute balances |
| POST | `/api/v1/transactions` (transfer) | create transfer | **double-entry insert in one DB transaction** |
| GET/PATCH/DELETE | `/api/v1/transfers/{id}` | get/update/delete | **double-entry update/delete** |
| GET | `/api/v1/analytics` | monthly trend, by-category, top spending | heavy SQL aggregation |
| GET | `/api/v1/analytics/safe-to-spend` | safe-to-spend | `safetospend` calc |
| GET | `/api/v1/overview` | dashboard aggregates | aggregation + upcoming |
| GET | `/api/v1/goals` | goals | read |
| POST | `/api/v1/goals` | create goal | persist |
| GET/PATCH/DELETE | `/api/v1/goals/{id}` | goal CRUD | persist |
| GET/POST/PATCH/DELETE | `/api/v1/recurring` | recurring templates | persist |
| GET | `/api/v1/recurring/upcoming` | upcoming materialisation | date math + projection |
| POST | `/api/v1/recurring/{id}/record` | materialise one instance | **creates tx + advances schedule state** |
| POST | `/api/v1/recurring/{id}/advance` | advance next date | date math |
| GET | `/api/v1/debts`, `/debts/totals` | debts + totals | aggregate |
| POST/PATCH/DELETE | `/api/v1/debts/{id}` | debt CRUD | persist |
| GET | `/api/v1/assistant` | assistant overview | aggregation |
| POST | `/api/v1/assistant/ask` | Q&A | **LLM + data reasoning** |
| POST | `/api/v1/quick/capture` | stateful capture | multi-rule diffing + validation |
| POST | `/api/v1/quick/transactions` | quick create | create tx + sync balances |
| POST | `/api/v1/backup/export` | envelope export | `TABLE_ORDER` envelope build |
| POST | `/api/v1/backup/validate` | restore dry-run | `validate_envelope` |
| POST | `/api/v1/backup/restore` | restore | **full teardown + ordered insert in txn** |
| POST | `/api/v1/import/inspect` , `/preview`, `/commit` | CSV import 3-phase | stateless parse → diff → **dedupe + batch insert** |

### 1.2 Schema summary (SQLite via SQLAlchemy)

All money columns are `Numeric(19,4, asdecimal=False)` = floats on the wire.
Ten tables (`TABLE_ORDER` from `domain/backup.py`): `profiles`, `categories`
(self-referencing `parent_id`, ordered seed), `accounts`, `budget_allocations`,
`goals`, `debts`, `budgets`, `transactions`, `transfers`,
`recurring_transactions`.

- Transactions: `type` in {income, expense}, `status` in {pending, cleared,
  reconciled, void}; void excluded from all money math.
- Transfers: `status` in {pending, completed, cancelled}; cancelled excluded.
  A transfer **is** two ledger rows (source `-amount`, destination `+amount`)
  written atomically server-side.
- Balances: `Account.current_balance` is a *cache* refreshed only by
  `BalanceService.sync`. The single source of truth is the formula:
  `opening_balance + Σ(income) - Σ(expense) + Σ(incoming transfers) - Σ(outgoing transfers)`.
- Recurring: template rows with `next_date`; `/record` materialises a
  transaction and mutates schedule state atomically.
- `MoneyType` precision: backend rounds to 2 decimals for display but computes
  with 4.

### 1.3 Current trust model

App-level single bearer token (`PILOTE_ACCESS_TOKEN`) gate or open. There is no
per-user isolation yet. Firestore rules introduce the first real
per-user/per-file trust boundary in the product.

---

## 2. Firestore target design (Spark-only, no backend)

Path scheme — every document is name-spaced under the authenticated user's UID:

```
users/{uid}/profile/{profile}                          (single doc, id "me")
users/{uid}/settings/{settings}                        (single doc, id "me")
users/{uid}/categories/{categoryId}
users/{uid}/accounts/{accountId}                       (codegen id, has openingBalance)
users/{uid}/transactions/{transactionId}               (type, status, cents)
users/{uid}/transfers/{transferId}                     (source/destination ids, cents)
users/{uid}/allocations/{monthId}                      (per-month budget envelope)
users/{uid}/budgets/{monthId}-c{categoryId}            (per-category budget)
users/{uid}/goals/{goalId}
users/{uid}/debts/{debtId}
users/{uid}/recurring/{recurringId}
users/{uid}/imports/{runId}                            (import fingerprint bookkeeping)
```

Rules enforce three layers only: **identity** (`request.auth.uid == uid`),
**collection scoping**, and **field-shape allowlisting** for the money-heavy
collections. They cannot (by design of Firestore) enforce cross-document
invariants; that is state the client must maintain, and is precisely where the
*secure* line is drawn.

### 2.1 Money encoding

Money is stored as **integer cents** (`amountCents`) plus a `currency` string on
the enclosing profile/settings for multi-currency. Integer cents remove JS
float drift and match the API's 2-decimal display semantics. `openingBalance`,
`currentBalance`, budget amounts, goal/debt amounts, transfer `amount` all use
cents. The import tool converts with `round(x*100)`; the export path renders
`cents/100` with 2 decimals.

### 2.2 Identity & per-user isolation

Firebase Auth (email/password) is the identity source; `auth.uid` is the only
key used in Firestore paths and rules. Provisions:

- `allow read, write: if request.auth != null && request.auth.uid == uid;`
- No `users`-level collection writes are ever possible (rules only grant scoped
  subcollection access).
- A transfer row's `sourceAccountId`/`destinationAccountId` live inside the same
  user subcollection, so cross-user leakage is impossible at the path level.
- Firestore Security Rules do **not** guarantee "a transfer touched two
  accounts" — that invariant is impossible to express in rules and is marked
  **blocked** (see §4, C-1/C-2).

---

## 3. Capability matrix

Legend: **A** = direct port, client-safe. **B** = portable client-side with
documented approach (not server-enforced). **C** = cannot be done securely
without a trusted backend → **STOP and report** per owner rule, not faked.

| # | Capability | Class | Approach / blocker |
|---|---|---|---|
| 1 | Email/password auth + per-uid scoping | **A** | Firebase Auth, rules (implemented) |
| 2 | Profile, settings, onboarding flags | **A** | single-doc CRUD |
| 3 | Categories tree + order + seed | **A** | parentId + order; maintain 14-row seed on account creation |
| 4 | Accounts (open, edit, archive) | **A** | raw docs; `currentBalance` stored as cache during import |
| 5 | Transactions CRUD + paging | **A** | raw docs, client queries; rules shape-checked |
| 6 | Budgets + allocations | **B** | client validation of allocation sums (not rules-enforceable) |
| 7 | Transfers create/read | **B** | write 2 ledger docs as best effort; **no rule can enforce pairing** → see C-1 |
| 8 | Import CSV 3-phase | **B** | client parses CSV (papaparse already used); dedupe fingerprint in `meta/imports`; pairing unguaranteed |
| 9 | Recurring templates + upcoming | **B** | date math ported verbatim; materialisation is client-initiated |
| 10 | Overview / summary / net worth | **B** | client aggregates open ledger docs; formula ported |
| 11 | Analytics trends / by-category / top | **B** | client reduce; precision via cents |
| 12 | Safe-to-spend formula | **B** | port `safetospend` math; input = local ledger snapshot |
| 13 | Goals / debts + totals | **B** | client sums (cents) |
| 14 | Backup/restore | **B** | JSON envelope of Firestore docs; restore = idempotent client writes; **envelope integrity unenforced** (C-4) |
| 15 | Multi-device offline, cross-instance consistency | **B** | Firestore offline cache; **no server-side transactions/locks** |
| 16 | C-1 Transfer double-entry guarantee | **C** | rules cannot hold two-row writes atomic → **STOP/report** |
| 17 | C-2 Balance single-source-of-truth | **C** | no server `sync()`; cache can drift if two devices write concurrently → **STOP/report** |
| 18 | C-3 Recurring materialisation on a server schedule | **C** | needs scheduled compute (Functions = Blaze) → **STOP/report** |
| 19 | C-4 Dedupe enforcement / import-in-transaction | **C** | needs server transaction → **STOP/report** |
| 20 | C-5 Backup envelope validation & integrity | **C** | needs server-side validator → **STOP/report** |
| 21 | C-6 Financial Assistant (LLM + data reasoning) | **C** | needs server + secret LLM key → **STOP/report** |
| 22 | C-7 Full PWA feature port (all pages rewired) | **C** | blocked by C-1..C-6; client-only app would silently drop guarantees → **DO NOT ship as "migrated"** |

---

## 4. STOP list (per owner rule — reported, not worked around)

Anything in class C is **reported with a recommendation**, and no code path is
added that pretends to provide the guarantee. For this migration the honest
stop points are:

- **C-1 transfer double-entry**, **C-2 balances from one server source**,
  **C-3 scheduled recurring materialisation**, **C-4 transactional import
  dedupe**, **C-5 envelope-validated backup**, **C-6 financial assistant**,
  **C-7 the full feature-level frontend port.**

The client-side app in "B" mode is fine for single-device hobby use but is not a
trustworthy replacement for a money ledger, so the product recommendation is:
**either (a) accept per-user single-device trust model expressly, or (b) enable
Blaze + Cloud Functions to preserve the guarantees** — that is owner-provider
decision, not this task's.

---

## 5. Scope of THIS delivery

Implementable and verified in this session:

1. This plan.
2. `firebase/` tooling workspace + rootless Java Firestore emulator **and**
   Docker fallback, whichever proves stable.
3. `firestore.rules` (identity + scoping + shape checks), `firestore.indexes.json`,
   `firebase.json`, `.firebaserc` (placeholder id).
4. Emulator-based rules unit tests (`@firebase/rules-unit-testing`).
5. Operator-run `import-sqlite-to-firestore` CLI (`--dry-run`, `--yes`,
   cents conversion, count/total validation, id mapping, import fingerprint),
   plus an E2E test against the emulator.
6. `FIREBASE_DEPLOYMENT.md` — Spark-only deploy + manual Console steps.
7. Existing backend + frontend suites stay green.

Not delivered: the full frontend port (C-7) and all class-C guarantees, per §4.

## 6. Verification status (this session)

- Rootless local JDK (Temurin 17, extracted under `/tmp/jre`, no sudo) runs the
  official Cloud Firestore emulator jar via `firebase-tools` — Docker was not
  needed. Emulator exposed at `127.0.0.1:8080`.
- `firebase/firestore.rules` + `firestore.indexes.json` + `firebase.json` +
  `.firebaserc` are in place with a placeholder project id (never deployed).
- `@firebase/rules-unit-testing` suite (`firebase/tests/rules.test.js`, 14 cases)
  passes against the emulator: anonymous deny, cross-UID isolation, integer-cent
  enforcement, shape allow-listing per collection, immutable imported rows,
  `imports/` append-only bookkeeping, catch-all deny.
- Field shapes in the rules are derived from the **real SQLite schema**
  (verified via `PRAGMA table_info` on the operator's DB) and the exact enum set
  from `backend/app/domain/enums.py`, not from guesses.
- Operator import tool (`firebase/tools/import-sqlite-to-firestore.mjs`) is
  DRY-RUN by default, requires `--yes`, never auto-runs, refuses to run without
  a credential target, stores money as integer cents, marks ledger rows
  `imported: true`, validates FK + re-derives balances, and writes an import
  fingerprint doc. Its emulator E2E (`firebase/tests/import.test.js`, 5 cases)
  passes: 19/19 emulator tests total, green.
- Ledger integrity check compares re-derived account balances with the cached
  `current_balance` column and reports drift as warnings (cached is a stale
  projection; the derived value is authoritative).