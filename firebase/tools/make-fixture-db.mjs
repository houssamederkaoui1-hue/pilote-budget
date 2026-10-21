#!/usr/bin/env node
/**
 * make-fixture-db.mjs
 *
 * SAFE fixture generator for the Firebase smoke test. It creates a disposable
 * SQLite database containing ONLY fabricated accounts / categories /
 * transactions / transfers, using the exact schema the operator importer
 * expects. It never reads or writes the real ledger.
 *
 * Safety properties:
 *   - `assertSafeDbPath()` refuses any path that resolves to
 *     `backend/data/pilote_budget.db` (or anywhere under `backend/data/`), so a
 *     fixture can never be generated on top of real data.
 *   - The default output path is inside the OS temp directory, never the repo.
 *   - The importer itself opens the generated DB read-only (`query_only`), so
 *     these tests cannot mutate the fixture either.
 *
 * Usage:
 *   node tools/make-fixture-db.mjs [--out /tmp/pilote-smoke/fixture.sqlite]
 *
 * The CLI prints JSON: { dbPath, counts, expectedBalances } where
 * `expectedBalances` is accountId -> integer cents, computed independently from
 * the seed rows below (same rule as backend BalanceService).
 */

import { mkdirSync, rmSync } from 'node:fs';
import { dirname, join, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';
import Database from 'better-sqlite3';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, '..', '..');
export const REPO_ROOT_DIR = REPO_ROOT;
export const REAL_DB = resolve(REPO_ROOT, 'backend', 'data', 'pilote_budget.db');
const BACKEND_DATA_DIR = resolve(REPO_ROOT, 'backend', 'data');

/**
 * Guard: throw if `dbPath` could be the real backend database. Exported so the
 * smoke test can prove the guard works and that fixtures are disposable.
 */
export function assertSafeDbPath(dbPath) {
  const target = resolve(dbPath);
  const underBackendData =
    target === BACKEND_DATA_DIR || target.startsWith(BACKEND_DATA_DIR + sep);
  if (
    target === REAL_DB ||
    underBackendData ||
    target.endsWith(`${sep}pilote_budget.db`)
  ) {
    throw new Error(
      `Refusing to use "${target}" as a fixture: it matches the real backend ` +
        `database. Fixtures must live in a disposable location (e.g. os.tmpdir()).`
    );
  }
  return target;
}

/* ------------------------------------------------------------------ */
/*  Seed data (fabricated; no real names, amounts or accounts)         */
/* ------------------------------------------------------------------ */

export const PROFILE = {
  id: 1,
  currency: 'MAD',
  month_start_day: 1,
  timezone: 'UTC',
  preferences: '{}',
};

export const CATEGORIES = [
  { id: 10, name: 'Salary', type: 'income', parent_id: null, active: 1, description: null },
  { id: 11, name: 'Groceries', type: 'expense', parent_id: null, active: 1, description: null },
  { id: 12, name: 'Transport', type: 'expense', parent_id: null, active: 1, description: null },
];

// current_balance is deliberately wrong on every row so we can prove the
// imported snapshot is stale and that derived balances are authoritative.
export const ACCOUNTS = [
  { id: 1, name: 'Smoke Checking', type: 'checking', opening_balance: 100.0, current_balance: 999.0, currency: 'MAD', active: 1, description: null },
  { id: 2, name: 'Smoke Savings', type: 'savings', opening_balance: 500.0, current_balance: -1.0, currency: 'MAD', active: 1, description: null },
  { id: 3, name: 'Smoke Cash', type: 'cash', opening_balance: 0.0, current_balance: 1234.56, currency: 'MAD', active: 1, description: null },
];

export const TRANSACTIONS = [
  { id: 1, account_id: 1, category_id: 10, type: 'income', amount: 1000.0, date: '2026-01-05', description: 'Salary', status: 'cleared' },
  { id: 2, account_id: 1, category_id: 11, type: 'expense', amount: 42.5, date: '2026-01-06', description: 'Groceries', status: 'cleared' },
  { id: 3, account_id: 1, category_id: 12, type: 'expense', amount: 10.0, date: '2026-01-07', description: 'Bus', status: 'pending' },
  { id: 4, account_id: 1, category_id: 10, type: 'income', amount: 9999.0, date: '2026-01-08', description: 'VOID income (excluded)', status: 'void' },
  { id: 5, account_id: 2, category_id: 10, type: 'income', amount: 25.0, date: '2026-01-09', description: 'Interest', status: 'reconciled' },
  { id: 6, account_id: 3, category_id: 12, type: 'expense', amount: 30.0, date: '2026-01-10', description: 'Taxi', status: 'cleared' },
  { id: 7, account_id: 1, category_id: 11, type: 'expense', amount: 100.0, date: '2026-01-11', description: 'VOID expense (excluded)', status: 'void' },
];

