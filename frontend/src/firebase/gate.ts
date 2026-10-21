/**
 * Pure Firebase-preview gate + navigation decisions.
 *
 * These are extracted so the auth-initialisation race is covered by unit
 * tests and the components share exactly the tested logic.
 *
 * Why this exists: on a cold load (deep link or hard refresh) the Firebase
 * runtime becomes available *before* `onAuthStateChanged` reports the restored
 * session. If the router renders during that window it sees `user === null`
 * and redirects the requested URL to `/firebase/login`, destroying the deep
 * link. The gate below keeps the router in a `loading` state until the auth
 * state is actually known, so the intended URL is always preserved.
 */

export type FirebaseGate = "not-configured" | "error" | "loading" | "ready";

export interface FirebaseGateInput {
  /** VITE_FIREBASE_* build config is present. */
  enabled: boolean;
  /** Runtime initialisation failed (bad config, blocked storage). */
  runtimeError: string | null;
  /** The Firebase app/auth/firestore runtime has been created. */
  hasRuntime: boolean;
  /** The first `onAuthStateChanged` callback has fired. */
  authResolved: boolean;
}

export function resolveFirebaseGate(input: FirebaseGateInput): FirebaseGate {
  if (!input.enabled) return "not-configured";
  if (input.runtimeError) return "error";
  if (!input.hasRuntime || !input.authResolved) return "loading";
  return "ready";
}

export const FIREBASE_HOME = "/firebase";
export const FIREBASE_LOGIN = "/firebase/login";
export const FIREBASE_DASHBOARD = "/firebase/dashboard";

/** The in-app pages that require a signed-in user. */
export const FIREBASE_AUTHENTICATED_ROUTES: readonly string[] = [
  FIREBASE_DASHBOARD,
  "/firebase/accounts",
  "/firebase/categories",
  "/firebase/transactions",
];

function normalisePath(pathname: string): string {
  if (pathname.length > 1 && pathname.endsWith("/")) {
    return pathname.replace(/\/+$/, "") || "/";
  }
  return pathname;
}

/**
 * Returns the path to redirect to, or `null` to render the requested route.
 *
 * While the gate is not `ready` it NEVER redirects, so a deep link / hard
 * refresh keeps its URL until authentication is known. Once ready it enforces:
 * unauthenticated users go to `/firebase/login`, signed-in users are bounced
 * off the login page to the dashboard, and authenticated sub-routes are kept.
 */
export function resolveFirebaseRedirect(
  pathname: string,
  gate: FirebaseGate,
  isSignedIn: boolean,
): string | null {
  if (gate !== "ready") return null;

  const path = normalisePath(pathname);

  if (path === FIREBASE_LOGIN) {
    return isSignedIn ? FIREBASE_DASHBOARD : null;
  }
  if (path === FIREBASE_HOME) {
    return isSignedIn ? FIREBASE_DASHBOARD : FIREBASE_LOGIN;
  }
  if (FIREBASE_AUTHENTICATED_ROUTES.includes(path)) {
    return isSignedIn ? null : FIREBASE_LOGIN;
  }
  // Unknown /firebase/* path.
  return FIREBASE_LOGIN;
}
