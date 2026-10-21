#!/usr/bin/env node
/**
 * import-sqlite-to-firestore.mjs
 *
 * OPERATOR-RUN migration tool: copies the Pilote Budget SQLite ledger into a
 * per-user Firestore namespace (`users/{uid}/...`). It is deliberately safe:
 *
 *   - Never runs automatically. Defaults to DRY-RUN and requires `--yes` to
 *     write anything.
 *   - Never reads credentials from arguments. Against a real Firebase project
 *     it requires `GOOGLE_APPLICATION_CREDENTIALS` (or `FIREBASE_IMPORT_SA`)
 *     to point at a SERVICE ACCOUNT JSON — supplied via the environment at run
 *     time and git-ignored. Against the emulator it needs
 *     `FIRESTORE_EMULATOR_HOST`, with no credentials.
 *   - Stores every monetary value as integer cents and marks ledger rows
 *     `imported: true` (the Firestore rules then make them immutable).
 *   - Validates FK integrity and ledger totals BEFORE writing, printing a
 *     report in dry-run and aborting on hard errors in commit mode.
 *
 * Usage:
 *   node tools/import-sqlite-to-firestore.mjs --db <sqlite> --uid <auth-uid> [--yes]
 *
 * Environment:
 *   FIRESTORE_EMULATOR_HOST=host:port   -> emulator target (no credentials)
 *   GOOGLE_APPLICATION_CREDENTIALS=path -> production target (service account)
 *   FIREBASE_IMPORT_SA=path             -> alternative production credential
 */

import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import Database from 'better-sqlite3';
import { initializeApp, applicationDefault, cert } from 'firebase-admin/app';
import { getFirestore } from 'firebase-admin/firestore';

const SCHEMA_VERSION = 1;

// ---------------------------------------------------------------------------
// CLI parsing
// ---------------------------------------------------------------------------
const args = process.argv.slice(2);
function flag(name) {
  const i = args.indexOf(`--${name}`);
  return i !== -1 ? args[i + 1] : undefined;
}
const has = (name) => args.includes(`--${name}`);

const DB_PATH = flag('db');
const UID = flag('uid');
const CONFIRM = has('yes');
const PROJECT_ID = process.env.GOOGLE_CLOUD_PROJECT || process.env.GCLOUD_PROJECT;

if (!DB_PATH || !UID) {
  console.error(
    'Usage: node tools/import-sqlite-to-firestore.mjs --db <sqlite> ' +
      '--uid <firebase-auth-uid> [--yes]\n' +
      'Default is DRY-RUN. Pass --yes only after reviewing the report.\n'
  );
  process.exit(2);
}

const EMULATOR_HOST = process.env.FIRESTORE_EMULATOR_HOST || null;
const SA_CERT_PATH = process.env.FIREBASE_IMPORT_SA || process.env.GOOGLE_APPLICATION_CREDENTIALS || null;

if (!EMULATOR_HOST && !SA_CERT_PATH) {
  console.error(
    'Refusing to import without a target:\n' +
      '  - emulator: set FIRESTORE_EMULATOR_HOST (host:port), or\n' +
      '  - production: set GOOGLE_APPLICATION_CREDENTIALS (or FIREBASE_IMPORT_SA)\n' +
      '    to the path of a service-account JSON. Credentials are never passed by argument.'
  );
  process.exit(2);
}

// ---------------------------------------------------------------------------
// SQLite extraction
// ---------------------------------------------------------------------------
const db = new Database(DB_PATH, { readonly: true });
db.pragma('query_only = true');

const catalog = {
  profiles: { table: 'profiles' },
  categories: { table: 'categories' },
  accounts: { table: 'accounts' },
  budget_allocations: { table: 'budget_allocations' },
  goals: { table: 'goals' },
  debts: { table: 'debts' },
  budgets: { table: 'budgets' },
  transactions: { table: 'transactions' },
  transfers: { table: 'transfers' },
  recurring_transactions: { table: 'recurring_transactions' },
};

function allRows(table) {
  return db.prepare(`SELECT * FROM ${table}`).all();
}

const toCents = (v) => Math.round((Number(v) || 0) * 100);
const toBool = (v) => Boolean(v);
const opt = (v) => (v === null || v === undefined ? undefined : v);

// ---------------------------------------------------------------------------
// Row -> Firestore document mapping (real SQLite schema, cents + camelCase)
// ---------------------------------------------------------------------------
function mapProfile(row) {
  return {
    currency: row.currency,
    monthStartDay: row.month_start_day,
    timezone: row.timezone,
    preferences: safeJson(row.preferences),
  };
}

