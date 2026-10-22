import { describe, expect, it } from "vitest";

import {
  bool,
  centsToNumber,
  classifyReadError,
  int,
  mapAccount,
  mapCategory,
  mapTransaction,
  optStr,
  str,
  type ReadError,
} from "./model";

describe("centsToNumber", () => {
  it("converts integer cents to a display amount", () => {
    expect(centsToNumber(123456)).toBe(1234.56);
  });

  it("returns 0 for non-numeric input", () => {
    expect(centsToNumber("nope" as unknown as number)).toBe(0);
  });
});

describe("primitives", () => {
  it("str keeps strings, coerces everything else", () => {
    expect(str("hello")).toBe("hello");
    expect(str(null)).toBe("");
    expect(str(undefined)).toBe("");
    expect(str(42)).toBe("");
  });

  it("optStr keeps non-empty strings, else null", () => {
    expect(optStr("x")).toBe("x");
    expect(optStr("")).toBe(null);
    expect(optStr(null)).toBe(null);
  });

  it("bool/int coerce", () => {
    expect(bool(true)).toBe(true);
    expect(bool("yes")).toBe(false);
    expect(int(12)).toBe(12);
    expect(int("12")).toBe(0);
  });
});

describe("document mappers (shapes written by the import tool)", () => {
  it("maps a category document", () => {
    const category = mapCategory("c1", {
      name: "Groceries",
      type: "expense",
      active: true,
      parentId: "c2",
      description: "food",
    });
    expect(category.id).toBe("c1");
    expect(category.type).toBe("expense");
    expect(category.active).toBe(true);
    expect(category.parentId).toBe("c2");
  });

  it("maps an account document with integer cents", () => {
    const account = mapAccount("a1", {
      name: "Checking",
      type: "checking",
      openingBalanceCents: 1000,
      currentBalanceCents: 123456,
      currency: "MAD",
      active: true,
    });
    expect(account.currency).toBe("MAD");
    expect(account.currentBalanceCents).toBe(123456);
    expect(account.type).toBe("checking");
    expect(account.description).toBe(null);
  });

  it("maps a transaction document and defaults missing optionals", () => {
    const tx = mapTransaction("t1", {
      accountId: "a1",
      type: "expense",
      amountCents: 243,
      date: "2026-01-02",
      description: "Coffee",
      status: "cleared",
      imported: true,
    });
    expect(tx.categoryId).toBe(null);
    expect(tx.notes).toBe(null);
    expect(tx.imported).toBe(true);
    expect(tx.amountCents).toBe(243);
  });
});

describe("classifyReadError", () => {
  it("classifies permission-denied", () => {
    const err = { code: "permission-denied", message: "Missing or insufficient permissions" };
    expect(classifyReadError(err).kind).toBe("permission-denied");
  });

  it("classifies network / unavailable as offline", () => {
    expect(classifyReadError({ code: "unavailable" }).kind).toBe("offline");
    expect(classifyReadError({ code: "network-request-failed" }).kind).toBe("offline");
    expect(classifyReadError(new Error("Failed to fetch: network")).kind).toBe("offline");
  });

  it("falls back to unknown for anything else", () => {
    const result: ReadError = classifyReadError({ code: "not-a-real-code" });
    expect(result.kind).toBe("unknown");
    expect(result.message.length).toBeGreaterThan(0);
  });
});