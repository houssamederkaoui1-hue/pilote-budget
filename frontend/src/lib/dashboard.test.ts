import { describe, expect, it } from "vitest";

import {
  changeHint,
  currentPeriodLine,
  currentPeriodWindow,
  monthLabel,
  periodRangeLabel,
} from "./dashboard";

describe("monthLabel", () => {
  it("parses an ISO date into a short month token", () => {
    expect(monthLabel("2026-10-01")).toMatch(/^[A-Za-zÀ-ÿ'.\-]+$/);
  });

  it("returns empty for invalid input", () => {
    expect(monthLabel("nonsense")).toBe("");
  });
});

describe("periodRangeLabel", () => {
  it("renders both dates in full with the year", () => {
    const rendered = periodRangeLabel({
      period_start: "2026-10-01",
      period_end: "2026-10-31",
    });
    expect(rendered).toBe("Oct 1 – Oct 31, 2026");
  });

  it("survives a year boundary (day-15 periods)", () => {
    const rendered = periodRangeLabel({
      period_start: "2025-12-15",
      period_end: "2026-01-14",
    });
    expect(rendered).toContain("2025");
    expect(rendered).toContain("2026");
  });

  it("returns empty for invalid input", () => {
    expect(periodRangeLabel({ period_start: "x", period_end: "" })).toBe("");
  });
});

describe("changeHint", () => {
  it("handles a missing previous period", () => {
    expect(changeHint(null)).toBe("No previous period data");
  });

  it("signs positive and negative changes", () => {
    expect(changeHint(12.5)).toContain("+12.5% vs previous period");
    expect(changeHint(-3)).toContain("-3.0% vs previous period");
  });

  it("reports a flat period", () => {
    expect(changeHint(0)).toBe("Flat vs previous period");
  });
});

describe("currentPeriodWindow", () => {
  it("anchors a default day-1 period on the calendar month", () => {
    const { period_start, period_end } = currentPeriodWindow(1, new Date(2026, 9, 8));
    expect(period_start.getDate()).toBe(1);
    expect(period_end.getDate()).toBe(31);
  });

  it("uses the current month when today >= month_start_day", () => {
    const { period_start, period_end } = currentPeriodWindow(15, new Date(2026, 9, 20));
    expect(period_start.getFullYear()).toBe(2026);
    expect(period_start.getMonth()).toBe(9);
    expect(period_end.getMonth()).toBe(10);
    expect(period_end.getDate()).toBe(14);
  });

  it("moves to the previous month when today < month_start_day", () => {
    const { period_start, period_end } = currentPeriodWindow(15, new Date(2026, 9, 10));
    expect(period_start.getMonth()).toBe(8); // September
    expect(period_start.getDate()).toBe(15);
    expect(period_end.getMonth()).toBe(9); // October
    expect(period_end.getDate()).toBe(14);
  });
});

describe("currentPeriodLine", () => {
  it("renders the header-style line for a day-1 period", () => {
    expect(currentPeriodLine(1, new Date(2026, 9, 8))).toBe("Oct 2026 · period 1–31");
  });

  it("renders a full range when the window crosses the month boundary", () => {
    expect(currentPeriodLine(15, new Date(2026, 9, 10))).toBe("Sep 15 – Oct 14, 2026");
  });

  it("includes both years when the window crosses a year boundary", () => {
    expect(currentPeriodLine(15, new Date(2026, 0, 10))).toBe("Dec 15, 2025 – Jan 14, 2026");
  });
});