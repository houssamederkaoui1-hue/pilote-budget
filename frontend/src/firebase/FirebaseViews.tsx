import type { ReactNode } from "react";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { formatCurrency } from "../lib/format";
import {
  useProfile,
  useAccounts,
  useCategories,
  useTransactions,
  useTransfers,
} from "./repo";
import {
  balancesReadiness,
  centsToNumber,
  deriveAccountBalances,
  type BalancesReadiness,
  type FAccount,
  type FCategory,
  type FTransaction,
  type ReadError,
} from "./model";
import styles from "./Firebase.module.css";

const POSTED_STATUSES = new Set(["pending", "cleared", "reconciled"]);

type AnyState = {
  docs: unknown[];
  loading: boolean;
  empty: boolean;
  offline: boolean;
  online: boolean;
  error: ReadError | null;
  retry: () => void;
};

/** Shared note explaining derived-balance provenance / degradation. */
function BalanceNote({ readiness }: { readiness: BalancesReadiness }) {
  if (readiness.status === "loading") {
    return <p className={styles.muted}>Derived balances: calculating…</p>;
  }
  if (readiness.status === "unavailable") {
    return (
      <p className={styles.muted}>
        Derived balances are hidden because not all ledger data could be read
        ({readiness.reason}). Showing a partial sum would be misleading.
      </p>
    );
  }
  if (readiness.cached) {
    return (
      <p className={styles.muted}>
        Derived balances are computed from offline cached data and may be out of
        date. Imported snapshots below are the values last written by the
        operator import.
      </p>
    );
  }
  return (
    <p className={styles.muted}>
      Derived balances are recomputed from opening balances, posted
      transactions and posted transfers. They are never written back to the
      imported account snapshots.
    </p>
  );
}

function ListShell({ state, emptyTitle, emptyDescription, children }: {
  state: AnyState;
  emptyTitle: string;
  emptyDescription: string;
  children: ReactNode;
}) {
  if (state.error && state.error.kind === "permission-denied") {
    return (
      <ErrorState
        title="Access denied by Firestore Security Rules"
        message={`${state.error.message} — check that you are signed in to Firebase and that your UID owns the data.`}
        onRetry={state.retry}
      />
    );
  }
  if (state.error && state.error.kind === "offline" && state.docs.length === 0) {
    return (
      <ErrorState
        title="Offline, nothing cached yet"
        message="This view has never synchronised. Go online once so Firestore can populate the local cache, then it will be available offline."
        onRetry={state.retry}
      />
    );
  }
  if (state.error && state.docs.length === 0) {
    return <ErrorState message={state.error.message} onRetry={state.retry} />;
  }
  if (state.loading) return <LoadingState label="Loading Firestore data…" />;
  if (state.empty) return <EmptyState title={emptyTitle} description={emptyDescription} />;
  return <>{children}</>;
}

/* ------------------------------------------------------------------ */
/*  Dashboard                                                          */
/* ------------------------------------------------------------------ */

