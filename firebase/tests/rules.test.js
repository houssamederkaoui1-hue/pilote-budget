import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  assertFails,
  assertSucceeds,
  initializeTestEnvironment,
} from '@firebase/rules-unit-testing';

const RULES = readFileSync(new URL('../firestore.rules', import.meta.url), 'utf8');

const PROJECT_ID = 'demo-pilote-budget';
const ALICE = 'alice-uid';
const BOB = 'bob-uid';

// The emulator keeps data between invocations, so document ids must be unique
// per run to keep create/update behaviour deterministic.
let seq = 0;
const fresh = () => `${Date.now().toString(36)}-${++seq}`;

let env;

// Seed helpers ---------------------------------------------------------
const validTx = (over = {}) => ({
  type: 'expense',
  status: 'cleared',
  amountCents: 1234,
  date: '2026-01-15',
  accountId: 'acct-1',
  categoryId: 'cat-1',
  description: 'Coffee',
  imported: false,
  ...over,
});

const validTransfer = (over = {}) => ({
  sourceAccountId: 'acct-1',
  destinationAccountId: 'acct-2',
  amountCents: 5000,
  date: '2026-01-16',
  status: 'completed',
  description: 'Move to savings',
  ...over,
});

const ALICE_TX = fresh();

before(async () => {
  env = await initializeTestEnvironment({
    projectId: PROJECT_ID,
    firestore: { host: '127.0.0.1', port: 8080, rules: RULES },
  });
});

after(async () => {
  await env.cleanup();
});

test('unauthenticated reads are denied', async () => {
  const anon = env.unauthenticatedContext();
  await assertFails(
    anon.firestore().doc(`users/${ALICE}/transactions/${fresh()}`).get()
  );
});

test('unauthenticated writes are denied', async () => {
  const anon = env.unauthenticatedContext();
  await assertFails(
    anon.firestore().doc(`users/${ALICE}/transactions/${fresh()}`).set(validTx())
  );
});

test('authenticated owner can create and read their own transaction', async () => {
  const alice = env.authenticatedContext(ALICE);
  await assertSucceeds(
    alice.firestore().doc(`users/${ALICE}/transactions/${ALICE_TX}`).set(validTx())
  );
  await assertSucceeds(
    alice.firestore().doc(`users/${ALICE}/transactions/${ALICE_TX}`).get()
  );
});

test('a different authenticated user cannot read or write the owner path', async () => {
  const bob = env.authenticatedContext(BOB);
  await assertFails(
    bob.firestore().doc(`users/${ALICE}/transactions/${ALICE_TX}`).get()
  );
  await assertFails(
    bob.firestore().doc(`users/${ALICE}/transactions/${fresh()}`).set(validTx())
  );
});

test('money must be stored as integer cents (floats denied)', async () => {
  const alice = env.authenticatedContext(ALICE);
  await assertFails(
    alice
      .firestore()
      .doc(`users/${ALICE}/transactions/${fresh()}`)
      .set(validTx({ amountCents: 12.5 }))
  );
  await assertFails(
    alice
      .firestore()
      .doc(`users/${ALICE}/transactions/${fresh()}`)
      .set(validTx({ amountCents: '1234' }))
  );
  await assertSucceeds(
    alice
      .firestore()
      .doc(`users/${ALICE}/transactions/${fresh()}`)
      .set(validTx({ amountCents: 1234 }))
  );
});

test('transaction shape is enforced (unknown/mis-typed fields denied)', async () => {
  const alice = env.authenticatedContext(ALICE);
  await assertFails(
    alice
      .firestore()
      .doc(`users/${ALICE}/transactions/${fresh()}`)
      .set(validTx({ accountId: 7 }))
  );
  await assertFails(
    alice
      .firestore()
      .doc(`users/${ALICE}/transactions/${fresh()}`)
      .set(validTx({ hackerField: true }))
  );
  await assertFails(
    alice
      .firestore()
      .doc(`users/${ALICE}/transactions/${fresh()}`)
      .set(validTx({ status: 'bogus' }))
  );
});

test('transfers require positive integer-cent amount and both ends', async () => {
  const alice = env.authenticatedContext(ALICE);
  await assertSucceeds(
    alice.firestore().doc(`users/${ALICE}/transfers/${fresh()}`).set(validTransfer())
  );
  await assertFails(
    alice
      .firestore()
      .doc(`users/${ALICE}/transfers/${fresh()}`)
      .set(validTransfer({ amountCents: 0 }))
  );
  await assertFails(
    alice
      .firestore()
      .doc(`users/${ALICE}/transfers/${fresh()}`)
      .set(validTransfer({ amountCents: -1 }))
  );
  await assertFails(
    alice
      .firestore()
      .doc(`users/${ALICE}/transfers/${fresh()}`)
      .set(validTransfer({ sourceAccountId: 0 }))
  );
});

