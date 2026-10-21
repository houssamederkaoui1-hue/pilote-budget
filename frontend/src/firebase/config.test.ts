import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * The /firebase/* path must only activate when the three identity-critical
 * public keys are present. If that gate is wrong the route either never loads
 * or could attempt to run against a half-configured Firebase project.
 */

async function loadConfig() {
  vi.resetModules();
  return import("./config");
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("firebaseEnabled gate", () => {
  it("enables only when apiKey, authDomain and projectId are present", async () => {
    vi.stubEnv("VITE_FIREBASE_API_KEY", "AIza-public");
    vi.stubEnv("VITE_FIREBASE_AUTH_DOMAIN", "demo.firebaseapp.com");
    vi.stubEnv("VITE_FIREBASE_PROJECT_ID", "demo");
    const { firebaseEnabled, PUBLIC_FIREBASE_CONFIG } = await loadConfig();
    expect(firebaseEnabled).toBe(true);
    expect(PUBLIC_FIREBASE_CONFIG.projectId).toBe("demo");
  });

  it("stays disabled when any identity key is missing", async () => {
    vi.stubEnv("VITE_FIREBASE_API_KEY", "AIza-public");
    vi.stubEnv("VITE_FIREBASE_AUTH_DOMAIN", "demo.firebaseapp.com");
    expect((await loadConfig()).firebaseEnabled).toBe(false);
  });

  it("treats whitespace-only values as missing", async () => {
    vi.stubEnv("VITE_FIREBASE_API_KEY", "   ");
    vi.stubEnv("VITE_FIREBASE_AUTH_DOMAIN", "demo.firebaseapp.com");
    vi.stubEnv("VITE_FIREBASE_PROJECT_ID", "demo");
    expect((await loadConfig()).firebaseEnabled).toBe(false);
  });

  it("does not require the optional storage/sender/appId keys", async () => {
    vi.stubEnv("VITE_FIREBASE_API_KEY", "AIza-public");
    vi.stubEnv("VITE_FIREBASE_AUTH_DOMAIN", "demo.firebaseapp.com");
    vi.stubEnv("VITE_FIREBASE_PROJECT_ID", "demo");
    expect((await loadConfig()).firebaseEnabled).toBe(true);
  });

  it("reads only the documented VITE_FIREBASE_* names", async () => {
    vi.stubEnv("VITE_FIREBASE_API_KEY", "AIza-public");
    vi.stubEnv("VITE_FIREBASE_AUTH_DOMAIN", "demo.firebaseapp.com");
    vi.stubEnv("VITE_FIREBASE_PROJECT_ID", "demo");
    vi.stubEnv("VITE_FIREBASE_STORAGE_BUCKET", "demo.appspot.com");
    vi.stubEnv("VITE_FIREBASE_MESSAGING_SENDER_ID", "12345");
    vi.stubEnv("VITE_FIREBASE_APP_ID", "1:2:web:3");
    const { PUBLIC_FIREBASE_CONFIG } = await loadConfig();
    expect(PUBLIC_FIREBASE_CONFIG).toEqual({
      apiKey: "AIza-public",
      authDomain: "demo.firebaseapp.com",
      projectId: "demo",
      storageBucket: "demo.appspot.com",
      messagingSenderId: "12345",
      appId: "1:2:web:3",
    });
  });
});

/**
 * The emulator switch must never be on unless a developer explicitly opts in.
 * A regression here would silently point real builds at a local emulator.
 */
describe("firebaseEmulatorsEnabled gate", () => {
  it("is OFF when the flag is absent", async () => {
    vi.stubEnv("VITE_FIREBASE_API_KEY", "AIza-public");
    vi.stubEnv("VITE_FIREBASE_AUTH_DOMAIN", "demo.firebaseapp.com");
    vi.stubEnv("VITE_FIREBASE_PROJECT_ID", "demo");
    expect((await loadConfig()).firebaseEmulatorsEnabled).toBe(false);
  });

  it("accepts true / 1 / yes (any case, trimmed)", async () => {
    for (const value of ["true", "TRUE", " 1 ", "yes", "Yes"]) {
      vi.stubEnv("VITE_FIREBASE_USE_EMULATORS", value);
      expect((await loadConfig()).firebaseEmulatorsEnabled).toBe(true);
    }
  });

  it("stays OFF for anything else", async () => {
    for (const value of ["", "false", "0", "no", "production"]) {
      vi.stubEnv("VITE_FIREBASE_USE_EMULATORS", value);
      expect((await loadConfig()).firebaseEmulatorsEnabled).toBe(false);
    }
  });

  it("defaults the endpoints to localhost standard ports", async () => {
    const { FIREBASE_AUTH_EMULATOR_URL, FIREBASE_FIRESTORE_EMULATOR } = await loadConfig();
    expect(FIREBASE_AUTH_EMULATOR_URL).toBe("http://127.0.0.1:9099");
    expect(FIREBASE_FIRESTORE_EMULATOR).toEqual({ host: "127.0.0.1", port: 8080 });
  });

  it("honours an explicit host override", async () => {
    vi.stubEnv("VITE_FIREBASE_EMULATOR_HOST", "10.0.0.5");
    const { FIREBASE_AUTH_EMULATOR_URL, FIREBASE_FIRESTORE_EMULATOR } = await loadConfig();
    expect(FIREBASE_AUTH_EMULATOR_URL).toBe("http://10.0.0.5:9099");
    expect(FIREBASE_FIRESTORE_EMULATOR).toEqual({ host: "10.0.0.5", port: 8080 });
  });
});