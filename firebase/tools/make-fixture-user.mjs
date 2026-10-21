#!/usr/bin/env node
/**
 * make-fixture-user.mjs
 *
 * Creates (or reuses) a single disposable email/password user in the **local
 * Auth emulator only**, so the browser preview can sign in and read the
 * synthetic fixture data that was imported under the same UID.
 *
 * Safety:
 *   - Refuses to run unless `FIREBASE_AUTH_EMULATOR_HOST` is set. That variable
 *     is only used when talking to the Auth emulator, so this tool can never
 *     create or touch a real Firebase account.
 *   - The default project id is a `demo-*` project, which the Firebase CLI
 *     treats as purely local (no real project, no credentials).
 *
 * Usage (with the emulator running):
 *   FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099 npm run make-user
 *
 * Prints JSON: { uid, email, projectId } — pass the uid to the importer:
 *   FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 GOOGLE_CLOUD_PROJECT=demo-pilote-budget \
 *     node tools/import-sqlite-to-firestore.mjs --db "$FIX" --uid "$UID" --yes
 */

import { initializeApp } from 'firebase-admin/app';
import { getAuth } from 'firebase-admin/auth';

const host = (process.env.FIREBASE_AUTH_EMULATOR_HOST || '').trim();

if (!host) {
  console.error(
    'Refusing to run: FIREBASE_AUTH_EMULATOR_HOST is not set. This tool only ' +
      'creates users in the LOCAL Auth emulator (e.g. 127.0.0.1:9099); it must ' +
      'never be pointed at a real project.'
  );
  process.exit(1);
}

const PROJECT_ID = process.env.GOOGLE_CLOUD_PROJECT || 'demo-pilote-budget';
const EMAIL = (process.env.FIXTURE_EMAIL || 'smoke@example.invalid').trim();
const PASSWORD = process.env.FIXTURE_PASSWORD || 'smokepass123';

const app = initializeApp({ projectId: PROJECT_ID }, 'fixture-user');
const auth = getAuth(app);

let user;
try {
  user = await auth.getUserByEmail(EMAIL);
} catch {
  user = await auth.createUser({ email: EMAIL, password: PASSWORD, emailVerified: true });
}

console.log(JSON.stringify({ uid: user.uid, email: user.email, projectId: PROJECT_ID }, null, 2));
