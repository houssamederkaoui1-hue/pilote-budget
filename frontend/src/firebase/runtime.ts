/**
 * Lazy Firebase runtime creation.
 *
 * Every `firebase/*` submodule is loaded via dynamic import so the legacy
 * FastAPI bundle does not pay for the SDK. The `/firebase/*` route is the only
 * entry point (react-router lazy route), which keeps the SDK out of the main
 * chunk entirely.
 */

import {
  firebaseEnabled,
  firebaseEmulatorsEnabled,
  FIREBASE_AUTH_EMULATOR_URL,
  FIREBASE_FIRESTORE_EMULATOR,
  PUBLIC_FIREBASE_CONFIG,
} from "./config";
import type { FirebaseApp } from "firebase/app";
import type { Auth } from "firebase/auth";
import type { Firestore } from "firebase/firestore";

export interface FirebaseRuntime {
  app: FirebaseApp;
  auth: Auth;
  db: Firestore;
}

let pending: Promise<FirebaseRuntime> | null = null;

export function getRuntime(): Promise<FirebaseRuntime> {
  if (!firebaseEnabled) {
    return Promise.reject(
      new Error("Firebase is not configured (set VITE_FIREBASE_* see .env.example)."),
    );
  }
  if (pending) return pending;

  pending = (async () => {
    const { initializeApp } = await import("firebase/app");
    const {
      getAuth,
      setPersistence,
      browserLocalPersistence,
      connectAuthEmulator,
    } = await import("firebase/auth");
    const {
      getFirestore,
      initializeFirestore,
      persistentLocalCache,
      connectFirestoreEmulator,
    } = await import("firebase/firestore");

    const app = initializeApp(PUBLIC_FIREBASE_CONFIG);
    const auth = getAuth(app);
    // LOCAL-ONLY: redirect Auth to the emulator before any auth call. Guarded by
    // an explicit opt-in flag so a normal/production build never does this.
    if (firebaseEmulatorsEnabled) {
      connectAuthEmulator(auth, FIREBASE_AUTH_EMULATOR_URL, { disableWarnings: true });
    }
    try {
      // Persist the email/password session across reloads.
      await setPersistence(auth, browserLocalPersistence);
    } catch {
      // Non-fatal: session defaults to in-memory if persistence is unavailable.
    }
    // Offline persistence backs the read-only views with the SDK's local cache.
    // If the browser cannot host IndexedDB (private mode, blocked storage) this
    // steps down to an in-memory Firestore so the signed-in views still work
    // online instead of failing to start.
    let db: Firestore;
    try {
      db = initializeFirestore(app, { localCache: persistentLocalCache() });
    } catch {
      db = getFirestore(app);
    }
    // LOCAL-ONLY: redirect Firestore to the emulator before any read. Same
    // explicit flag as above; the emulator never sees real data.
    if (firebaseEmulatorsEnabled) {
      connectFirestoreEmulator(db, FIREBASE_FIRESTORE_EMULATOR.host, FIREBASE_FIRESTORE_EMULATOR.port);
    }

    return { app, auth, db };
  })().catch((error: unknown) => {
    pending = null;
    throw error;
  });

  return pending;
}