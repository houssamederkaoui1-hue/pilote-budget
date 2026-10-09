/** Assistant presentation helpers (pure; testable without the API). */

import type { AssistantInsight, AssistantSource } from "../types/api";

const SEVERITY_ORDER: Record<string, number> = {
  critical: 0,
  warning: 1,
  success: 2,
  info: 3,
};

/** Stable ordering for insight cards: critical → warning → success → info. */
export function sortInsights(insights: AssistantInsight[]): AssistantInsight[] {
  return [...insights].sort(
    (a, b) =>
      (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9) ||
      (b.priority ?? 0) - (a.priority ?? 0) ||
      a.id.localeCompare(b.id),
  );
}

export function severityLabel(severity: string): string {
  return severity.charAt(0).toUpperCase() + severity.slice(1);
}

/** Where a structured answer got its numbers. */
export function sourceLabel(source: AssistantSource): string {
  switch (source) {
    case "ledger":
      return "From your ledger";
    case "plan":
      return "From your plan";
    case "estimate":
      return "Estimate";
    case "assistant":
    default:
      return "Assistant";
  }
}

/** Badge tone shown next to an answer. */
export function sourceTone(source: AssistantSource): "accent" | "positive" | "warning" | "neutral" {
  switch (source) {
    case "ledger":
      return "positive";
    case "plan":
      return "accent";
    case "estimate":
      return "warning";
    case "assistant":
    default:
      return "neutral";
  }
}

/** Short human hint for a metric change percentage. */
export function changeHint(changePct: number | null): string {
  if (changePct === null) return "";
  if (changePct === 0) return "unchanged";
  return `${changePct > 0 ? "up" : "down"} ${Math.abs(changePct).toFixed(1)}%`;
}