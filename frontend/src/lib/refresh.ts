/** Tiny in-app data-change bus so global actions (Quick Add) can refresh pages. */

type Listener = () => void;

const listeners = new Set<Listener>();

/** Subscribe to "data changed somewhere" notifications; returns unsubscribe. */
export function subscribeDataChanged(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Broadcast that ledger data changed (after a Quick Add / record / delete). */
export function notifyDataChanged(): void {
  listeners.forEach((listener) => listener());
}