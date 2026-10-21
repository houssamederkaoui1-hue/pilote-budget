/**
 * Pure data types + mappers for the READ-ONLY Firestore layer.
 *
 * Shapes mirror exactly what `firebase/tools/import-sqlite-to-firestore.mjs`
 * writes (integer cents, camelCase), which is the transport contract owned by
 * the operator import tool. No business writes happen here (Phase 1).
 *
 * This module must NOT import the firebase SDK so it stays unit-testable.
 */

export type AccountType =
  | "bank"
  | "checking"
  | "savings"
  | "cash"
  | "credit_card"
  | "debit_card"
  | "investment"
  | "loan"
  | "other";

export type FTransactionKind = "income" | "expense" | "transfer";
export type FTransactionStatus =
  | "pending"
  | "cleared"
  | "reconciled"
  | "void"
  | "completed"
  | "cancelled";

export interface FCategory {
  id: string;
  name: string;
  type: "income" | "expense";
  active: boolean;
  parentId: string | null;
  description: string | null;
}

export interface FAccount {
  id: string;
  name: string;
  type: AccountType;
  openingBalanceCents: number;
  currentBalanceCents: number;
  currency: string;
  active: boolean;
  description: string | null;
}

export interface FTransaction {
  id: string;
  accountId: string;
  categoryId: string | null;
  type: FTransactionKind;
  amountCents: number;
  date: string;
  description: string;
  status: FTransactionStatus;
  notes: string | null;
  imported: boolean;
}

export type FTransferStatus = "pending" | "completed" | "cancelled";

export interface FTransfer {
  id: string;
  sourceAccountId: string;
  destinationAccountId: string;
  amountCents: number;
  date: string;
  description: string;
  status: FTransferStatus;
  notes: string | null;
  imported: boolean;
}

export interface FProfile {
  currency: string;
  monthStartDay: number;
  timezone: string;
  preferences: Record<string, unknown>;
}

/** Money is stored as integer cents; convert for display. */
export function centsToNumber(cents: number): number {
  return typeof cents === "number" ? cents / 100 : 0;
}

export function bool(value: unknown): boolean {
  return typeof value === "boolean" ? value : false;
}

