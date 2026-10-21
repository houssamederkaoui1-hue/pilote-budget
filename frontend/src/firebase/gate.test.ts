import { describe, expect, it } from "vitest";

import {
  resolveFirebaseGate,
  resolveFirebaseRedirect,
  type FirebaseGate,
  type FirebaseGateInput,
} from "./gate";

/* Regression coverage for the Firebase preview deep-link / hard-refresh bug.
 *
 * Root cause: the runtime became available before `onAuthStateChanged` fired,
 * so the router rendered with `user === null` and redirected the requested URL
 * to `/firebase/login`, after which the restored session bounced it to the
 * dashboard. The gate must therefore be `loading` (never redirect) until auth
 * is actually known. `resolveFirebaseRedirect` is the exact function the
 * component uses, so these tests guard real behaviour.
 */

function gateInput(overrides: Partial<FirebaseGateInput> = {}): FirebaseGateInput {
  return {
    enabled: true,
    runtimeError: null,
    hasRuntime: false,
    authResolved: false,
    ...overrides,
  };
}

describe("resolveFirebaseGate", () => {
  it("is not-configured when the Firebase build config is absent", () => {
    expect(
      resolveFirebaseGate(gateInput({ enabled: false, hasRuntime: true, authResolved: true })),
    ).toBe("not-configured");
  });

  it("is error when runtime initialisation failed", () => {
    expect(resolveFirebaseGate(gateInput({ runtimeError: "boom" }))).toBe("error");
  });

  it("is loading before the runtime exists", () => {
    expect(resolveFirebaseGate(gateInput())).toBe("loading");
  });

  it("stays loading when the runtime exists but auth has not resolved (the race)", () => {
    expect(resolveFirebaseGate(gateInput({ hasRuntime: true, authResolved: false }))).toBe(
      "loading",
    );
  });

  it("is ready only once the runtime exists and auth has resolved", () => {
    expect(resolveFirebaseGate(gateInput({ hasRuntime: true, authResolved: true }))).toBe(
      "ready",
    );
  });
});

describe("resolveFirebaseRedirect — never redirect before auth is known", () => {
  const links = [
    "/firebase/login",
    "/firebase",
    "/firebase/dashboard",
    "/firebase/accounts",
    "/firebase/categories",
    "/firebase/transactions",
  ];
  const nonReady: FirebaseGate[] = ["not-configured", "error", "loading"];

  for (const gate of nonReady) {
    for (const link of links) {
      it(`${gate} + ${link} is preserved for a signed-in user`, () => {
        expect(resolveFirebaseRedirect(link, gate, true)).toBeNull();
      });
      it(`${gate} + ${link} is preserved for a signed-out user`, () => {
        expect(resolveFirebaseRedirect(link, gate, false)).toBeNull();
      });
    }
  }
});

describe("resolveFirebaseRedirect — deep links when ready", () => {
  it("sends a signed-out user on an authenticated sub-route to login", () => {
    for (const link of [
      "/firebase/dashboard",
      "/firebase/accounts",
      "/firebase/categories",
      "/firebase/transactions",
    ]) {
      expect(resolveFirebaseRedirect(link, "ready", false)).toBe("/firebase/login");
    }
  });

  it("keeps a signed-in user on their authenticated sub-route", () => {
    for (const link of [
      "/firebase/dashboard",
      "/firebase/accounts",
      "/firebase/categories",
      "/firebase/transactions",
    ]) {
      expect(resolveFirebaseRedirect(link, "ready", true)).toBeNull();
    }
  });

  it("renders login for a signed-out user", () => {
    expect(resolveFirebaseRedirect("/firebase/login", "ready", false)).toBeNull();
  });

  it("bounces a signed-in user off the login page to the dashboard", () => {
    expect(resolveFirebaseRedirect("/firebase/login", "ready", true)).toBe(
      "/firebase/dashboard",
    );
  });

  it("resolves the bare home path", () => {
    expect(resolveFirebaseRedirect("/firebase", "ready", true)).toBe(
      "/firebase/dashboard",
    );
    expect(resolveFirebaseRedirect("/firebase", "ready", false)).toBe(
      "/firebase/login",
    );
    expect(resolveFirebaseRedirect("/firebase/", "ready", true)).toBe(
      "/firebase/dashboard",
    );
  });

  it("tolerates a trailing slash on a sub-route", () => {
    expect(resolveFirebaseRedirect("/firebase/accounts/", "ready", true)).toBeNull();
    expect(resolveFirebaseRedirect("/firebase/accounts/", "ready", false)).toBe(
      "/firebase/login",
    );
  });

  it("routes an unknown /firebase/* path to login", () => {
    expect(resolveFirebaseRedirect("/firebase/nope", "ready", true)).toBe(
      "/firebase/login",
    );
    expect(resolveFirebaseRedirect("/firebase/nope", "ready", false)).toBe(
      "/firebase/login",
    );
  });
});

describe("resolveFirebaseRedirect — cold-load sequences", () => {
  it("preserves /firebase/accounts through the whole auth-init race", () => {
    const link = "/firebase/accounts";

    // 1. Cold start: runtime not created yet.
    let gate = resolveFirebaseGate(gateInput());
    expect(gate).toBe("loading");
    expect(resolveFirebaseRedirect(link, gate, false)).toBeNull();

    // 2. Runtime created, onAuthStateChanged has NOT fired yet.
    gate = resolveFirebaseGate(gateInput({ hasRuntime: true, authResolved: false }));
    expect(gate).toBe("loading");
    expect(resolveFirebaseRedirect(link, gate, false)).toBeNull();

    // 3. Auth resolves with the restored session: deep link survives.
    gate = resolveFirebaseGate(gateInput({ hasRuntime: true, authResolved: true }));
    expect(gate).toBe("ready");
    expect(resolveFirebaseRedirect(link, gate, true)).toBeNull();
  });

  it("redirects to login only after auth resolves with no session", () => {
    const link = "/firebase/accounts";
    const gate = resolveFirebaseGate(gateInput({ hasRuntime: true, authResolved: true }));
    expect(gate).toBe("ready");
    expect(resolveFirebaseRedirect(link, gate, false)).toBe("/firebase/login");
  });

  it("sign-out from a sub-route lands on login", () => {
    const gate = resolveFirebaseGate(gateInput({ hasRuntime: true, authResolved: true }));
    expect(resolveFirebaseRedirect("/firebase/accounts", gate, true)).toBeNull();
    expect(resolveFirebaseRedirect("/firebase/accounts", gate, false)).toBe(
      "/firebase/login",
    );
  });
});
