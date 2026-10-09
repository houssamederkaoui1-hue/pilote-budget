/** Optional bearer-token auth, driven by the backend's PILOTE_ACCESS_TOKEN. */

const TOKEN_KEY = "pilote.access.token";
export const AUTH_CHANGE_EVENT = "pilote:auth-change";
export const UNAUTHORIZED_EVENT = "pilote:unauthorized";

function readStorage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function getAuthToken(): string | null {
  const storage = readStorage();
  if (!storage) return null;
  const token = storage.getItem(TOKEN_KEY);
  return token && token.trim() !== "" ? token : null;
}

export function setAuthToken(token: string): void {
  const storage = readStorage();
  if (storage) storage.setItem(TOKEN_KEY, token.trim());
  window.dispatchEvent(new Event(AUTH_CHANGE_EVENT));
}

export function clearAuthToken(): void {
  const storage = readStorage();
  if (storage) storage.removeItem(TOKEN_KEY);
  window.dispatchEvent(new Event(AUTH_CHANGE_EVENT));
}

/** Fire when a guarded API call answers 401 (token missing/invalid). */
export function notifyUnauthorized(): void {
  clearAuthToken();
  window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
}

export function subscribeAuth(listener: () => void): () => void {
  window.addEventListener(AUTH_CHANGE_EVENT, listener);
  return () => window.removeEventListener(AUTH_CHANGE_EVENT, listener);
}