export function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function optStr(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function int(value: unknown): number {
  return typeof value === "number" ? value : 0;
}

export function mapCategory(id: string, raw: Record<string, unknown>): FCategory {
  return {
    id,
    name: str(raw.name),
    type: raw.type === "income" ? "income" : "expense",
    active: bool(raw.active),
    parentId: optStr(raw.parentId),
    description: optStr(raw.description),
  };
}

export function mapAccount(id: string, raw: Record<string, unknown>): FAccount {
  return {
    id,
    name: str(raw.name),
    type: raw.type as AccountType,
    openingBalanceCents: int(raw.openingBalanceCents),
    currentBalanceCents: int(raw.currentBalanceCents),
    currency: str(raw.currency),
    active: bool(raw.active),
    description: optStr(raw.description),
  };
}

export function mapTransaction(id: string, raw: Record<string, unknown>): FTransaction {
  return {
    id,
    accountId: str(raw.accountId),
    categoryId: optStr(raw.categoryId),
    type: raw.type as FTransactionKind,
    amountCents: int(raw.amountCents),
    date: str(raw.date),
    description: str(raw.description),
    status: raw.status as FTransactionStatus,
    notes: optStr(raw.notes),
    imported: bool(raw.imported),
  };
}

export function mapTransfer(id: string, raw: Record<string, unknown>): FTransfer {
  return {
    id,
    sourceAccountId: str(raw.sourceAccountId),
    destinationAccountId: str(raw.destinationAccountId),
    amountCents: int(raw.amountCents),
    date: str(raw.date),
    description: str(raw.description),
    status: raw.status as FTransferStatus,
    notes: optStr(raw.notes),
    imported: bool(raw.imported),
  };
}

/* ------------------------------------------------------------------ */
/*  Derived balances (read-only)                                       */
/* ------------------------------------------------------------------ */

/**
 * Posted/included statuses, mirroring
 * ``BalanceService.POSTED_TRANSACTION_STATUSES`` / ``POSTED_TRANSFER_STATUSES``
 * in `backend/app/services/balance_service.py`. Void transactions and
 * cancelled transfers are intentionally excluded.
 */
export const POSTED_TRANSACTION_STATUSES: ReadonlySet<FTransactionStatus> = new Set([
  "pending",
  "cleared",
  "reconciled",
]);

export const POSTED_TRANSFER_STATUSES: ReadonlySet<FTransferStatus> = new Set([
  "pending",
  "completed",
]);

/**
 * Pure recomputation of every account balance, matching BalanceService exactly:
 *
 *   opening
 *     + Σ income  (posted)  - Σ expense (posted)   for the account's transactions
 *     + Σ incoming posted transfers - Σ outgoing posted transfers
 *
 * Money is integer cents so this is exact integer arithmetic (the backend uses
 * floats + ``round(x, 2)``; cents are equivalent for all values the importer
 * produces). Accounts absent from ``accounts`` are ignored, matching the
 * backend which only reports balances for accounts it loaded. Like the backend,
 * a transaction/transfer that references an unknown account has no effect.
 */
export function deriveAccountBalances(
  accounts: FAccount[],
  transactions: FTransaction[],
  transfers: FTransfer[],
): Map<string, number> {
  const balances = new Map<string, number>();
  for (const account of accounts) {
    balances.set(account.id, account.openingBalanceCents);
  }

  for (const tx of transactions) {
    if (!POSTED_TRANSACTION_STATUSES.has(tx.status)) continue;
    if (!balances.has(tx.accountId)) continue;
    const delta =
      tx.type === "income"
        ? tx.amountCents
        : tx.type === "expense"
          ? -tx.amountCents
          : 0;
    balances.set(tx.accountId, (balances.get(tx.accountId) ?? 0) + delta);
  }

  for (const transfer of transfers) {
    if (!POSTED_TRANSFER_STATUSES.has(transfer.status)) continue;
    if (balances.has(transfer.sourceAccountId)) {
      balances.set(
        transfer.sourceAccountId,
        (balances.get(transfer.sourceAccountId) ?? 0) - transfer.amountCents,
      );
    }
    if (balances.has(transfer.destinationAccountId)) {
      balances.set(
        transfer.destinationAccountId,
        (balances.get(transfer.destinationAccountId) ?? 0) + transfer.amountCents,
      );
    }
  }

  return balances;
}

/** Minimal per-collection state needed to decide whether a balance is trustworthy. */
export interface ReadinessLike {
  loading: boolean;
  error: ReadError | null;
  offline: boolean;
}

export type BalancesReadiness =
  | { status: "loading" }
  | { status: "unavailable"; reason: string }
  | { status: "ready"; cached: boolean };

/**
 * A derived balance is only authoritative when *all* contributing reads have
 * completed without error. If any collection is still loading or failed, we
 * must not present a partial sum (e.g. accounts loaded but transfers failed) as
 * final. Cached (offline) snapshots are complete but may be stale, so they are
 * labelled rather than treated as live.
 */
export function balancesReadiness(states: ReadinessLike[]): BalancesReadiness {
  if (states.length === 0) return { status: "loading" };
  if (states.some((state) => state.loading)) return { status: "loading" };
  const failed = states.find((state) => state.error);
  if (failed && failed.error) {
    return { status: "unavailable", reason: failed.error.message };
  }
  return { status: "ready", cached: states.some((state) => state.offline) };
}

export type ReadErrorKind = "permission-denied" | "offline" | "unknown";

export interface ReadError {
  kind: ReadErrorKind;
  message: string;
}

function errorCode(error: unknown): string {
  if (error && typeof error === "object" && "code" in error) {
    return String((error as { code: unknown }).code ?? "");
  }
  return "";
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error ?? "Unknown error");
}

/** Map a Firestore/offline failure into a small set of actionable states. */
export function classifyReadError(error: unknown): ReadError {
  const code = errorCode(error);
  if (code === "permission-denied") {
    return { kind: "permission-denied", message: errorMessage(error) };
  }
  if (
    code === "unavailable" ||
    code === "network-request-failed" ||
    code === "unauthenticated" ||
    /network|offline|unavailable/i.test(errorMessage(error))
  ) {
    return { kind: "offline", message: errorMessage(error) };
  }
  return { kind: "unknown", message: errorMessage(error) };
}