/** Pure helpers for settings-backed dashboard layout + personalization. */

import { DASHBOARD_SECTION_META, type DashboardPreferences, type DashboardSectionId } from "../types/api";

export const SUPPORTED_CURRENCIES: { code: string; label: string }[] = [
  { code: "MAD", label: "MAD — Moroccan Dirham" },
  { code: "EUR", label: "EUR — Euro" },
  { code: "USD", label: "USD — US Dollar" },
  { code: "GBP", label: "GBP — British Pound" },
  { code: "CAD", label: "CAD — Canadian Dollar" },
  { code: "AUD", label: "AUD — Australian Dollar" },
  { code: "NZD", label: "NZD — New Zealand Dollar" },
  { code: "CHF", label: "CHF — Swiss Franc" },
  { code: "JPY", label: "JPY — Japanese Yen" },
  { code: "INR", label: "INR — Indian Rupee" },
];

/** All known section ids in canonical order (backed by the API contract). */
export const ALL_SECTION_IDS: DashboardSectionId[] = DASHBOARD_SECTION_META.map((entry) => entry.id);

export function sectionLabel(id: DashboardSectionId): string {
  return DASHBOARD_SECTION_META.find((entry) => entry.id === id)?.label ?? id;
}

/** Section ids that are user-turned-*off*, in canonical order (nice for lists). */
export function hiddenSections(sections: DashboardPreferences["sections"]): DashboardSectionId[] {
  return ALL_SECTION_IDS.filter((id) => sections[id] === false);
}

/**
 * The ordered, visible section ids to render, honouring the stored order and
 * appending any freshly-added sections the server hasn't seen yet.
 */
export function orderedVisibleSections(
  sections: DashboardPreferences["sections"],
  order: DashboardSectionId[],
): DashboardSectionId[] {
  const visible = new Set<DashboardSectionId>(
    ALL_SECTION_IDS.filter((id) => sections[id] !== false),
  );
  const ordered: DashboardSectionId[] = [];
  for (const id of [...order, ...ALL_SECTION_IDS]) {
    if (visible.has(id) && !ordered.includes(id)) ordered.push(id);
  }
  return ordered;
}

/** True when "last three periods" personalization is active. */
export function usesThreeMonthHistory(period: DashboardPreferences["period"]): boolean {
  return period === "last_three";
}

export interface Toggle {
  section: DashboardSectionId;
  visible: boolean;
}

/** Stable personalization form state: every section in canonical order. */
export function dashboardToggleRow(
  sections: DashboardPreferences["sections"],
): Toggle[] {
  return ALL_SECTION_IDS.map((section) => ({
    section,
    visible: sections[section] !== false,
  }));
}

/** Rebuild a valid order after any set of visibility changes (no duplicates). */
export function pruneOrder(
  order: string[],
  keep: (id: DashboardSectionId) => boolean,
): DashboardSectionId[] {
  const pruned = order.filter(
    (id): id is DashboardSectionId => ALL_SECTION_IDS.includes(id as DashboardSectionId) && keep(id as DashboardSectionId),
  );
  const missing = ALL_SECTION_IDS.filter((id) => keep(id) && !pruned.includes(id));
  return [...pruned, ...missing];
}