function mapCategory(row) {
  const doc = {
    name: row.name,
    type: row.type,
    active: toBool(row.active),
  };
  if (row.parent_id != null) doc.parentId = String(row.parent_id);
  if (opt(row.description)) doc.description = row.description;
  return doc;
}

function mapAccount(row) {
  return {
    name: row.name,
    type: row.type,
    openingBalanceCents: toCents(row.opening_balance),
    currentBalanceCents: toCents(row.current_balance),
    currency: row.currency,
    active: toBool(row.active),
    ...(opt(row.description) && { description: row.description }),
  };
}

function mapAllocation(row) {
  return {
    monthId: monthId(row.month),
    incomeCents: toCents(row.income_amount),
    needsCents: toCents(row.needs_amount),
    wantsCents: toCents(row.wants_amount),
    savingsCents: toCents(row.savings_amount),
    otherCents: toCents(row.other_amount),
  };
}

function mapBudget(row) {
  const doc = {
    monthId: monthId(row.month),
    categoryId: String(row.category_id),
    plannedAmountCents: toCents(row.planned_amount),
  };
  if (opt(row.notes)) doc.notes = row.notes;
  return doc;
}

function mapGoal(row) {
  const doc = {
    name: row.name,
    targetAmountCents: toCents(row.target_amount),
    currentAmountCents: toCents(row.current_amount),
    accountId: String(row.account_id),
    active: toBool(row.active),
  };
  if (opt(row.target_date)) doc.targetDate = row.target_date;
  if (opt(row.notes)) doc.notes = row.notes;
  return doc;
}

function mapDebt(row) {
  const doc = {
    name: row.name,
    originalAmountCents: toCents(row.original_amount),
    remainingAmountCents: toCents(row.remaining_amount),
    accountId: String(row.account_id),
    active: toBool(row.active),
  };
  if (opt(row.creditor)) doc.creditor = row.creditor;
  if (row.interest_rate != null) doc.interestRateBps = toBps(row.interest_rate);
  if (row.minimum_payment != null) doc.minimumPaymentCents = toCents(row.minimum_payment);
  if (opt(row.due_date)) doc.dueDate = row.due_date;
  if (opt(row.notes)) doc.notes = row.notes;
  return doc;
}

function mapTransaction(row) {
  const doc = {
    accountId: String(row.account_id),
    type: row.type,
    amountCents: toCents(row.amount),
    date: row.date,
    description: row.description || '',
    status: row.status,
    imported: true,
  };
  if (row.category_id != null) doc.categoryId = String(row.category_id);
  if (opt(row.notes)) doc.notes = row.notes;
  if (opt(row.import_batch_id)) doc.importBatchId = row.import_batch_id;
  if (opt(row.external_id)) doc.externalId = row.external_id;
  if (opt(row.import_metadata)) doc.importMetadata = String(row.import_metadata);
  if (opt(row.dedupe_key)) doc.dedupeKey = row.dedupe_key;
  return doc;
}

function mapTransfer(row) {
  const doc = {
    sourceAccountId: String(row.source_account_id),
    destinationAccountId: String(row.destination_account_id),
    amountCents: toCents(row.amount),
    date: row.date,
    description: row.description || '',
    status: row.status,
    imported: true,
  };
  if (opt(row.notes)) doc.notes = row.notes;
  return doc;
}

function mapRecurring(row) {
  const doc = {
    accountId: String(row.account_id),
    type: row.type,
    amountCents: toCents(row.amount),
    frequency: row.frequency,
    nextOccurrence: row.next_occurrence,
    description: row.description || '',
    active: toBool(row.active),
  };
  if (row.category_id != null) doc.categoryId = String(row.category_id);
  if (opt(row.end_date)) doc.endDate = row.end_date;
  if (opt(row.notes)) doc.notes = row.notes;
  return doc;
}

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------
function safeJson(raw) {
  if (raw == null) return {};
  if (typeof raw === 'string') {
    try {
      return JSON.parse(raw);
    } catch {
      return { raw };
    }
  }
  return raw;
}

const monthId = (d) => String(d).slice(0, 7);
const toBps = (v) => Math.round((Number(v) || 0) * 100);

