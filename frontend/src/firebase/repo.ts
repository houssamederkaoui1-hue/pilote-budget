/**
 * READ-ONLY Firestore data access for the Phase 1 Firebase path.
 *
 * Every query is rooted at `users/{uid}/...` where `uid` comes from the signed
 * in Firebase user. The Security Rules are the only thing that enforces the
 * boundary — this code never queries another UID and has no write surface.
 *
 * State is explicit: loading, ready, EMPTY, and errors classified as
 * permission-denied / offline / unknown. Offline detection combines the
 * browser connectivity events with Firestore snapshot metadata
 * (snapshot.metadata.fromCache) so a cached view is labelled, never silent.
 */

import { useCallback, useEffect, useState } from "react";
import {
  collection,
  doc,
  onSnapshot,
  type DocumentData,
  type DocumentSnapshot,
  type FirestoreError,
  type QuerySnapshot,
  type SnapshotListenOptions,
} from "firebase/firestore";
import { useFirebaseAuth } from "./auth";
import {
  classifyReadError,
  mapAccount,
  mapCategory,
  mapTransaction,
  mapTransfer,
  type FAccount,
  type FCategory,
  type FProfile,
  type FTransaction,
  type FTransfer,
  type ReadError,
} from "./model";

const SNAPSHOT_OPTIONS: SnapshotListenOptions = { includeMetadataChanges: true };

export interface CollectionState<T> {
  docs: T[];
  loading: boolean;
  empty: boolean;
  offline: boolean;
  online: boolean;
  error: ReadError | null;
  retry: () => void;
}

const initialCollection = <T,>(): CollectionState<T> => ({
  docs: [],
  loading: true,
  empty: false,
  offline: false,
  online: true,
  error: null,
  retry: () => undefined,
});

export function useOnline(): boolean {
  const [online, setOnline] = useState<boolean>(
    typeof navigator === "undefined" ? true : navigator.onLine,
  );
  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const update = () => setOnline(navigator.onLine);
    update();
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  return online;
}

function useCollection<T>(
  path: string,
  map: (id: string, raw: Record<string, unknown>) => T,
): CollectionState<T> {
  const { uid, runtime } = useFirebaseAuth();
  const online = useOnline();
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<CollectionState<T>>(initialCollection);

  const retry = useCallback(() => setAttempt((value) => value + 1), []);

  useEffect(() => {
    if (!uid || !runtime) return;
    let active = true;
    let unsubscribe: (() => void) | undefined;
    setState((previous) => ({ ...previous, loading: true, error: null }));

    const ref = collection(runtime.db, "users", uid, path);
    try {
      unsubscribe = onSnapshot(
        ref,
        SNAPSHOT_OPTIONS,
        (snapshot: QuerySnapshot<DocumentData, DocumentData>) => {
          if (!active) return;
          const docs = snapshot.docs.map((snapDoc) =>
            map(snapDoc.id, snapDoc.data() as Record<string, unknown>),
          );
          setState({
            docs,
            loading: false,
            empty: snapshot.size === 0,
            offline: snapshot.metadata.fromCache,
            online,
            error: null,
            retry,
          });
        },
        (error: FirestoreError) => {
          if (!active) return;
          setState({
            docs: [],
            loading: false,
            empty: false,
            offline: false,
            online,
            error: classifyReadError(error),
            retry,
          });
        },
      );
    } catch (error) {
      if (active) {
        setState({
          docs: [],
          loading: false,
          empty: false,
          offline: false,
          online,
          error: classifyReadError(error),
          retry,
        });
      }
    }

    return () => {
      active = false;
      if (unsubscribe) unsubscribe();
    };
  }, [uid, runtime, path, attempt, online, retry]);

  return state;
}

export function useAccounts(): CollectionState<FAccount> {
  return useCollection<FAccount>("accounts", mapAccount);
}

export function useCategories(): CollectionState<FCategory> {
  return useCollection<FCategory>("categories", mapCategory);
}

export function useTransactions(): CollectionState<FTransaction> {
  return useCollection<FTransaction>("transactions", mapTransaction);
}

export function useTransfers(): CollectionState<FTransfer> {
  return useCollection<FTransfer>("transfers", mapTransfer);
}

export interface ProfileState {
  currency: string;
  loading: boolean;
}

const DEFAULT_PROFILE: ProfileState = { currency: "MAD", loading: true };

/** Reads `users/{uid}/profile/me` for display currency (single source). */
export function useProfile(): ProfileState {
  const { uid, runtime } = useFirebaseAuth();
  const [state, setState] = useState<ProfileState>(DEFAULT_PROFILE);

  useEffect(() => {
    if (!uid || !runtime) {
      setState({ currency: "MAD", loading: true });
      return;
    }
    let active = true;
    setState({ currency: "MAD", loading: true });
    const ref = doc(runtime.db, "users", uid, "profile", "me");
    const unsubscribe = onSnapshot(
      ref,
      SNAPSHOT_OPTIONS,
      (snapshot: DocumentSnapshot<DocumentData, DocumentData>) => {
        if (!active) return;
        const data = snapshot.data() as Partial<FProfile> | undefined;
        const currency =
          typeof data?.currency === "string" && data.currency
            ? data.currency
            : "MAD";
        setState({ currency, loading: false });
      },
      () => {
        if (active) setState({ currency: "MAD", loading: false });
      },
    );
    return () => {
      active = false;
      unsubscribe();
    };
  }, [uid, runtime]);

  return state;
}