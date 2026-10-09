import { describe, expect, it } from "vitest";

import {
  bestSuggestions,
  captureToCreate,
  duplicateTone,
  duplicateToneLabel,
  topSuggestion,
} from "./quick";
import type { CategorySuggestion, DuplicateMatch, QuickCaptureResponse } from "../types/api";

function suggestion(overrides: Partial<CategorySuggestion>): CategorySuggestion {
  return {
    category_id: 1,
    category_name: "Food",
    confidence: "exact",
    evidence: null,
    score: 10,
    ...overrides,
  };
}

function match(overrides: Partial<DuplicateMatch>): DuplicateMatch {
  return {
    id: 1,
    account_id: 1,
    date: "2026-10-08",
    amount: 20,
    description: "x",
    same_day: false,
    days_apart: 2,
    ...overrides,
  };
}

describe("quick add suggestions", () => {
  it("ranks exact matches above similar above popular", () => {
    const sorted = bestSuggestions([
      suggestion({ confidence: "popular", score: 99, category_id: 3 }),
      suggestion({ confidence: "similar", score: 40, category_id: 2 }),
      suggestion({ confidence: "exact", score: 5, category_id: 1 }),
    ]);
    expect(sorted[0].category_id).toBe(1);
    expect(sorted[1].category_id).toBe(2);
    expect(sorted[2].category_id).toBe(3);
  });

  it("breaks confidence ties by score", () => {
    const sorted = bestSuggestions([
      suggestion({ confidence: "exact", score: 3, category_id: 2 }),
      suggestion({ confidence: "exact", score: 9, category_id: 1 }),
    ]);
    expect(sorted[0].category_id).toBe(1);
  });

  it("picks the top suggestion or nothing", () => {
    expect(topSuggestion([suggestion({})])?.category_id).toBe(1);
    expect(topSuggestion([])).toBeNull();
  });
});

describe("quick add duplicate triage", () => {
  it("escalates same-day, then near, then none", () => {
    expect(duplicateTone([match({ same_day: true })])).toBe("same_day");
    expect(duplicateTone([match({ same_day: false })])).toBe("near");
    expect(duplicateTone([])).toBe("none");
    expect(duplicateToneLabel("same_day")).toContain("duplicate");
  });
});

describe("captureToCreate", () => {
  const capture: QuickCaptureResponse = {
    type: "expense",
    amount: 12.5,
    date: "2026-10-08",
    account_id: 7,
    category_id: 3,
    description: "Lunch",
    categories: [],
    duplicates: [],
    warnings: [],
  };

  it("carries the capture forward verbatim", () => {
    const payload = captureToCreate(capture);
    expect(payload.amount).toBe(12.5);
    expect(payload.account_id).toBe(7);
    expect(payload.category_id).toBe(3);
    expect(payload.date).toBe("2026-10-08");
  });

  it("allows user overrides and duplicate rejection", () => {
    const payload = captureToCreate(capture, {
      categoryId: 9,
      rejectDuplicate: true,
    });
    expect(payload.category_id).toBe(9);
    expect(payload.reject_duplicate).toBe(true);
    expect(payload.amount).toBe(12.5);
  });
});