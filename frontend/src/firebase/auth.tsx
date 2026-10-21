/**
 * Firebase Auth (email/password) session provider.
 *
 * This is the ONLY auth path used by the `/firebase/*` area. The legacy
 * FastAPI bearer-token flow (`src/lib/auth.ts`) is untouched and remains the
 * auth for every other route.
 */

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  createUserWithEmailAndPassword,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signOut as firebaseSignOut,
  type User,
} from "firebase/auth";
import { firebaseEnabled } from "./config";
import { resolveFirebaseGate, type FirebaseGate } from "./gate";
import { getRuntime, type FirebaseRuntime } from "./runtime";

export interface FirebaseAuthValue {
  enabled: boolean;
  /**
   * Coarse readiness of the `/firebase/*` area. `loading` is returned until
   * the runtime exists *and* the first `onAuthStateChanged` callback has fired,
   * so the router never redirects before the session is known.
   */
  gate: FirebaseGate;
  runtimeError: string | null;
  user: User | null;
  uid: string | null;
  runtime: FirebaseRuntime | null;
  signIn(email: string, password: string): Promise<void>;
  createAccount(email: string, password: string): Promise<void>;
  signOut(): Promise<void>;
}

const FirebaseAuthContext = createContext<FirebaseAuthValue | null>(null);

export function FirebaseAuthProvider({ children }: { children: ReactNode }) {
  const [runtime, setRuntime] = useState<FirebaseRuntime | null>(null);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  // Flips to true only once auth has actually reported the (restored) session.
  // It is deliberately never set before `onAuthStateChanged` fires, which is
  // what stops a deep link / refresh from being redirected while auth is
  // still unknown.
  const [authResolved, setAuthResolved] = useState(false);

  useEffect(() => {
    if (!firebaseEnabled) return;
    let active = true;
    getRuntime()
      .then((rt) => {
        if (!active) return;
        setRuntime(rt);
        setRuntimeError(null);
      })
      .catch((error: unknown) => {
        // A real init failure (bad config, storage blocked) is surfaced as a
        // discrete error screen instead of a permanent loading spinner.
        if (!active) return;
        setRuntime(null);
        setRuntimeError(
          error instanceof Error ? error.message : "Failed to start Firebase.",
        );
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!runtime) return;
    const unsubscribe = onAuthStateChanged(runtime.auth, (next) => {
      setUser(next);
      setAuthResolved(true);
    });
    return unsubscribe;
  }, [runtime]);

  const gate = resolveFirebaseGate({
    enabled: firebaseEnabled,
    runtimeError,
    hasRuntime: runtime !== null,
    authResolved,
  });

  async function signIn(email: string, password: string): Promise<void> {
    if (!runtime) throw new Error("Firebase is not ready.");
    await signInWithEmailAndPassword(runtime.auth, email.trim(), password);
  }

  async function createAccount(email: string, password: string): Promise<void> {
    if (!runtime) throw new Error("Firebase is not ready.");
    await createUserWithEmailAndPassword(runtime.auth, email.trim(), password);
  }

  async function signOut(): Promise<void> {
    if (runtime) await firebaseSignOut(runtime.auth);
  }

  return (
    <FirebaseAuthContext.Provider
      value={{
        enabled: firebaseEnabled,
        gate,
        runtimeError,
        user,
        uid: user?.uid ?? null,
        runtime,
        signIn,
        createAccount,
        signOut,
      }}
    >
      {children}
    </FirebaseAuthContext.Provider>
  );
}

export function useFirebaseAuth(): FirebaseAuthValue {
  const value = useContext(FirebaseAuthContext);
  if (!value) {
    throw new Error("useFirebaseAuth must be used inside FirebaseAuthProvider");
  }
  return value;
}