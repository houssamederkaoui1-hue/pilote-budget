import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import Database from 'better-sqlite3';
import { initializeApp } from 'firebase-admin/app';
import { getFirestore } from 'firebase-admin/firestore';

const HERE = dirname(fileURLToPath(import.meta.url));
const TOOL = join(HERE, '..', 'tools', 'import-sqlite-to-firestore.mjs');
const EMULATOR_HOST = '127.0.0.1:8080';
const UID = `import-test-${Date.now().toString(36)}`;

// Point firebase-admin (used for read-back) at the emulator: no credentials
// needed. Must be set before the admin client is constructed.
process.env.FIRESTORE_EMULATOR_HOST = EMULATOR_HOST;

let dir;
let fixture;
let admin;

function runTool(extraArgs = []) {
  return execFileSync(process.execPath, [TOOL, '--db', fixture, '--uid', UID, ...extraArgs], {
    env: {
      ...process.env,
      FIRESTORE_EMULATOR_HOST: '127.0.0.1:8080',
      GOOGLE_CLOUD_PROJECT: 'demo-pilote-budget',
    },
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
}

function seedFixture() {
  const db = new Database(fixture);
  db.exec(`
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
  `);

  const active1 = db.prepare('INSERT INTO profiles (id,currency,month_start_day,timezone,preferences) VALUES (?,?,?,?,?)');
  active1.run(1, 'MAD', 1, 'UTC', '{}');

  const cat = db.prepare('INSERT INTO categories (id,name,type,parent_id,active,description) VALUES (?,?,?,?,?,?)');
  cat.run(10, 'Salary', 'income', null, 1, null);
  cat.run(11, 'Food', 'expense', null, 1, null);
  cat.run(12, 'Transport', 'expense', null, 1, null);

  const acct = db.prepare('INSERT INTO accounts (id,name,type,opening_balance,current_balance,currency,active,description) VALUES (?,?,?,?,?,?,?,?)');
  acct.run(1, 'Checking', 'checking', 100.0, 120.0, 'MAD', 1, null); // cached balance deliberately stale
  acct.run(2, 'Savings', 'savings', 500.0, 700.0, 'MAD', 1, null);

  const tx = db.prepare('INSERT INTO transactions (id,account_id,category_id,type,amount,date,description,status) VALUES (?,?,?,?,?,?,?,?)');
  tx.run(1, 1, 10, 'income', 1000.0, '2026-01-05', 'January salary', 'cleared');
  tx.run(2, 1, 11, 'expense', 42.5, '2026-01-06', 'Groceries', 'cleared');

  const tr = db.prepare('INSERT INTO transfers (id,source_account_id,destination_account_id,amount,date,description,status) VALUES (?,?,?,?,?,?,?)');
  tr.run(1, 1, 2, 200.0, '2026-01-07', 'To savings', 'completed');

  db.prepare('INSERT INTO budget_allocations (id,month,income_amount,needs_amount,wants_amount,savings_amount,other_amount) VALUES (1,?,?,?,?,?,?)')
    .run('2026-01-01', 1000.0, 500.0, 300.0, 100.0, 100.0);
  db.prepare('INSERT INTO budgets (id,month,category_id,planned_amount,notes) VALUES (1,?,?,?,?)')
    .run('2026-01-01', 11, 300.0, '');

  db.prepare("INSERT INTO goals (id,name,target_amount,current_amount,target_date,account_id,active) VALUES (1,?,?,?,?,?,1)")
    .run('Vacation', 5000.0, 200.0, '2026-12-31', 2);
  db.prepare('INSERT INTO debts (id,name,creditor,original_amount,remaining_amount,interest_rate,minimum_payment,due_date,account_id,active) VALUES (1,?,?,?,?,?,?,?,?,1)')
    .run('Card', 'Bank', 10000.0, 6000.0, 5.25, 200.0, '2026-11-30', 1);
  db.prepare("INSERT INTO recurring_transactions (id,account_id,category_id,type,amount,frequency,next_occurrence,description,active) VALUES (1,1,11,'expense',80.0,'monthly','2026-02-01','Internet',1)")
    .run();

  db.close();
}

const count = async (collection) => {
  const snap = await admin.collection(`users/${UID}/${collection}`).get();
  return snap.size;
};

const doc = async (collection, id) => {
  const ref = admin.doc(`users/${UID}/${collection}/${id}`);
  const snap = await ref.get();
  return snap.exists ? snap.data() : null;
};

before(async () => {
  dir = mkdtempSync(join(tmpdir(), 'pilote-import-'));
  fixture = join(dir, 'fixture.sqlite');
  seedFixture();
  const app = initializeApp({ projectId: 'demo-pilote-budget' }, 'import-test-reader');
  admin = getFirestore(app);
});

after(async () => {
  rmSync(dir, { recursive: true, force: true });
});

test('dry-run writes nothing and reports the plan', async () => {
  const out = runTool(); // no --yes
  assert.match(out, /DRY-RUN/);
  for (const expect of [
    'profiles',
    'accounts',
    'transactions',
    'transfers',
    'recurring',
    'budgets',
    'allocations',
    'goals',
    'debts',
  ]) {
    assert.match(out, new RegExp(expect));
  }
  assert.equal(await count('transactions'), 0);
  assert.equal(await count('accounts'), 0);
});

test('refuses to run without a credential target or emulator', () => {
  assert.throws(() =>
    execFileSync(process.execPath, [TOOL, '--db', fixture, '--uid', UID], {
      env: {
        ...process.env,
        FIRESTORE_EMULATOR_HOST: '',
        GOOGLE_APPLICATION_CREDENTIALS: '',
        FIREBASE_IMPORT_SA: '',
      },
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    }),
    /Refusing/
  );
});

test('commit writes mapped documents under the uid', async () => {
  const out = runTool(['--yes']);

  assert.equal(await count('accounts'), 2);
  assert.equal(await count('categories'), 3);
  assert.equal(await count('transactions'), 2);
  assert.equal(await count('transfers'), 1);
  assert.equal(await count('allocations'), 1);
  assert.equal(await count('budgets'), 1);
  assert.equal(await count('goals'), 1);
  assert.equal(await count('debts'), 1);
  assert.equal(await count('recurring'), 1);
  assert.equal(await count('profile'), 1);

  const profile = await doc('profile', 'me');
  assert.equal(profile.currency, 'MAD');
  assert.equal(profile.monthStartDay, 1);
  assert.deepEqual(profile.preferences, {});

  const acct1 = await doc('accounts', '1');
  assert.equal(acct1.openingBalanceCents, 10000);
  assert.equal(acct1.currentBalanceCents, 12000); // cached value preserved
  assert.equal(acct1.active, true);
  assert.equal(acct1.type, 'checking');

  const tx1 = await doc('transactions', '1');
  assert.equal(tx1.type, 'income');
  assert.equal(tx1.amountCents, 100000);
  assert.equal(tx1.accountId, '1');
  assert.equal(tx1.categoryId, '10');
  assert.equal(tx1.imported, true);

  const tx2 = await doc('transactions', '2');
  assert.equal(tx2.amountCents, 4250);

  const tr = await doc('transfers', '1');
  assert.equal(tr.sourceAccountId, '1');
  assert.equal(tr.destinationAccountId, '2');
  assert.equal(tr.amountCents, 20000);
  assert.equal(tr.status, 'completed');
  assert.equal(tr.imported, true);

  const alloc = await doc('allocations', '2026-01');
  assert.equal(alloc.incomeCents, 100000);
  assert.equal(alloc.needsCents, 50000);
  assert.equal(alloc.wantsCents, 30000);
  assert.equal(alloc.savingsCents, 10000);
  assert.equal(alloc.otherCents, 10000);

  const budget = await doc('budgets', '2026-01-c11');
  assert.equal(budget.monthId, '2026-01');
  assert.equal(budget.categoryId, '11');
  assert.equal(budget.plannedAmountCents, 30000);

  const goal = await doc('goals', '1');
  assert.equal(goal.targetAmountCents, 500000);
  assert.equal(goal.currentAmountCents, 20000);
  assert.equal(goal.accountId, '2');
  assert.equal(goal.active, true);

  const debt = await doc('debts', '1');
  assert.equal(debt.interestRateBps, 525);
  assert.equal(debt.remainingAmountCents, 600000);
  assert.equal(debt.minimumPaymentCents, 20000);
  assert.equal(debt.creditor, 'Bank');

  const rec = await doc('recurring', '1');
  assert.equal(rec.amountCents, 8000);
  assert.equal(rec.frequency, 'monthly');
  assert.equal(rec.nextOccurrence, '2026-02-01');
  assert.equal(rec.active, true);
});

test('stale cached balance is reported as a warning (derived is authoritative)', async () => {
  const out = runTool();
  assert.match(out, /derived value is authoritative/);
});

test('an import fingerprint document is written', async () => {
  assert.ok((await count('imports')) >= 1);
  const snap = await admin.collection(`users/${UID}/imports`).get();
  const run = snap.docs[0].data();
  assert.match(run.fingerprint, /^[0-9a-f]{64}$/);
  assert.equal(run.importedCount, 14);
});