export function DashboardPage() {
  const accounts = useAccounts();
  const categories = useCategories();
  const transactions = useTransactions();
  const transfers = useTransfers();
  const profile = useProfile();
  const currency = profile.currency;

  const readiness = balancesReadiness([accounts, transactions, transfers]);
  const derived =
    readiness.status === "ready"
      ? deriveAccountBalances(accounts.docs, transactions.docs, transfers.docs)
      : null;

  const posted = transactions.docs.filter((tx) => POSTED_STATUSES.has(tx.status));
  const incomeCents = posted
    .filter((tx) => tx.type === "income")
    .reduce((sum, tx) => sum + tx.amountCents, 0);
  const expenseCents = posted
    .filter((tx) => tx.type === "expense")
    .reduce((sum, tx) => sum + tx.amountCents, 0);
  const activeAccounts = accounts.docs.filter((account) => account.active);
  const importedBalanceCents = activeAccounts.reduce(
    (sum, account) => sum + account.currentBalanceCents,
    0,
  );
  const derivedBalanceCents = derived
    ? activeAccounts.reduce((sum, account) => sum + (derived.get(account.id) ?? 0), 0)
    : null;
  const derivedLoading = readiness.status === "loading";
  const loading =
    accounts.loading || transactions.loading || categories.loading || profile.loading;

  const recent = [...transactions.docs]
    .sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0))
    .slice(0, 6);

  return (
    <section>
      <h2 className={styles.sectionTitle}>
        {profile.loading ? "Loading profile…" : `Overview (${currency})`}
      </h2>
      <div className={styles.grid}>
        <Stat label="Active accounts" value={`${activeAccounts.length}`} loading={loading} />
        <Stat label="Categories" value={`${categories.docs.length}`} loading={loading} />
        <Stat label="Transactions" value={`${transactions.docs.length}`} loading={loading} />
        <Stat label="Posted income" value={formatCurrency(centsToNumber(incomeCents), currency)} positive={incomeCents >= 0} loading={loading} />
        <Stat label="Posted expenses" value={formatCurrency(centsToNumber(expenseCents), currency)} negative={expenseCents > 0} loading={loading} />
        <Stat
          label="Derived balance"
          value={
            derivedBalanceCents === null
              ? "—"
              : formatCurrency(centsToNumber(derivedBalanceCents), currency)
          }
          loading={derivedLoading}
        />
        <Stat
          label="Imported snapshot"
          value={formatCurrency(centsToNumber(importedBalanceCents), currency)}
          loading={loading}
        />
      </div>
      <BalanceNote readiness={readiness} />

      <h3 className={styles.sectionTitle}>Recent transactions</h3>
      {transactions.docs.length === 0 ? (
        <EmptyState
          title="No transactions yet"
          description="Import data with the operator tool, then it will appear here."
        />
      ) : (
        <div className={styles.list}>
          {recent.map((tx) => (
            <TransactionRow key={tx.id} tx={tx} accounts={accounts.docs} categories={categories.docs} currency={currency} />
          ))}
        </div>
      )}
    </section>
  );
}