test('profile document id must be "me"', async () => {
  const alice = env.authenticatedContext(ALICE);
  const profile = { currency: 'MAD', monthStartDay: 1, timezone: 'UTC', preferences: {} };
  await assertSucceeds(
    alice
      .firestore()
      .doc(`users/${ALICE}/profile/me`)
      .set(profile)
  );
  await assertFails(
    alice
      .firestore()
      .doc(`users/${ALICE}/profile/wrong-id`)
      .set(profile)
  );
});

test('import bookkeeping documents are append-only (delete denied)', async () => {
  const alice = env.authenticatedContext(ALICE);
  const ref = alice.firestore().doc(`users/${ALICE}/imports/${fresh()}`);
  const run = { fingerprint: 'sha256:abc', createdAt: '2026-01-01T00:00:00Z', importedCount: 0 };
  await assertSucceeds(ref.set(run));
  await assertFails(ref.delete());
  await assertFails(ref.set({ fingerprint: 'x', createdAt: 'x', importedCount: 1, weird: true }));
});

test('imported ledger rows are immutable against updates', async () => {
  const alice = env.authenticatedContext(ALICE);
  const ref = alice.firestore().doc(`users/${ALICE}/transactions/${fresh()}`);
  await assertSucceeds(ref.set(validTx({ imported: true })));
  await assertSucceeds(ref.get());
  await assertFails(ref.update({ description: 'tampered' }));
});

test('imported ledger rows cannot escape immutability by flipping imported to false', async () => {
  const alice = env.authenticatedContext(ALICE);
  const ref = alice.firestore().doc(`users/${ALICE}/transactions/${fresh()}`);
  await assertSucceeds(ref.set(validTx({ imported: true })));

  // Partial update that only clears the flag.
  await assertFails(ref.update({ imported: false }));
  // Partial update that clears the flag AND edits a field.
  await assertFails(ref.update({ imported: false, description: 'tampered' }));
  // Full overwrite (set) that replaces the imported row with a non-imported one.
  await assertFails(ref.set(validTx({ imported: false })));

  const snap = await ref.get();
  assert.equal(snap.data().imported, true);
  assert.equal(snap.data().description, 'Coffee');
});

test('imported ledger rows cannot be deleted', async () => {
  const alice = env.authenticatedContext(ALICE);
  const ref = alice.firestore().doc(`users/${ALICE}/transactions/${fresh()}`);
  await assertSucceeds(ref.set(validTx({ imported: true })));
  await assertFails(ref.delete());
  const snap = await ref.get();
  assert.equal(snap.exists, true);
  assert.equal(snap.data().imported, true);
});

test('a non-imported row cannot be promoted to imported:true', async () => {
  const alice = env.authenticatedContext(ALICE);
  const ref = alice.firestore().doc(`users/${ALICE}/transactions/${fresh()}`);
  await assertSucceeds(ref.set(validTx({ imported: false })));
  await assertFails(ref.update({ imported: true }));
  // Sanity: an ordinary edit of a non-imported row is still allowed.
  await assertSucceeds(ref.update({ description: 'renamed' }));
  const snap = await ref.get();
  assert.equal(snap.data().description, 'renamed');
});

test('imported transfers cannot escape immutability by flipping imported to false', async () => {
  const alice = env.authenticatedContext(ALICE);
  const ref = alice.firestore().doc(`users/${ALICE}/transfers/${fresh()}`);
  await assertSucceeds(ref.set(validTransfer({ imported: true })));

  // Partial update that only clears the flag.
  await assertFails(ref.update({ imported: false }));
  // Partial update that clears the flag AND edits a field.
  await assertFails(ref.update({ imported: false, description: 'tampered' }));
  // Full overwrite (set) with altered fields that replaces the imported row.
  await assertFails(
    ref.set(validTransfer({ imported: false, amountCents: 999999 }))
  );

  const snap = await ref.get();
  assert.equal(snap.data().imported, true);
  assert.equal(snap.data().description, 'Move to savings');
  assert.equal(snap.data().amountCents, 5000);
});

