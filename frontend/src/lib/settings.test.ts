import { describe, expect, it } from "vitest";

import {
  ALL_SECTION_IDS,
  dashboardToggleRow,
  hiddenSections,
  orderedVisibleSections,
  pruneOrder,
  usesThreeMonthHistory,
} from "./settings";
import type { DashboardPreferences } from "../types/api";

const SECTIONS_OFF_GOALS_CASHFLOW: DashboardPreferences["sections"] = {
  stats: true,
  cash_flow: false,
  category_spending: true,
  net_worth: true,
  budget_vs_actual: true,
  safe_to_spend: true,
  forecast: true,
  financial_health: true,
  insights: true,
  goals: false,
  upcoming_bills: true,
  debts: true,
};

describe("settings layout helpers", () => {
  it("orders visible sections while honouring custom order", () => {
    const order = orderedVisibleSections(
      SECTIONS_OFF_GOALS_CASHFLOW,
      ["debts", "stats", "net_worth"],
    );
    expect(order[0]).toBe("debts");
    expect(order[1]).toBe("stats");
    expect(order).toContain("net_worth");
    expect(order).not.toContain("goals");
    expect(order).not.toContain("cash_flow");
    expect(new Set(order).size).toBe(order.length);
  });

  it("never drops sections the server does not know about yet", () => {
    const partial = orderedVisibleSections(
      {
        stats: true,
        cash_flow: true,
        net_worth: true,
        goals: true,
        debts: true,
      } as DashboardPreferences["sections"],
      ["stats", "debts"],
    );
    expect(partial).toEqual(expect.arrayContaining(["stats", "debts", "net_worth"]));
  });

  it("lists the hidden sections for the settings UI", () => {
    expect(hiddenSections(SECTIONS_OFF_GOALS_CASHFLOW)).toEqual(["cash_flow", "goals"]);
  });

  it("returns every canonical section as a toggle row", () => {
    const row = dashboardToggleRow(SECTIONS_OFF_GOALS_CASHFLOW);
    expect(row).toHaveLength(ALL_SECTION_IDS.length);
    expect(row.find((toggle) => toggle.section === "goals")?.visible).toBe(false);
    expect(row.find((toggle) => toggle.section === "stats")?.visible).toBe(true);
  });

  it("prunes removed sections and appends missing ones", () => {
    const pruned = pruneOrder(
      ["stats", "ghost", "goals", "debts"],
      (id) => id !== "goals",
    );
    expect(pruned).toContain("stats");
    expect(pruned).toContain("debts");
    expect(pruned).not.toContain("ghost");
    expect(pruned).not.toContain("goals");
    expect(new Set(pruned).size).toBe(pruned.length);
    expect(pruned).toEqual(expect.arrayContaining(ALL_SECTION_IDS.filter((id) => id !== "goals")));
  });

  it("maps last-three personalization to fewer months", () => {
    expect(usesThreeMonthHistory("last_three")).toBe(true);
    expect(usesThreeMonthHistory("current")).toBe(false);
  });
});