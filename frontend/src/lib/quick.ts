/** Pure helpers for Quick Add suggestions + duplicate triage. */

import type {
  CategorySuggestion,
  DuplicateMatch,
  QuickCaptureResponse,
  SuggestionConfidence,
} from "../types/api";

const CONFIDENCE_RANK: Record<SuggestionConfidence, number> = {
  exact: 0,
  similar: 1,
  popular: 2,
};

/** Compares by confidence tier then by server score (best first). */
export function bestSuggestions(suggestions: CategorySuggestion[]): CategorySuggestion[] {
  return [...suggestions].sort(
    (left, right) =>
      (CONFIDENCE_RANK[left.confidence] ?? 9) - (CONFIDENCE_RANK[right.confidence] ?? 9) ||
      (right.score ?? 0) - (left.score ?? 0),
  );
}

/** The single most likely category, or null when nothing is usable. */
export function topSuggestion(suggestions: CategorySuggestion[]): CategorySuggestion | null {
  return bestSuggestions(suggestions)[0] ?? null;
}

export type DuplicateTone = "none" | "near" | "same_day";

/** How strongly a set of matches suggests a re-entry. */
export function duplicateTone(duplicates: DuplicateMatch[]): DuplicateTone {
  if (duplicates.some((match) => match.same_day)) return "same_day";
  if (duplicates.length > 0) return "near";
  return "none";
}

export function duplicateToneLabel(tone: DuplicateTone): string {
  switch (tone) {
    case "same_day":
      return "Looks like a duplicate";
    case "near":
      return "Possible duplicate nearby";
    default:
      return "No duplicates found";
  }
}

/** Build the create payload from a capture, honouring user overrides. */
export function captureToCreate(
  capture: QuickCaptureResponse,
  overrides: Partial<{
    amount: number;
    date: string;
    accountId: number | null;
    categoryId: number | null;
    description: string;
    rejectDuplicate: boolean;
  }> = {},
) {
  return {
    type: capture.type,
    amount: overrides.amount ?? capture.amount,
    description: overrides.description ?? capture.description,
    date: overrides.date ?? capture.date,
    account_id: overrides.accountId ?? capture.account_id,
    category_id: overrides.categoryId ?? capture.category_id,
    reject_duplicate: overrides.rejectDuplicate ?? false,
  };
}