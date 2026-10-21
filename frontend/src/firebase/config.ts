/**
 * PUBLIC Firebase web configuration (client credentials only).
 *
 * These values come from the Firebase Console "Add web app" flow and are
 * deliberately safe to embed in the bundle. They are NOT a service-account
 * key: Firestore access is still gated by Security Rules on `request.auth.uid`.
 *
 * Source of truth for the variable names is `frontend/.env.example`.
 */

export interface PublicFirebaseConfig {
  apiKey: string;
  authDomain: string;
  projectId: string;
  storageBucket: string;
  messagingSenderId: string;
  appId: string;
}

function pick(name: string): string {
  const value = import.meta.env[name] as string | undefined;
  return typeof value === "string" ? value.trim() : "";
}

export const PUBLIC_FIREBASE_CONFIG: PublicFirebaseConfig = {
  apiKey: pick("VITE_FIREBASE_API_KEY"),
  authDomain: pick("VITE_FIREBASE_AUTH_DOMAIN"),
  projectId: pick("VITE_FIREBASE_PROJECT_ID"),
  storageBucket: pick("VITE_FIREBASE_STORAGE_BUCKET"),
  messagingSenderId: pick("VITE_FIREBASE_MESSAGING_SENDER_ID"),
  appId: pick("VITE_FIREBASE_APP_ID"),
};

/**
 * The Firebase path is only enabled when the three identity-critical values
 * are present. Without them the whole `/firebase/*` area renders a clear
 * "not configured" screen and the legacy FastAPI app keeps working untouched.
 */
export const firebaseEnabled: boolean =
  Boolean(PUBLIC_FIREBASE_CONFIG.apiKey) &&
  Boolean(PUBLIC_FIREBASE_CONFIG.authDomain) &&
  Boolean(PUBLIC_FIREBASE_CONFIG.projectId);

function flag(name: string): boolean {
  const value = import.meta.env[name] as string | undefined;
  if (typeof value !== "string") return false;
  const normalized = value.trim().toLowerCase();
  return normalized === "1" || normalized === "true" || normalized === "yes";
}

/**
 * LOCAL-ONLY emulator switch. Defaults to OFF and is only turned on when the
 * developer explicitly sets `VITE_FIREBASE_USE_EMULATORS=true` in an untracked
 * `.env.local` (see `.env.example`). A normal/production build therefore never
 * talks to the emulator unless this flag is deliberately set, and it only takes
 * effect when the Firebase path is otherwise configured.
 */
export const firebaseEmulatorsEnabled: boolean = flag("VITE_FIREBASE_USE_EMULATORS");

/** Emulator host shared by Auth + Firestore (override for non-local setups). */
const EMULATOR_HOST = pick("VITE_FIREBASE_EMULATOR_HOST") || "127.0.0.1";

/** `connectAuthEmulator` target (standard Auth emulator port). */
export const FIREBASE_AUTH_EMULATOR_URL = `http://${EMULATOR_HOST}:9099`;

/** `connectFirestoreEmulator` target (matches firebase.json). */
export const FIREBASE_FIRESTORE_EMULATOR = { host: EMULATOR_HOST, port: 8080 };