function docIdFor(table, row) {
  switch (table) {
    case 'profiles':
      return 'me';
    case 'budget_allocations':
      return monthId(row.month);
    case 'budgets':
      return `${monthId(row.month)}-c${row.category_id}`;
    default:
      return String(row.id);
  }
}

const COLLECTION = {
  profiles: 'profile',
  categories: 'categories',
  accounts: 'accounts',
  budget_allocations: 'allocations',
  goals: 'goals',
  debts: 'debts',
  budgets: 'budgets',
  transactions: 'transactions',
  transfers: 'transfers',
  recurring_transactions: 'recurring',
};

const MAPPER = {
  profiles: mapProfile,
  categories: mapCategory,
  accounts: mapAccount,
  budget_allocations: mapAllocation,
  goals: mapGoal,
  debts: mapDebt,
  budgets: mapBudget,
  transactions: mapTransaction,
  transfers: mapTransfer,
  recurring_transactions: mapRecurring,
};

// ---------------------------------------------------------------------------
// Extraction + validation
// ---------------------------------------------------------------------------
const extracted = {};
for (const [key, { table }] of Object.entries(catalog)) {
  extracted[key] = allRows(table);
}

const accountIds = new Set(extracted.accounts.map((r) => String(r.id)));
const categoryIds = new Set(extracted.categories.map((r) => String(r.id)));

const errors = [];
const warnings = [];

function check(cond, message, where) {
  if (!cond) errors.push(`${where}: ${message}`);
}

// Parent/child ordering follows domain/backup.py TABLE_ONLY for sanity; FK
// integrity is verified below regardless of order in the DB file.
for (const tx of extracted.transactions) {
  check(accountIds.has(String(tx.account_id)), `account_id ${tx.account_id} missing`, `transaction ${tx.id}`);
  if (tx.category_id != null) {
    check(categoryIds.has(String(tx.category_id)), `category_id ${tx.category_id} missing`, `transaction ${tx.id}`);
  }
}
for (const tr of extracted.transfers) {
  check(accountIds.has(String(tr.source_account_id)), `source_account_id ${tr.source_account_id} missing`, `transfer ${tr.id}`);
  check(accountIds.has(String(tr.destination_account_id)), `destination_account_id ${tr.destination_account_id} missing`, `transfer ${tr.id}`);
  check(tr.source_account_id !== tr.destination_account_id, 'source == destination', `transfer ${tr.id}`);
  check(tr.amount > 0, 'amount must be > 0', `transfer ${tr.id}`);
}
for (const g of extracted.goals) {
  check(accountIds.has(String(g.account_id)), `account_id ${g.account_id} missing`, `goal ${g.id}`);
}
for (const d of extracted.debts) {
  check(accountIds.has(String(d.account_id)), `account_id ${d.account_id} missing`, `debt ${d.id}`);
}
for (const r of extracted.recurring_transactions) {
  check(accountIds.has(String(r.account_id)), `account_id ${r.account_id} missing`, `recurring ${r.id}`);
  if (r.category_id != null) {
    check(categoryIds.has(String(r.category_id)), `category_id ${r.category_id} missing`, `recurring ${r.id}`);
  }
}
for (const b of extracted.budgets) {
  check(categoryIds.has(String(b.category_id)), `category_id ${b.category_id} missing`, `budget ${b.id}`);
}

// Ledger integrity: re-derive each account balance from the ledger (same rule
// as BalanceService) and compare with the cached current_balance column.
const derived = new Map(extracted.accounts.map((a) => [String(a.id), toCents(a.opening_balance)]));
for (const tx of extracted.transactions) {
  const amount = toCents(tx.amount);
  const key = String(tx.account_id);
  if (!['pending', 'cleared', 'reconciled'].includes(tx.status)) continue;
  derived.set(key, derived.get(key) + (tx.type === 'income' ? amount : -amount));
}
for (const tr of extracted.transfers) {
  const amount = toCents(tr.amount);
  if (!['pending', 'completed'].includes(tr.status)) continue;
  derived.set(String(tr.source_account_id), derived.get(String(tr.source_account_id)) - amount);
  derived.set(String(tr.destination_account_id), derived.get(String(tr.destination_account_id)) + amount);
}
for (const a of extracted.accounts) {
  const cached = toCents(a.current_balance);
  if (derived.get(String(a.id)) !== cached) {
    warnings.push(
      `account ${a.id} "${a.name}": stored current_balance(${cached}) != derived(${derived.get(String(a.id))}); derived value is authoritative`
    );
  }
}

