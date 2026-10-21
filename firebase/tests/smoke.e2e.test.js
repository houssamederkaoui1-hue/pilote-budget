import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, existsSync, statSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { initializeApp } from 'firebase-admin/app';
import { getFirestore } from 'firebase-admin/firestore';
import {
  assertFails,
  assertSucceeds,
  initializeTestEnvironment,
} from '@firebase/rules-unit-testing';
import {
  REAL_DB,
  assertSafeDbPath,
  buildFixtureDb,
  expectedBalances,
} from '../tools/make-fixture-db.mjs';

/**
 * End-to-end smoke test for the Firebase preview, using ONLY fabricated data.
 *
 *   1. Generates a disposable fixture SQLite DB (tools/make-fixture-db.mjs).
 *   2. Runs the operator importer in DRY-RUN (must write nothing), then COMMIT
 *      against the emulator under a fresh test UID.
 *   3. Reads the imported Firestore documents back as the owner (through the
 *      real Security Rules) and re-derives every account balance independently.
 *   4. Verifies the derived balances against the fixture's own expectation and
 *      a hard-coded value, and exercises owner-read / anonymous-denial /
 *      cross-user-denial.
 *
 * The real database (backend/data/pilote_budget.db) is never opened: the
 * importer reads the *fixture* read-only, and this file asserts the real DB's
 * hash is unchanged before/after.
 *
 * Prerequisite: the Firestore emulator must be running on 127.0.0.1:8080
 * (see FIREBASE_SMOKE_TEST.md). The suite skips cleanly if it is not.
 */

const HERE = dirname(fileURLToPath(import.meta.url));
const TOOL = join(HERE, '..', 'tools', 'import-sqlite-to-firestore.mjs');
const RULES = readFileSync(new URL('../firestore.rules', import.meta.url), 'utf8');

const PROJECT_ID = 'demo-pilote-budget';
const EMULATOR_HOST = '127.0.0.1:8080';
const OWNER = `smoke-owner-${Date.now().toString(36)}`;
const OTHER = `smoke-other-${Date.now().toString(36)}`;

// Independently hand-computed from the fixture seed (must match the generator).
const HARDCODED_EXPECTED = { '1': 79750, '2': 77500, '3': -3000 };

process.env.FIRESTORE_EMULATOR_HOST = EMULATOR_HOST;

const hashFile = (path) => {
  if (!existsSync(path)) return null;
  return createHash('sha256').update(readFileSync(path)).digest('hex');
};

function runTool(uid, extraArgs = []) {
  return execFileSync(process.execPath, [TOOL, '--db', fixture, '--uid', uid, ...extraArgs], {
    env: {
      ...process.env,
      FIRESTORE_EMULATOR_HOST: EMULATOR_HOST,
      GOOGLE_CLOUD_PROJECT: PROJECT_ID,
    },
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
}

/** Independent re-derivation from Firestore documents (camelCase integer cents). */
function deriveFromDocs(accounts, transactions, transfers) {
  const balances = new Map(accounts.map((a) => [a.id, a.openingBalanceCents]));
  for (const tx of transactions) {
    if (!['pending', 'cleared', 'reconciled'].includes(tx.status)) continue;
    const delta = tx.type === 'income' ? tx.amountCents : -tx.amountCents;
    balances.set(tx.accountId, (balances.get(tx.accountId) ?? 0) + delta);
  }
  for (const tr of transfers) {
    if (!['pending', 'completed'].includes(tr.status)) continue;
    balances.set(tr.sourceAccountId, (balances.get(tr.sourceAccountId) ?? 0) - tr.amountCents);
    balances.set(tr.destinationAccountId, (balances.get(tr.destinationAccountId) ?? 0) + tr.amountCents);
  }
  return Object.fromEntries(balances);
}

let dir;
let fixture;
let admin;
let env;
let emulatorUp = false;
let realDbHashBefore = null;
let realDbExistsBefore = false;
let fixtureHashBefore = null;
let fixtureHashAfter = null;
let countAfterDryRun = null;
let dryRunOut = '';

async function pingEmulator() {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 1500);
    const res = await fetch(`http://${EMULATOR_HOST}/`, { signal: controller.signal });
    clearTimeout(timer);
    return res.ok || res.status === 200;
  } catch {
    return false;
  }
}

