import { describe, expect, it } from "vitest";

import { formatDate, formatMonthAnchor } from "./format";

describe("formatDate", () => {
  it("returns an em dash for invalid input", () => {
    expect(formatDate("not-a-date")).toBe("—");
  });

  it("renders a recognizable date", () => {
    const rendered = formatDate("2026-03-14T12:00:00Z");
    expect(rendered).toContain("2026");
    expect(rendered).toContain("Mar");
  });
});

describe("formatMonthAnchor", () => {
  it("formats a month + year anchor", () => {
    const rendered = formatMonthAnchor(new Date("2026-03-14T12:00:00Z"));
    expect(rendered).toContain("March");
    expect(rendered).toContain("2026");
  });
});