if (errors.length > 0) {
  console.error('Validation failed; aborting. Fix the source SQLite first.\n');
  for (const e of errors) console.error('  - ' + e);
  process.exit(1);
}

// ---------------------------------------------------------------------------
// Plan report
// ---------------------------------------------------------------------------
const plan = {};
for (const [key, rows] of Object.entries(extracted)) {
  const centsTotal = {};
  for (const row of rows) {
    const doc = MAPPER[key](row);
    for (const [field, value] of Object.entries(doc)) {
      if (typeof value === 'number' && Number.isInteger(value)) {
        centsTotal[field] = (centsTotal[field] || 0) + value;
      }
    }
  }
  plan[key] = { count: rows.length, centsTotal };
}

const fingerprint = createHash('sha256')
  .update(JSON.stringify({ schemaVersion: SCHEMA_VERSION, uid: UID, plan }))
  .digest('hex');

console.log('Pilote Budget — SQLite -> Firestore import');
console.log('  uid     :', UID);
console.log('  target  :', EMULATOR_HOST ? `emulator ${EMULATOR_HOST}` : 'production Firestore');
console.log('  mode    :', CONFIRM ? 'COMMIT (--yes)' : 'DRY-RUN');
console.log('  db      :', DB_PATH);
console.log('  fingerprint:', fingerprint.slice(0, 16) + '…');
console.log();
console.log('Counts and integer-cent field sums:');
for (const [key, p] of Object.entries(plan)) {
  const sums = Object.entries(p.centsTotal)
    .filter(([k]) => /Cents$/.test(k) || k === 'interestRateBps')
    .map(([k, v]) => `${k}=${v}`)
    .join(' ');
  console.log(
    String(key).padEnd(24),
    String(p.count).padStart(5),
    sums ? ' [' + sums + ']' : ''
  );
}
if (warnings.length > 0) {
  console.log('\nWarnings:');
  for (const w of warnings) console.log('  ! ' + w);
}
console.log();

if (!CONFIRM) {
  console.log('DRY-RUN: nothing was written. Re-run with --yes to commit.');
  process.exit(0);
}

// ---------------------------------------------------------------------------
// Commit to Firestore
// ---------------------------------------------------------------------------
let app;
if (EMULATOR_HOST) {
  app = initializeApp({ projectId: PROJECT_ID || 'demo-pilote-budget' });
} else {
  if (SA_CERT_PATH) {
    let serviceAccount;
    try {
      serviceAccount = JSON.parse(readFileSync(SA_CERT_PATH, 'utf8'));
    } catch (e) {
      console.error(`Cannot read service account JSON (${SA_CERT_PATH}):`, e.message);
      process.exit(1);
    }
    app = initializeApp({ credential: cert(serviceAccount), projectId: PROJECT_ID || serviceAccount.project_id });
  } else {
    app = initializeApp({ credential: applicationDefault(), projectId: PROJECT_ID || undefined });
  }
}

const firestore = getFirestore(app);
const batchSize = 450;
let written = 0;

// Order documents parents-before-children; process each table's rows in
// stable id order.
let chunks = [];
for (const key of Object.keys(plan)) {
  const collection = COLLECTION[key];
  const rows = [...extracted[key]].sort((a, b) => Number(a.id) - Number(b.id));
  for (const row of rows) {
    chunks.push([collection, docIdFor(key, row), MAPPER[key](row)]);
    if (chunks.length >= batchSize) {
      await flush();
    }
  }
}
if (chunks.length > 0) await flush();
chunks = [];

async function flush() {
  const batch = firestore.batch();
  for (const [collection, id, data] of chunks) {
    batch.set(firestore.doc(`users/${UID}/${collection}/${id}`), data, { merge: true });
  }
  try {
    await batch.commit();
  } catch (e) {
    console.error('Batch commit failed; import aborted mid-run. Re-run with --yes to continue (idempotent).');
    throw e;
  }
  written += chunks.length;
  chunks = [];
}

await firestore
  .doc(`users/${UID}/imports/${Date.now().toString(36)}`)
  .set({
    fingerprint,
    createdAt: new Date().toISOString(),
    importedCount: written,
  });

console.log(`Import committed: ${written} documents under users/${UID}/`);
console.log(`Fingerprint document written to users/${UID}/imports/*`);
console.log('Next steps: see FIREBASE_DEPLOYMENT.md (manual Authentication + Console steps).');
await app.delete();
process.exit(0);