before(async () => {
  realDbExistsBefore = existsSync(REAL_DB);
  realDbHashBefore = hashFile(REAL_DB);

  emulatorUp = await pingEmulator();
  if (!emulatorUp) return;

  const app = initializeApp({ projectId: PROJECT_ID }, 'smoke-admin');
  admin = getFirestore(app);

  dir = mkdtempSync(join(tmpdir(), 'pilote-smoke-'));
  fixture = join(dir, 'fixture.sqlite');
  buildFixtureDb(fixture);
  fixtureHashBefore = hashFile(fixture);
  const mtimeBefore = statSync(fixture).mtimeMs;

  // DRY-RUN must not write anything.
  dryRunOut = runTool(OWNER);
  countAfterDryRun = (await admin.collection(`users/${OWNER}/accounts`).get()).size;
  assert.equal(statSync(fixture).mtimeMs, mtimeBefore, 'dry-run touched the fixture DB');

  // COMMIT against the emulator.
  runTool(OWNER, ['--yes']);
  fixtureHashAfter = hashFile(fixture);

  env = await initializeTestEnvironment({
    projectId: PROJECT_ID,
    firestore: { host: '127.0.0.1', port: 8080, rules: RULES },
  });
});

after(async () => {
  if (env) await env.cleanup();
  if (dir) rmSync(dir, { recursive: true, force: true });

  // Hard guarantee: the real ledger was neither created nor modified.
  assert.equal(existsSync(REAL_DB), realDbExistsBefore, 'real DB existence changed');
  assert.equal(hashFile(REAL_DB), realDbHashBefore, 'real DB contents changed');
});

test('fixture generator refuses the real backend database path', () => {
  assert.throws(() => assertSafeDbPath(REAL_DB), /Refusing/);
  assert.throws(() => assertSafeDbPath(join(HERE, '..', '..', 'backend', 'data', 'anything.sqlite')), /Refusing/);
});

test('fixture expectation is stable and matches hard-coded values', () => {
  assert.deepEqual(expectedBalances(), HARDCODED_EXPECTED);
});

test('importer DRY-RUN writes nothing for the test UID', (t) => {
  if (!emulatorUp) return t.skip('Firestore emulator not running on 127.0.0.1:8080');
  assert.match(dryRunOut, /DRY-RUN/);
  assert.equal(countAfterDryRun, 0);
});

test('importer opens the fixture read-only (fixture hash unchanged)', (t) => {
  if (!emulatorUp) return t.skip('Firestore emulator not running on 127.0.0.1:8080');
  assert.ok(fixtureHashBefore);
  assert.equal(fixtureHashAfter, fixtureHashBefore, 'importer modified the fixture DB');
});

test('importer COMMIT writes the expected document counts under the UID', async (t) => {
  if (!emulatorUp) return t.skip('Firestore emulator not running on 127.0.0.1:8080');
  const count = async (c) => (await admin.collection(`users/${OWNER}/${c}`).get()).size;
  assert.equal(await count('accounts'), 3);
  assert.equal(await count('categories'), 3);
  assert.equal(await count('transactions'), 7);
  assert.equal(await count('transfers'), 4);
  assert.equal(await count('profile'), 1);
});

test('derived balances from Firestore match the fixture expectation', async (t) => {
  if (!emulatorUp) return t.skip('Firestore emulator not running on 127.0.0.1:8080');
  const owner = env.authenticatedContext(OWNER).firestore();
  const grab = async (c) =>
    (await owner.collection(`users/${OWNER}/${c}`).get()).docs.map((d) => ({
      id: d.id,
      ...d.data(),
    }));
  const accounts = await grab('accounts');
  const transactions = await grab('transactions');
  const transfers = await grab('transfers');

  const derived = deriveFromDocs(accounts, transactions, transfers);
  assert.deepEqual(derived, expectedBalances());
  assert.deepEqual(derived, HARDCODED_EXPECTED);

  // Imported snapshots are deliberately stale, proving derivation is authoritative.
  const imported = Object.fromEntries(accounts.map((a) => [a.id, a.currentBalanceCents]));
  assert.notDeepEqual(imported, derived);
});

test('owner can read and list accounts, transactions and transfers', async (t) => {
  if (!emulatorUp) return t.skip('Firestore emulator not running on 127.0.0.1:8080');
  const owner = env.authenticatedContext(OWNER).firestore();
  for (const c of ['accounts', 'transactions', 'transfers']) {
    await assertSucceeds(owner.collection(`users/${OWNER}/${c}`).get());
  }
});

test('anonymous reads over the ledger are denied', async (t) => {
  if (!emulatorUp) return t.skip('Firestore emulator not running on 127.0.0.1:8080');
  const anon = env.unauthenticatedContext().firestore();
  for (const c of ['accounts', 'transactions', 'transfers']) {
    await assertFails(anon.collection(`users/${OWNER}/${c}`).get());
    await assertFails(anon.doc(`users/${OWNER}/${c}/1`).get());
  }
});

test('cross-user reads over the ledger are denied', async (t) => {
  if (!emulatorUp) return t.skip('Firestore emulator not running on 127.0.0.1:8080');
  const other = env.authenticatedContext(OTHER).firestore();
  for (const c of ['accounts', 'transactions', 'transfers']) {
    await assertFails(other.collection(`users/${OWNER}/${c}`).get());
    await assertFails(other.doc(`users/${OWNER}/${c}/1`).get());
  }
});
