import { describe, expect, it } from "vitest";

import {
  balancesReadiness,
  deriveAccountBalances,
  type BalancesReadiness,
  type FAccount,
  type FTransaction,
  type FTransactionKind,
  type FTransactionStatus,
  type FTransfer,
  type FTransferStatus,
  type ReadError,
} from "./model";

/* Factories mirror the shapes written by the operator import tool. The
 * `currentBalanceCents`/imported snapshot values are deliberately bogus to
 * prove the derivation never reads them. */

function account(id: string, openingBalanceCents: number): FAccount {
  return {
    id,
    name: id,
    type: "bank",
    openingBalanceCents,
    currentBalanceCents: 999999,
    currency: "EUR",
    active: true,
    description: null,
  };
}

function tx(
  id: string,
  accountId: string,
  type: FTransactionKind,
  amountCents: number,
  status: FTransactionStatus,
): FTransaction {
  return {
    id,
    accountId,
    categoryId: null,
    type,
    amountCents,
    date: "2026-01-01",
    description: "",
    status,
    notes: null,
    imported: true,
  };
}

function transfer(
  id: string,
  sourceAccountId: string,
  destinationAccountId: string,
  amountCents: number,
  status: FTransferStatus,
): FTransfer {
  return {
    id,
    sourceAccountId,
    destinationAccountId,
    amountCents,
    date: "2026-01-01",
    description: "",
    status,
    notes: null,
    imported: true,
  };
}

describe("deriveAccountBalances — matches BalanceService (backend)", () => {
  it("starts from the opening balance and ignores the imported snapshot", () => {
    const balances = deriveAccountBalances([account("a1", 100000)], [], []);
    expect(balances.get("a1")).toBe(100000);
  });

  it("adds posted income and subtracts posted expenses", () => {
    const balances = deriveAccountBalances(
      [account("a1", 0)],
      [tx("t1", "a1", "income", 5000, "cleared"), tx("t2", "a1", "expense", 2000, "cleared")],
      [],
    );
    expect(balances.get("a1")).toBe(3000);
  });

  it("counts every posted transaction status (pending / cleared / reconciled)", () => {
    const balances = deriveAccountBalances(
      [account("a1", 0)],
      [
        tx("t1", "a1", "income", 1000, "pending"),
        tx("t2", "a1", "income", 2000, "cleared"),
        tx("t3", "a1", "income", 3000, "reconciled"),
      ],
      [],
    );
    expect(balances.get("a1")).toBe(6000);
  });

  it("excludes void transactions", () => {
    const balances = deriveAccountBalances(
      [account("a1", 1000)],
      [tx("t1", "a1", "income", 9999, "void"), tx("t2", "a1", "expense", 5000, "void")],
      [],
    );
    expect(balances.get("a1")).toBe(1000);
  });

  it("ignores transactions whose account is unknown (backend behaviour)", () => {
    const balances = deriveAccountBalances(
      [account("a1", 0)],
      [tx("t1", "ghost", "income", 1234, "cleared")],
      [],
    );
    expect(balances.has("ghost")).toBe(false);
    expect(balances.get("a1")).toBe(0);
  });

  it("treats a transaction typed 'transfer' as zero (transfers are their own table)", () => {
    const balances = deriveAccountBalances(
      [account("a1", 0)],
      [tx("t1", "a1", "transfer", 5000, "cleared")],
      [],
    );
    expect(balances.get("a1")).toBe(0);
  });

  it("subtracts outgoing and adds incoming posted transfers", () => {
    const balances = deriveAccountBalances(
      [account("src", 10000), account("dst", 0)],
      [],
      [transfer("x1", "src", "dst", 3000, "completed")],
    );
    expect(balances.get("src")).toBe(7000);
    expect(balances.get("dst")).toBe(3000);
  });

  it("counts pending and completed transfers but excludes cancelled", () => {
    const balances = deriveAccountBalances(
      [account("src", 0), account("dst", 0)],
      [],
      [
        transfer("x1", "src", "dst", 1000, "pending"),
        transfer("x2", "src", "dst", 2000, "completed"),
        transfer("x3", "src", "dst", 4000, "cancelled"),
      ],
    );
    expect(balances.get("src")).toBe(-3000);
    expect(balances.get("dst")).toBe(3000);
  });

  it("handles a zero balance when nothing posted", () => {
    const balances = deriveAccountBalances([account("a1", 0)], [], []);
    expect(balances.get("a1")).toBe(0);
  });

  it("allows negative balances (expenses/outgoing exceed funds)", () => {
    const balances = deriveAccountBalances(
      [account("a1", 1000), account("a2", 0)],
      [tx("t1", "a1", "expense", 2500, "cleared")],
      [transfer("x1", "a1", "a2", 1000, "completed")],
    );
    expect(balances.get("a1")).toBe(-2500);
    expect(balances.get("a2")).toBe(1000);
  });

  it("computes multiple accounts independently and in aggregate", () => {
    const accounts = [account("a1", 100000), account("a2", 0), account("a3", 0)];
    const transactions = [
      tx("t1", "a1", "income", 5000, "cleared"),
      tx("t2", "a1", "expense", 2000, "reconciled"),
      tx("t3", "a1", "income", 9999, "void"),
      tx("t4", "a1", "expense", 1000, "pending"),
    ];
    const transfers = [
      transfer("x1", "a1", "a2", 3000, "completed"),
      transfer("x2", "a2", "a1", 4000, "pending"),
      transfer("x3", "a1", "a2", 7000, "cancelled"),
    ];

    const balances = deriveAccountBalances(accounts, transactions, transfers);

    // a1 = 100000 + 5000 - 2000 - 1000 - 3000 + 4000 = 103000
    expect(balances.get("a1")).toBe(103000);
    // a2 = 0 + 3000 - 4000 = -1000
    expect(balances.get("a2")).toBe(-1000);
    // a3 = 0 (untouched)
    expect(balances.get("a3")).toBe(0);

    const total = [...balances.values()].reduce((sum, value) => sum + value, 0);
    expect(total).toBe(102000);
  });

  it("reproduces the legacy backend formula on a synthetic fixture", () => {
    // Independent restatement of BalanceService.compute_all() (in cents).
    const accounts: FAccount[] = [account("checking", 500000), account("savings", -20000)];
    const transactions: FTransaction[] = [
      tx("i1", "checking", "income", 250000, "cleared"),
      tx("e1", "checking", "expense", 130000, "reconciled"),
      tx("e2", "checking", "expense", 45000, "pending"),
      tx("void1", "checking", "income", 800000, "void"),
      tx("i2", "savings", "income", 10000, "pending"),
    ];
    const transfers: FTransfer[] = [
      transfer("tr1", "checking", "savings", 100000, "completed"),
      transfer("tr2", "checking", "savings", 25000, "pending"),
      transfer("tr3", "savings", "checking", 99999, "cancelled"),
    ];

    const expected = new Map<string, number>([
      ["checking", 500000 + 250000 - 130000 - 45000 - 100000 - 25000],
      ["savings", -20000 + 10000 + 100000 + 25000],
    ]);

    expect(deriveAccountBalances(accounts, transactions, transfers)).toEqual(expected);
  });
});

