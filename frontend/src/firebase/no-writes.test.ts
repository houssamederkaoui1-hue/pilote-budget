import { describe, expect, it } from "vitest";

/**
 * Phase 2.1 is read-only. This guard fails the build if any Firestore *data
 * write* API (or an offline write-enabler) appears anywhere in the Firebase
 * preview source. Authentication (sign-in/out) is intentionally allowed.
 *
 * The source text is inlined by Vite's `?raw` glob so we do not need Node fs
 * types in the app tsconfig. Test files themselves are excluded below.
 */
const FIRESTORE_WRITE_APIS = [
  "setDoc",
  "addDoc",
  "updateDoc",
  "deleteDoc",
  "writeBatch",
  "runTransaction",
  "enableNetwork",
];

const RAW_SOURCES = import.meta.glob("./*.{ts,tsx}", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const SOURCE_FILES = Object.entries(RAW_SOURCES).filter(
  ([path]) => !/\.test\.tsx?$/.test(path),
);

describe("Firebase preview stays read-only (no Firestore write APIs)", () => {
  it("found the Firebase source files to scan", () => {
    expect(SOURCE_FILES.length).toBeGreaterThan(0);
  });

  for (const api of FIRESTORE_WRITE_APIS) {
    it(`never references ${api}`, () => {
      const offenders = SOURCE_FILES.filter(([, contents]) => contents.includes(api)).map(
        ([path]) => path,
      );
      expect(offenders).toEqual([]);
    });
  }
});