test('imported transfers cannot be deleted', async () => {
  const alice = env.authenticatedContext(ALICE);
  const ref = alice.firestore().doc(`users/${ALICE}/transfers/${fresh()}`);
  await assertSucceeds(ref.set(validTransfer({ imported: true })));
  await assertFails(ref.delete());
  const snap = await ref.get();
  assert.equal(snap.exists, true);
  assert.equal(snap.data().imported, true);
});

test('non-imported transfers remain editable and deletable', async () => {
  const alice = env.authenticatedContext(ALICE);
  const ref = alice.firestore().doc(`users/${ALICE}/transfers/${fresh()}`);
  await assertSucceeds(ref.set(validTransfer()));
  await assertSucceeds(ref.update({ description: 'renamed', amountCents: 6000 }));
  const snap = await ref.get();
  assert.equal(snap.data().description, 'renamed');
  assert.equal(snap.data().amountCents, 6000);
  await assertSucceeds(ref.delete());
  const gone = await ref.get();
  assert.equal(gone.exists, false);
});

test('unknown collections under a uid are denied by default', async () => {
  const alice = env.authenticatedContext(ALICE);
  await assertFails(
    alice.firestore().doc(`users/${ALICE}/unknownCollection/${fresh()}`).set({ a: 1 })
  );
});

test('owner can delete their own non-imported transaction', async () => {
  const alice = env.authenticatedContext(ALICE);
  const ref = alice.firestore().doc(`users/${ALICE}/transactions/${fresh()}`);
  await assertSucceeds(ref.set(validTx()));
  await assertSucceeds(ref.delete());
});

test('no rule allows access outside /users/{uid}', async () => {
  const alice = env.authenticatedContext(ALICE);
  await assertFails(
    alice.firestore().doc(`transactions/${fresh()}`).set(validTx())
  );
  await assertFails(
    alice.firestore().doc(`users/another-uid/transactions/${fresh()}`).get()
  );
});

// A list query from an authenticated user over ANOTHER user's subcollection
// is denied outright because no document in it is readable by that user.
test('bob list query over alice documents is denied', async () => {
  const bob = env.authenticatedContext(BOB);
  const q = bob.firestore().collection(`users/${ALICE}/transactions`);
  await assertFails(q.get());
});

// ---------------------------------------------------------------------------
// Phase 1 read-path scoping: the client views read `users/{uid}/accounts`,
// `users/{uid}/categories` and `users/{uid}/transactions`. Prove that the
// owner can list and read full collections, while anonymous and cross-user
// list queries over the same read paths are denied.
// ---------------------------------------------------------------------------

const validAccount = () => ({
  name: `checking-${fresh()}`,
  type: 'checking',
  openingBalanceCents: 0,
  currentBalanceCents: 1234,
  currency: 'EUR',
  active: true,
});

const validCategory = () => ({
  name: `Groceries-${fresh()}`,
  type: 'expense',
  active: true,
});

test('owner can read and list their accounts and categories', async () => {
  const alice = env.authenticatedContext(ALICE);
  const accountId = fresh();
  const categoryId = fresh();
  await assertSucceeds(
    alice.firestore().doc(`users/${ALICE}/accounts/${accountId}`).set(validAccount())
  );
  await assertSucceeds(
    alice.firestore().doc(`users/${ALICE}/categories/${categoryId}`).set(validCategory())
  );

  await assertSucceeds(
    alice.firestore().doc(`users/${ALICE}/accounts/${accountId}`).get()
  );
  await assertSucceeds(
    alice.firestore().collection(`users/${ALICE}/accounts`).get()
  );
  await assertSucceeds(
    alice.firestore().doc(`users/${ALICE}/categories/${categoryId}`).get()
  );
  await assertSucceeds(
    alice.firestore().collection(`users/${ALICE}/categories`).get()
  );
});

test('unauthenticated list queries over the Phase 1 read paths are denied', async () => {
  const anon = env.unauthenticatedContext();
  for (const path of [
    `users/${ALICE}/accounts`,
    `users/${ALICE}/categories`,
    `users/${ALICE}/transactions`,
  ]) {
    await assertFails(anon.firestore().collection(path).get());
    await assertFails(anon.firestore().collection(path).doc(fresh()).get());
  }
});

test('cross-user list queries over the Phase 1 read paths are denied', async () => {
  const bob = env.authenticatedContext(BOB);
  for (const path of [
    `users/${ALICE}/accounts`,
    `users/${ALICE}/categories`,
    `users/${ALICE}/transactions`,
  ]) {
    await assertFails(bob.firestore().collection(path).get());
  }
});