export const TRANSFERS = [
  { id: 1, source_account_id: 1, destination_account_id: 2, amount: 200.0, date: '2026-01-12', description: 'To savings', status: 'completed' },
  { id: 2, source_account_id: 1, destination_account_id: 2, amount: 50.0, date: '2026-01-13', description: 'To savings (pending)', status: 'pending' },
  { id: 3, source_account_id: 2, destination_account_id: 1, amount: 999.0, date: '2026-01-14', description: 'CANCELLED (excluded)', status: 'cancelled' },
  { id: 4, source_account_id: 1, destination_account_id: 3, amount: 10.0, date: '2026-01-15', description: 'CANCELLED (excluded)', status: 'cancelled' },
];

const POSTED_TX = new Set(['pending', 'cleared', 'reconciled']);
const POSTED_TR = new Set(['pending', 'completed']);
const toCents = (v) => Math.round((Number(v) || 0) * 100);

/**
 * Independent restatement of BalanceService.compute_all() in integer cents:
 * opening + posted income - posted expenses + incoming - outgoing posted
 * transfers. Void transactions and cancelled transfers are excluded. Exported
 * so the smoke test can compare Firestore-derived values against it.
 */
export function expectedBalances() {
  const balances = new Map(ACCOUNTS.map((a) => [String(a.id), toCents(a.opening_balance)]));
  for (const tx of TRANSACTIONS) {
    if (!POSTED_TX.has(tx.status)) continue;
    const cents = toCents(tx.amount);
    const key = String(tx.account_id);
    balances.set(key, (balances.get(key) ?? 0) + (tx.type === 'income' ? cents : -cents));
  }
  for (const tr of TRANSFERS) {
    if (!POSTED_TR.has(tr.status)) continue;
    const cents = toCents(tr.amount);
    const src = String(tr.source_account_id);
    const dst = String(tr.destination_account_id);
    balances.set(src, (balances.get(src) ?? 0) - cents);
    balances.set(dst, (balances.get(dst) ?? 0) + cents);
  }
  return Object.fromEntries(balances);
}

/* ------------------------------------------------------------------ */
/*  Schema + build                                                     */
/* ------------------------------------------------------------------ */

export const SCHEMA_SQL = `
  CREATE TABLE profiles (
    id INTEGER PRIMARY KEY, currency VARCHAR(3), month_start_day INTEGER,
    timezone VARCHAR(64), preferences JSON, created_at DATETIME, updated_at DATETIME);
  CREATE TABLE categories (
    id INTEGER PRIMARY KEY, name VARCHAR(120), type VARCHAR(7), parent_id INTEGER,
    active BOOLEAN, description TEXT, created_at DATETIME, updated_at DATETIME);
  CREATE TABLE accounts (
    id INTEGER PRIMARY KEY, name VARCHAR(120), type VARCHAR(11),
    opening_balance DOUBLE, current_balance DOUBLE, currency VARCHAR(3),
    active BOOLEAN, description TEXT, import_metadata JSON,
    created_at DATETIME, updated_at DATETIME);
  CREATE TABLE budget_allocations (
    id INTEGER PRIMARY KEY, month DATE, income_amount DOUBLE, needs_amount DOUBLE,
    wants_amount DOUBLE, savings_amount DOUBLE, other_amount DOUBLE,
    created_at DATETIME, updated_at DATETIME);
  CREATE TABLE goals (
    id INTEGER PRIMARY KEY, name VARCHAR(120), target_amount DOUBLE,
    current_amount DOUBLE, target_date DATE, account_id INTEGER, active BOOLEAN,
    notes TEXT, created_at DATETIME, updated_at DATETIME);
  CREATE TABLE debts (
    id INTEGER PRIMARY KEY, name VARCHAR(120), creditor VARCHAR(120),
    original_amount DOUBLE, remaining_amount DOUBLE, interest_rate NUMERIC(6,3),
    minimum_payment DOUBLE, due_date DATE, account_id INTEGER, active BOOLEAN,
    notes TEXT, created_at DATETIME, updated_at DATETIME);
  CREATE TABLE budgets (
    id INTEGER PRIMARY KEY, month DATE, category_id INTEGER, planned_amount DOUBLE,
    notes VARCHAR(255), created_at DATETIME, updated_at DATETIME);
  CREATE TABLE transactions (
    id INTEGER PRIMARY KEY, account_id INTEGER, category_id INTEGER,
    type VARCHAR(8), amount DOUBLE, date DATE, description VARCHAR(255),
    notes TEXT, status VARCHAR(10), import_batch_id VARCHAR(64),
    external_id VARCHAR(128), import_metadata JSON,
    created_at DATETIME, updated_at DATETIME, dedupe_key VARCHAR(128));
  CREATE TABLE transfers (
    id INTEGER PRIMARY KEY, source_account_id INTEGER, destination_account_id INTEGER,
    amount DOUBLE, date DATE, description VARCHAR(255), notes TEXT,
    status VARCHAR(9), source_transaction_id INTEGER, destination_transaction_id INTEGER,
    created_at DATETIME, updated_at DATETIME);
  CREATE TABLE recurring_transactions (
    id INTEGER PRIMARY KEY, account_id INTEGER, category_id INTEGER,
    type VARCHAR(8), amount DOUBLE, frequency VARCHAR(9), next_occurrence DATE,
    end_date DATE, description VARCHAR(255), notes TEXT, active BOOLEAN,
    created_at DATETIME, updated_at DATETIME);
`;

