# Pilote Budget — Phase 7 Report: Settings, Onboarding, Backup, Quick Add & Personalization

Date: 2026-10-08 · Scope: the settings write path, first-run onboarding, backup/restore,
one-field quick entry with deterministic suggestions and duplicate protection,
dashboard personalization, assistant question coverage, and data-safety UX.

This report replaces the Phase 6 financial-correctness audit. Every Phase 6 restriction
("Settings is a planned nav item", "no endpoint/UI for month-start day") is now resolved
by a real write path. No money formula changed; the audit's constraints remain binding
(no auth, no cloud sync, no external AI, no bank integrations).

---

## 1. Scope & result summary

Delivered end to end (backend schema/service/route + frontend page/helpers/wiring):

| Feature | Backend | Frontend | Tests |
|---|---|---|---|
| Settings write path | PUT/PATCH settings | Settings page (ready nav) | 5 + 6 helper |
| First-run onboarding | state service + skip | 4-step wizard + banner | 4 |
| Backup / restore | export/validate/restore | download/validate/restore UI | 5 |
| Quick Add | capture + create + reject | topbar modal, suggestions | 4 + 6 helper |
| Suggestions | ledger+recurring ranking | chips (Quick Add + form) | part of above |
| Duplicate protection | same-day/near recognition | UI tone + rejection gate | part of above |
| Dashboard personalization | `months` param | filter + reorder cards | 4 |
| Assistant coverage | +4 intents → 12 | recognized | 5 |

Suites: backend **263 passed** (was 245), frontend **49 passed** (was 37), `tsc -b` clean,
`vite build` clean, live API smoke green.

## 2. Money model integrity

Phase 7 is additive; no verified formula was altered. Analytics gained an optional
`months=1..12` query (validation in `analytics.py`) that caps the history windows
including the current period (default 7) — it does not change any money number, only the
length of history. The dashboard wires `last_three` → `?months=3`.

## 3. Settings write path (`app/api/v1/settings.py`, `settings_service.py`)

