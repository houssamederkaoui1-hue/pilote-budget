import { describe, expect, it } from "vitest";

import { apiUrl } from "./api";

describe("apiUrl", () => {
  it("builds a plain path when no params are given", () => {
    expect(apiUrl("/transactions")).toBe("/api/v1/transactions");
  });

  it("appends non-empty params to the query string", () => {
    expect(
      apiUrl("/transactions/export.csv", { q: "groceries", type: "expense", limit: 25 }),
    ).toBe("/api/v1/transactions/export.csv?q=groceries&type=expense&limit=25");
  });

  it("drops undefined and empty values", () => {
    expect(apiUrl("/transactions", { date_from: "", type: undefined, limit: 0 })).toBe(
      "/api/v1/transactions?limit=0",
    );
  });

  it("encodes special characters", () => {
    expect(apiUrl("/accounts", { q: "a b&c" })).toBe("/api/v1/accounts?q=a+b%26c");
  });
});