function readiness(over: {
  loading?: boolean;
  error?: ReadError | null;
  offline?: boolean;
}) {
  return {
    loading: over.loading ?? false,
    error: over.error ?? null,
    offline: over.offline ?? false,
  };
}

describe("balancesReadiness — never presents a partial sum as authoritative", () => {
  it("is loading while any contributing read is loading", () => {
    const result = balancesReadiness([
      readiness({ loading: false }),
      readiness({ loading: true }),
      readiness({ loading: false }),
    ]);
    expect(result.status).toBe("loading");
  });

  it("is unavailable when any read errored, with the reason", () => {
    const result = balancesReadiness([
      readiness({}),
      readiness({ error: { kind: "permission-denied", message: "nope" } }),
    ]);
    expect(result.status).toBe("unavailable");
    if (result.status === "unavailable") expect(result.reason).toBe("nope");
  });

  it("is ready and not cached when all reads are live and clean", () => {
    const result = balancesReadiness([readiness({}), readiness({}), readiness({})]);
    expect(result).toEqual<BalancesReadiness>({ status: "ready", cached: false });
  });

  it("is ready but flagged cached when a snapshot came from cache", () => {
    const result = balancesReadiness([readiness({}), readiness({ offline: true })]);
    expect(result).toEqual<BalancesReadiness>({ status: "ready", cached: true });
  });

  it("loading takes precedence over an unrelated error", () => {
    const result = balancesReadiness([
      readiness({ error: { kind: "offline", message: "x" } }),
      readiness({ loading: true }),
    ]);
    expect(result.status).toBe("loading");
  });
});