function Stat({ label, value, positive, negative, loading }: { label: string; value: string; positive?: boolean; negative?: boolean; loading?: boolean }) {
  const cls = positive ? styles.statValuePositive : negative ? styles.statValueNegative : undefined;
  return (
    <div className={styles.statCard}>
      <div className={styles.statLabel}>{label}</div>
      <div className={`${styles.statValue} ${cls ?? ""}`}>{loading ? "…" : value}</div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Accounts                                                           */
/* ------------------------------------------------------------------ */

export function AccountsPage() {
  const accounts = useAccounts();
  const transactions = useTransactions();
  const transfers = useTransfers();
  const profile = useProfile();

  const readiness = balancesReadiness([accounts, transactions, transfers]);
  const derived =
    readiness.status === "ready"
      ? deriveAccountBalances(accounts.docs, transactions.docs, transfers.docs)
      : null;

  return (
    <section>
      <h2 className={styles.sectionTitle}>Accounts</h2>
      <BalanceNote readiness={readiness} />
      <ListShell
        state={accounts}
        emptyTitle="No accounts imported"
        emptyDescription="Accounts will appear here after the operator import tool runs."
      >
        <div className={styles.list}>
          {accounts.docs.map((account) => (
            <AccountRow
              key={account.id}
              account={account}
              derivedCents={derived ? derived.get(account.id) ?? 0 : null}
              readiness={readiness}
              currency={profile.currency}
            />
          ))}
        </div>
      </ListShell>
    </section>
  );
}

function AccountRow({ account, derivedCents, readiness, currency }: {
  account: FAccount;
  derivedCents: number | null;
  readiness: BalancesReadiness;
  currency: string;
}) {
  const accountCurrency = account.currency || currency;
  const imported = formatCurrency(centsToNumber(account.currentBalanceCents), accountCurrency);
  const derivedDisplay =
    derivedCents === null
      ? "—"
      : formatCurrency(centsToNumber(derivedCents), accountCurrency);
  const derivedLabel =
    readiness.status === "loading"
      ? "derived balance"
      : derivedCents === null
        ? "derived balance (unavailable)"
        : readiness.status === "ready" && readiness.cached
          ? "derived balance (cached)"
          : "derived balance";
  const differs = derivedCents !== null && derivedCents !== account.currentBalanceCents;

  return (
    <div className={styles.row}>
      <div className={styles.rowMain}>
        <div className={styles.rowTitle}>{account.name}</div>
        <div className={styles.rowMeta}>
          {account.type}
          {account.description ? ` · ${account.description}` : ""}
        </div>
      </div>
      <span className={`${styles.chip} ${account.active ? styles.chipActive : styles.chipInactive}`}>
        {account.active ? "active" : "inactive"}
      </span>
      <div className={styles.amountStack}>
        <span className={styles.rowAmount}>{derivedDisplay}</span>
        <span className={styles.amountLabel}>{derivedLabel}</span>
        <span className={`${styles.amountSnapshot} ${differs ? styles.amountSnapshotDiffers : ""}`}>
          imported snapshot {imported}
        </span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Categories                                                         */
/* ------------------------------------------------------------------ */

export function CategoriesPage() {
  const categories = useCategories();
  const income = categories.docs.filter((category) => category.type === "income");
  const expense = categories.docs.filter((category) => category.type === "expense");

  return (
    <section>
      <h2 className={styles.sectionTitle}>Categories</h2>
      <ListShell
        state={categories}
        emptyTitle="No categories imported"
        emptyDescription="Categories will appear here after the operator import tool runs."
      >
        <CategoryGroup title="Income" rows={income} all={categories.docs} />
        <CategoryGroup title="Expense" rows={expense} all={categories.docs} />
      </ListShell>
    </section>
  );
}

function CategoryGroup({ title, rows, all }: { title: string; rows: FCategory[]; all: FCategory[] }) {
  const nameById = new Map(all.map((category) => [category.id, category.name]));
  return (
    <>
      <h3 className={styles.sectionTitle}>{title}</h3>
      <div className={styles.list}>
        {rows.map((category) => (
          <div className={styles.row} key={category.id}>
            <div className={styles.rowMain}>
              <div className={styles.rowTitle}>{category.name}</div>
              <div className={styles.rowMeta}>
                {category.parentId ? `Parent: ${nameById.get(category.parentId) ?? category.parentId}` : "Top level"}
                {category.description ? ` · ${category.description}` : ""}
              </div>
            </div>
            <span className={`${styles.chip} ${category.active ? styles.chipActive : styles.chipInactive}`}>
              {category.active ? "active" : "inactive"}
            </span>
          </div>
        ))}
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Transactions                                                       */
/* ------------------------------------------------------------------ */

export function TransactionsPage() {
  const transactions = useTransactions();
  const accounts = useAccounts();
  const categories = useCategories();
  const currency = useProfile().currency;

  const sorted = [...transactions.docs].sort((a, b) =>
    a.date < b.date ? 1 : a.date > b.date ? -1 : 0,
  );

  return (
    <section>
      <h2 className={styles.sectionTitle}>Transactions</h2>
      <ListShell
        state={transactions}
        emptyTitle="No transactions imported"
        emptyDescription="Transactions will appear here after the operator import tool runs."
      >
        <div className={styles.list}>
          {sorted.map((tx) => (
            <TransactionRow key={tx.id} tx={tx} accounts={accounts.docs} categories={categories.docs} currency={currency} />
          ))}
        </div>
      </ListShell>
    </section>
  );
}

function TransactionRow({ tx, accounts, categories, currency }: {
  tx: FTransaction;
  accounts: FAccount[];
  categories: FCategory[];
  currency: string;
}) {
  const accountName = accounts.find((account) => account.id === tx.accountId)?.name;
  const categoryName = categories.find((category) => category.id === tx.categoryId)?.name;
  const isExpense = tx.type === "expense";
  const signed = isExpense ? -1 : 1;
  const amount = formatCurrency(centsToNumber(tx.amountCents) * signed, currency);

  return (
    <div className={styles.row}>
      <div className={styles.rowMain}>
        <div className={styles.rowTitle}>{tx.description || "Untitled"}</div>
        <div className={styles.rowMeta}>
          {tx.date}
          {accountName ? ` · ${accountName}` : ""}
          {categoryName ? ` · ${categoryName}` : ""}
        </div>
      </div>
      <span className={styles.chip}>{tx.status}</span>
      {tx.imported && <span className={`${styles.chip} ${styles.chipImported}`}>imported</span>}
      <span className={`${styles.rowAmount} ${isExpense ? styles.amountExpense : styles.amountIncome}`}>
        {amount}
      </span>
    </div>
  );
}