/**
 * Build a disposable fixture DB at `dbPath`. Refuses unsafe paths first.
 * Returns { dbPath, counts, expectedBalances }.
 */
export function buildFixtureDb(dbPath) {
  const target = assertSafeDbPath(dbPath);
  mkdirSync(dirname(target), { recursive: true });
  rmSync(target, { force: true });

  const db = new Database(target);
  db.exec(SCHEMA_SQL);

  db.prepare(
    'INSERT INTO profiles (id,currency,month_start_day,timezone,preferences) VALUES (?,?,?,?,?)'
  ).run(PROFILE.id, PROFILE.currency, PROFILE.month_start_day, PROFILE.timezone, PROFILE.preferences);

  const cat = db.prepare(
    'INSERT INTO categories (id,name,type,parent_id,active,description) VALUES (?,?,?,?,?,?)'
  );
  for (const c of CATEGORIES) cat.run(c.id, c.name, c.type, c.parent_id, c.active, c.description);

  const acct = db.prepare(
    'INSERT INTO accounts (id,name,type,opening_balance,current_balance,currency,active,description) VALUES (?,?,?,?,?,?,?,?)'
  );
  for (const a of ACCOUNTS) {
    acct.run(a.id, a.name, a.type, a.opening_balance, a.current_balance, a.currency, a.active, a.description);
  }

  const tx = db.prepare(
    'INSERT INTO transactions (id,account_id,category_id,type,amount,date,description,status) VALUES (?,?,?,?,?,?,?,?)'
  );
  for (const t of TRANSACTIONS) {
    tx.run(t.id, t.account_id, t.category_id, t.type, t.amount, t.date, t.description, t.status);
  }

  const tr = db.prepare(
    'INSERT INTO transfers (id,source_account_id,destination_account_id,amount,date,description,status) VALUES (?,?,?,?,?,?,?)'
  );
  for (const t of TRANSFERS) {
    tr.run(t.id, t.source_account_id, t.destination_account_id, t.amount, t.date, t.description, t.status);
  }

  db.close();

  return {
    dbPath: target,
    counts: {
      accounts: ACCOUNTS.length,
      categories: CATEGORIES.length,
      transactions: TRANSACTIONS.length,
      transfers: TRANSFERS.length,
    },
    expectedBalances: expectedBalances(),
  };
}

/* ------------------------------------------------------------------ */
/*  CLI                                                                */
/* ------------------------------------------------------------------ */
function isMain() {
  return process.argv[1] && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url));
}

if (isMain()) {
  const args = process.argv.slice(2);
  const i = args.indexOf('--out');
  const out =
    i !== -1 && args[i + 1]
      ? args[i + 1]
      : join(tmpdir(), 'pilote-budget-smoke', `fixture-${Date.now().toString(36)}.sqlite`);

  try {
    const result = buildFixtureDb(out);
    console.log(JSON.stringify(result, null, 2));
  } catch (error) {
    console.error(String(error && error.message ? error.message : error));
    process.exit(1);
  }
}