- `GET/PUT /api/v1/settings` over profile preferences (previously
  GET `profile` returned the row but there was no write surface for currency,
  month-start day or `minimum_reserve` — Phase 6 limitation #1, now closed).
- `SettingsUpdate` accepts partial payloads; `payload.model_dump(exclude_unset=True)`
  gives true partial updates (send `{currency: "USD"}` and nothing else changes).
- Validation: currency must belong to `domain/currency.SUPPORTED_CURRENCIES`;
  `month_start_day` is an int 1..28; amounts `>= 0`; PATCH semantics for strings/None.
- `_clean_dashboard` merges the stored dashboard preferences with any incoming patch
  and sanitizes the section map + order so unknown ids never leak into the DB and no
  valid preference is lost — `dashboardToggleRow`/`pruneOrder` mirror this contract on
  the frontend so the UI and server sanitize identically.
- Responses typed `SettingsResponse`; `updated_at` refreshed on write.

## 4. Settings UI (`SettingsPage.tsx`, now a ready route)

- **General**: currency (select from `SUPPORTED_CURRENCIES` with symbols), month-start
  day, minimum reserve (feeds Safe-to-Spend's "Minimum reserve" row).
- **Quick defaults**: default expense/income category + default account — wired to the
  server's Quick Add resolution.
- **Assistant**: verbosity (concise/standard) exposed to the rule-based provider.
- **Dashboard**: per-section toggles (12 sections, `DASHBOARD_SECTION_META`) plus
  ↑/↓ reordering; period (`current_month` / `last_three`) controls the 3-month window.
- Loads current values, optimistic-save via `apiPut` with `exclude_unset` behavior,
  inline error/success and pending disables. Navigation entry promoted to **ready**.

## 5. First-run onboarding (`onboarding_service.py` + `OnboardingPage.tsx`)

- State is **derived from persisted data**, never a flag: `completed` = at least one
  account + one category (+ optional budget/goal); `skipped` stored in preferences.
- Four-step wizard (account → categories → budget → goals with the last two optional),
  per-step completion rail with progress %, currency chosen at the end.
- "Skip onboarding" sets `skipped: true`. A topbar banner in `AppShell` links to
  `/onboarding` while incomplete and not skipped; it disappears automatically once the
  state turns complete. Route registered in `App.tsx`.

## 6. Backup & restore (`backup_service.py`, `app/api/v1/backup.py`)

- `GET /api/v1/backup/export` → envelope `{format, version, exported_at, counts[{table,
  rows}], data}`; tables exported in dependency order.
- `POST /api/v1/backup/validate` reads the envelope, verifies format/version (rejects
  future versions) and pre-checks FK references without touching the DB.
- `POST /api/v1/backup/restore` requires `confirmed: true`, re-validates format/version,
  requires a non-empty `profiles` payload, then deletes all rows and re-inserts them in
  dependency order (categories: roots before children) inside one rollback-safe
  transaction — a failure mid-restore leaves the previous data intact.
- Settings backup section: **Export** (download JSON), **Validate** (paste + check),
  **Restore** (paste + confirm modal listing per-table counts). Restore has no
  reload-after inside the modal; the page reflects state on next visit.

## 7. Quick Add (`quick_service.py`, `app/api/v1/quick.py`)

- `POST /api/v1/quick/capture`: type + amount + description + date → resolved defaults
  from settings (account, category ids), deterministic ranking suggestions and a
  duplicate scan. **No write.**
- `POST /api/v1/quick/transactions`: creates the row, optionally rejecting/checking
  duplicates; returns the created transaction + duplicates + warnings.
- Frontend global modal (topbar **Quick add** button in `AppShell`): kind toggle,
  description/amount/date, live suggestion chips, duplicate tone banner, "Save & add
  another" (keeps modal open, notifies the data-change bus so the Transactions page
  refetches) and a plain "Add". Amount defaults from server rules; account from Settings.

## 8. Deterministic suggestions (`suggestion_service.py`, `lib/quick.ts`)

- Ranking source-of-truth: **post history + recurring templates** aggregated server-side
  (no ML). `normalize()` folds case/whitespace/punctuation; `rank()` scores by confidence
  tier (`exact` (verbatim seen) → `similar` (fuzzy, ≥0.7 similarity / token overlap) →
  `popular` (most-used category)) then by count/recency. Up to 5 returned with per-category
  evidence strings.
- Client `bestSuggestions`/`topSuggestion` sort/shortlist for chips; the first ranked by
  the server becomes the preselected chip in Quick Add.
- Explicit `Category` joins (not `label()` on a relationship) after a fixture caught a
  boolean-mislabeled join in an intermediate version.

## 9. Duplicate protection (`quick_service` + `TransactionForm.tsx`)

- Duplicate keys on **same account + same category + rounded amount + description
  normalized**; `same_day` when the hit is on the same calendar day, else `near`
  (within 5 days) — the two tones drive different UX.
- Quick Add: same-day duplicates are refused by the server
  (`reject_duplicate` false → 409); the banner explains the refusal.
- New-expense form: `/quick/capture` feedback is used to render chips and a
  warning; a same-day add is **blocked in the UI** with a "Add anyway" escape hatch
  (the plain `/transactions` POST has no server guard — see Limitations).

## 10. Dashboard personalization (`lib/settings.ts` + `DashboardPage.tsx`)

- `orderedVisibleSections(sections, order)` returns the ordered, visible ids, appending
  any section the settings map lacks; `dashboardToggleRow`/`pruneOrder` give the settings
  editor a stable form state.
- Dashboard fetches settings; `usesThreeMonthHistory(period)` switches the analytics
  window to `?months=3`. Every section (12) is visibility-gated, and layout order is
  honoured with CSS `order` from the stored sequence — so the Settings ↑/↓ order is
  reflected live on the dashboard. When settings are absent/failing it renders the
  canonical layout (fail-open).
- `app/api/v1/analytics.py` now caps `months` (1..12, default 7).

## 11. Assistant question coverage (`domain/financial_assistant.py`)

- Four new intents bring the question bank to **12**: `upcoming` (recurring occurrences
  in the next window), `net_worth_contributors` (what drives net worth),
  `insights` (prioritized rule insights) and `goals_progress` (progress across goals).
- `match_intent` ordering is deliberate: `goals_progress` before `goal_eta` because the
  broad word "goal" matches both. No-data guard excludes
  `{goal_eta, net_worth, net_worth_contributors, upcoming}` so those never fabricate
  numbers. `_state` now carries prioritized `insights` and `upcoming` rows fed by
  `RecurringService`.

## 12. Frontend wiring & data-safety UX

- Routes: Settings + Onboarding registered in `App.tsx`; settings navigation status →
  ready (analytics stays planned).
- `src/lib/refresh.ts` + `useDataChangedReload` bus: a global Quick Add posts and notifies
  pages (Transactions page refetches) without a global store.
- Destructive-action confirmations were already present on every delete surface
  (accounts archive-warn, categories, goals, debts, recurring templates, transactions);
  audited, no gaps.
- Restore carries its own confirmation modal with per-table counts — double confirmation
  on an irreversible action.

## 13. Type/int test fixes

- `pruneOrder` widened to `string[]` so the "server may not know every section yet" test
  compiles; `settings.test.ts` casts the partial sections object to the real type.
- `SettingsPage` cleaned of unused imports and an out-of-scope `accounts` reference in the
  (now removed) backup-empty hint.
- `tsc -b` clean across the app after the new pages/hooks/components.

## 14. Backend tests (`tests/test_phase7_features.py` — 18 new)

Settings defaults + partial update + validation + dashboard roundtrip; analytics `months`
validation and range; onboarding states (empty/skipped/complete); quick capture defaults +
create + same-day reject; backup export envelope / validate / restore roundtrip / must
confirm / corrupt & future-version rejection / missing profile rejection; assistant new
intents + routing + no-data upcoming handling. Stale `test_assistant.py` assertion updated
(8 → 12 intents).

## 15. Verification

- Backend: **263 pytest passed** (0 failures).
- Frontend: **49 vitest passed**, `tsc -b` clean, `vite build` clean (102 modules).
- Live smoke on the running backend (`127.0.0.1:8000`): `/settings`,
  `/settings/onboarding`, `/analytics?months=3`, `/quick/capture`,
  `/backup/export`, assistant `upcoming` intent — all 200 with correct bodies.
  The `/health` path correctly requires the `/api/v1` prefix (not a regression).
- The Vite dev server is available via `npm run dev`; the app+API bundle green.

## 16. Known limitations (intentional or out of scope)

- **Plain `/transactions` POST has no server-side duplicate guard** — only Quick Add
  enforces same-day rejection server-side. The transaction form blocks same-day re-entry
  in the UI with an explicit override; a future hardening could move the guard into
  `transaction_service.create`.
- **Restore keeps modal open after success** — the page reflects restored data on next
  navigation; auto-refresh of every cached hook was intentionally avoided.
- No **multi-user/auth**, **cloud/drive backup**, **bank imports** or **external AI**: the
  assistant stays rule-based behind the provider abstraction (LLM-ready later); backups
  are local JSON files by design.
- `domain/calculations.py` alternate-sign helpers remain reference-only (Phase 6 note).

---

### How to run the checks

```
cd backend && uv run pytest                 # 263 passed
cd frontend && npm run test && npm run typecheck && npm run build
# live: backend on :8000 (uvicorn, script at /tmp/opencode/start_backend.sh),
#       frontend dev server on :5173 (npm run dev)
```