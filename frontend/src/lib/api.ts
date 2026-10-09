/** Minimal typed fetch client for the local API. */

import type { AppInfo } from "../types/api";
import { getAuthToken, notifyUnauthorized } from "./auth";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const BASE = "/api/v1";

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

/** Authorization header when a shared access token is in play. */
function authHeaders(headers: HeadersInit | undefined): HeadersInit {
  const token = getAuthToken();
  if (!token) return headers ?? {};
  return {
    ...typeof headers === "object" && !(headers instanceof Headers) ? headers : {},
    Authorization: `Bearer ${token}`,
  };
}

/** Turn a failed response into an ApiError carrying the server's message. */
async function toApiError(response: Response): Promise<ApiError> {
  const fallback = `Request failed (${response.status})`;
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail) {
      return new ApiError(response.status, body.detail);
    }
    if (Array.isArray(body.detail)) {
      // FastAPI request validation: [{ loc, msg }, ...]
      const messages = body.detail
        .map((entry) => (entry && typeof entry === "object" && "msg" in entry ? String(entry.msg) : ""))
        .filter(Boolean);
      if (messages.length) return new ApiError(response.status, messages.join(" · "));
    }
  } catch {
    // Non-JSON error body: fall through to the generic message.
  }
  return new ApiError(response.status, fallback);
}

async function request<T>(
  path: string,
  init: RequestInit & { signal?: AbortSignal } = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: authHeaders({ Accept: "application/json", ...(init.headers as object) }),
    });
  } catch (error) {
    if (isAbort(error)) throw error;
    throw new ApiError(0, "Cannot reach the Pilote Budget API. Is the backend running?");
  }
  if (response.status === 401) {
    // The shared token is missing or wrong: drop it so the sign-in screen
    // reappears instead of hammering the server with a dead credential.
    notifyUnauthorized();
  }
  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  return request<T>(path, { method: "GET", signal });
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function apiPut<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function apiDelete<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

/**
 * Multipart upload (CSV import). ``fields`` become form fields; files are
 * sent under the ``file`` key.
 */
export function apiUpload<T>(
  path: string,
  file: File | Blob,
  fields: Record<string, string>,
  filename = "upload.csv",
): Promise<T> {
  const form = new FormData();
  form.append("file", file, filename);
  for (const [key, value] of Object.entries(fields)) {
    form.append(key, value);
  }
  return request<T>(path, { method: "POST", body: form });
}

/** Absolute URL for a CSV download (filters included). */
export function apiUrl(path: string, params?: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  const suffix = query.toString();
  return `${BASE}${path}${suffix ? `?${suffix}` : ""}`;
}

export function fetchAppInfo(signal?: AbortSignal): Promise<AppInfo> {
  return fetch("/", { signal, headers: { Accept: "application/json" } }).then(
    async (response) => {
      if (!response.ok) {
        throw new ApiError(response.status, `Request failed (${response.status})`);
      }
      return (await response.json()) as AppInfo;
    },
  );
}
