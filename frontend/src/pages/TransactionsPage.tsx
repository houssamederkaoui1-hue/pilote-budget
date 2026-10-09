import { useMemo, useState } from "react";

import { ImportWizard } from "../components/import/ImportWizard";
import { ChevronLeftIcon, ChevronRightIcon, DownloadIcon, PencilIcon, PlusIcon, SearchIcon, TrashIcon, UploadIcon, WalletIcon } from "../components/icons";
import { TransactionForm } from "../components/transactions/TransactionForm";
import { Button } from "../components/ui/Button";
import { Card, StatCard } from "../components/ui/Card";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { useApi } from "../hooks/useApi";
import { errorMessage } from "../hooks/useMutation";
import { apiDelete, apiUrl } from "../lib/api";
import { formatCurrency, formatDate } from "../lib/format";
import type { Account, Category, Summary, TransactionList, TransactionRow } from "../types/api";
import styles from "./TransactionsPage.module.css";

const PAGE_SIZE = 25;

function typeLabel(type: TransactionRow["type"]): string {
  return type[0].toUpperCase() + type.slice(1);
}

export function TransactionsPage() {
  const accounts = useApi<Account[]>("/accounts");
  const categories = useApi<Category[]>("/categories");
  const activeAccounts = useMemo(() => accounts.data?.filter((a) => a.active) ?? [], [accounts.data]);
  const initialAccountId = activeAccounts[0]?.id;

  const [q, setQ] = useState("");
  const [committedQ, setCommittedQ] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [accountId, setAccountId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [type, setType] = useState<"income" | "expense" | "transfer" | "">("");
  const [offset, setOffset] = useState(0);

  const [showQuick, setShowQuick] = useState(false);
  const [showFull, setShowFull] = useState(false);
  const [editing, setEditing] = useState<TransactionRow | null>(null);
  const [showImport, setShowImport] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const resetOffset = () => setOffset(0);

  const listParams = useMemo(
    () => ({
      q: committedQ,
      date_from: from,
      date_to: to,
      account_id: accountId,
      category_id: categoryId,
      type,
    }),
    [committedQ, from, to, accountId, categoryId, type],
  );

  const listPath = useMemo(() => {
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(offset),
    });
    for (const [key, value] of Object.entries(listParams)) {
      if (value !== undefined && value !== "") params.set(key, value);
    }
    return `/transactions?${params.toString()}`;
  }, [offset, listParams]);

  const transactions = useApi<TransactionList>(listPath);
  const summaryPath = useMemo(() => {
    const params = new URLSearchParams();
    if (from) params.set("date_from", from);
    if (to) params.set("date_to", to);
    return `/transactions/summary${params.toString() ? `?${params.toString()}` : ""}`;
  }, [from, to]);
  const summary = useApi<Summary>(summaryPath);

  const currency = activeAccounts[0]?.currency ?? "EUR";
  const rows = transactions.data?.items ?? [];
  const total = transactions.data?.total ?? 0;

  const applyFilters = () => {
    setCommittedQ(q.trim());
    resetOffset();
  };

  const clearFilters = () => {
    setQ("");
    setCommittedQ("");
    setFrom("");
    setTo("");
    setAccountId("");
    setCategoryId("");
    setType("");
    resetOffset();
  };

  const hasActiveFilters = Boolean(committedQ || from || to || accountId || categoryId || type);

  const refresh = () => {
    transactions.reload();
    summary.reload();
  };

  const runDelete = async (row: TransactionRow) => {
    if (!window.confirm(`Delete this ${row.entity}? Balances will be recalculated.`)) return;
    setDeletingId(row.id);
    setDeleteError(null);
    try {
      await apiDelete(row.entity === "transfer" ? `/transfers/${row.id}` : `/transactions/${row.id}`);
      refresh();
    } catch (err) {
      setDeleteError(errorMessage(err));
    } finally {
      setDeletingId(null);
    }
  };

  const onImported = () => {
    transactions.reload();
    summary.reload();
  };

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-header__eyebrow">Overview</div>
          <h1>Transactions</h1>
          <p className="page-header__subtitle">
            Every income, expense and transfer, in one place. Voided and cancelled rows are excluded.
          </p>
        </div>
        <div className={styles.headerActions}>
          <Button variant="ghost" onClick={() => setShowImport(true)}>
            <UploadIcon size={15} />
            Import CSV
          </Button>
          <a className={styles.exportLink} href={apiUrl("/transactions/export.csv", listParams)} download>
            <DownloadIcon size={15} />
            Export
          </a>
          <Button onClick={() => setShowQuick(true)} disabled={activeAccounts.length === 0}>
            <PlusIcon size={15} />
            Quick entry
          </Button>
          <Button variant="subtle" onClick={() => setShowFull(true)} disabled={activeAccounts.length === 0}>
            New…
          </Button>
        </div>
      </div>

      <div className={styles.statRow}>
        <StatCard label="Income" value={formatCurrency(summary.data?.income ?? null, currency)} hint="In the selected period" />
        <StatCard label="Expenses" value={formatCurrency(summary.data?.expense ?? null, currency)} hint="In the selected period" />
        <StatCard label="Net" value={formatCurrency(summary.data?.net ?? null, currency)} tone={summary.data && summary.data.net < 0 ? "negative" : "positive"} />
        <StatCard label="Transfers" value={formatCurrency(summary.data?.transfer_volume ?? null, currency)} hint="Moved between accounts" />
      </div>

      <Card title="Ledger" subtitle={`${total} row${total === 1 ? "" : "s"}`}>
        <div className="toolbar">
          <input
            className="toolbar-input"
            placeholder="Search description, payee, reference…"
            value={q}
            onChange={(event) => setQ(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") applyFilters();
            }}
          />
          <button type="button" className="icon-button" title="Search" onClick={applyFilters}>
            <SearchIcon size={15} />
          </button>
          <input
            className="toolbar-input"
            type="date"
            value={from}
            title="From date"
            onChange={(event) => {
              setFrom(event.target.value);
              resetOffset();
            }}
          />
          <input
            className="toolbar-input"
            type="date"
            value={to}
            title="To date"
            onChange={(event) => {
              setTo(event.target.value);
              resetOffset();
            }}
          />
          <select
            className="toolbar-input"
            value={accountId}
            title="Account"
            onChange={(event) => {
              setAccountId(event.target.value);
              resetOffset();
            }}
          >
            <option value="">All accounts</option>
            {activeAccounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </select>
          <select
            className="toolbar-input"
            value={type}
            title="Type"
            onChange={(event) => {
              setType(event.target.value as typeof type);
              resetOffset();
            }}
          >
            <option value="">All types</option>
            <option value="income">Income</option>
            <option value="expense">Expense</option>
            <option value="transfer">Transfers</option>
          </select>
          <select
            className="toolbar-input"
            value={categoryId}
            title="Category"
            onChange={(event) => {
              setCategoryId(event.target.value);
              resetOffset();
            }}
          >
            <option value="">All categories</option>
            {(categories.data ?? []).map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>
          <Button
            variant="subtle"
            size="sm"
            disabled={!hasActiveFilters}
            onClick={clearFilters}
          >
            Clear filters
          </Button>
        </div>

        {transactions.loading && <LoadingState label="Loading transactions…" />}
        {!transactions.loading && transactions.error && (
          <ErrorState message={transactions.error} onRetry={transactions.reload} />
        )}
        {!transactions.loading && !transactions.error && activeAccounts.length === 0 && (
          <EmptyState
            icon={<WalletIcon size={20} />}
            title="Add an account first"
            description="Transactions need a home. Create an account, then come back to add entries."
          />
        )}
        {!transactions.loading && !transactions.error && activeAccounts.length > 0 && rows.length === 0 && (
          <EmptyState
            icon={<SearchIcon size={20} />}
            title={hasActiveFilters ? "No matching transactions" : "No transactions yet"}
            description={
              hasActiveFilters
                ? "Try widening the filters or clearing them."
                : "Use Quick entry for a fast add, or Import CSV to pull a bank export."
            }
            action={
              !hasActiveFilters ? (
                <Button size="sm" onClick={() => setShowQuick(true)}>
                  <PlusIcon size={14} />
                  Quick entry
                </Button>
              ) : undefined
            }
          />
        )}

        {deleteError && (
          <div className={styles.inlineError} role="alert">
            {deleteError}
          </div>
        )}

        {rows.length > 0 && (
          <>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Description</th>
                  <th>Account</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th className="amount-cell">Amount</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const income = row.type === "income";
                  const expense = row.type === "expense";
                  return (
                    <tr key={`${row.entity}-${row.id}`}>
                      <td className="muted-label">{formatDate(row.date)}</td>
                      <td>
                        <div className={styles.description}>
                          {row.description || <span className="muted-label">Untitled</span>}
                          {row.category_name && (
                            <span
                              className={`chip ${income ? "chip-income" : expense ? "chip-expense" : "chip-neutral"}`}
                            >
                              {row.category_name}
                            </span>
                          )}
                        </div>
                        {row.notes && <div className="muted-label">{row.notes}</div>}
                      </td>
                      <td>
                        <div className={styles.accountCell}>
                          <span>{row.account_name}</span>
                          {row.entity === "transfer" && row.destination_account_name && (
                            <span className={styles.transferArrow}>→ {row.destination_account_name}</span>
                          )}
                        </div>
                      </td>
                      <td>
                        <span
                          className={`chip ${
                            income ? "chip-income" : expense ? "chip-expense" : "chip-transfer"
                          }`}
                        >
                          {typeLabel(row.type)}
                        </span>
                      </td>
                      <td>
                        <span className={`chip ${row.status === "pending" ? "chip-warning" : "chip-neutral"}`}>
                          {row.status}
                        </span>
                      </td>
                      <td
                        className={`amount-cell ${
                          expense ? "negative" : income ? "positive" : "num"
                        }`}
                      >
                        {expense
                          ? `−${formatCurrency(row.amount, currency)}`
                          : income
                            ? `+${formatCurrency(row.amount, currency)}`
                            : formatCurrency(row.amount, currency)}
                      </td>
                      <td>
                        <div className="row-actions">
                          <button
                            type="button"
                            className="icon-button"
                            title="Edit"
                            onClick={() => setEditing(row)}
                          >
                            <PencilIcon size={15} />
                          </button>
                          <button
                            type="button"
                            className="icon-button danger"
                            title="Delete"
                            disabled={deletingId === row.id}
                            onClick={() => runDelete(row)}
                          >
                            <TrashIcon size={15} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="pagination">
              <button
                type="button"
                className="icon-button"
                title="Previous page"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                <ChevronLeftIcon size={15} />
              </button>
              <span>
                {total === 0 ? 0 : offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
              </span>
              <button
                type="button"
                className="icon-button"
                title="Next page"
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                <ChevronRightIcon size={15} />
              </button>
            </div>
          </>
        )}
      </Card>

      {showQuick && (
        <TransactionForm
          accounts={activeAccounts}
          categories={categories.data ?? []}
          quick
          defaultAccountId={initialAccountId}
          onSaved={() => {
            setShowQuick(false);
            refresh();
          }}
          onClose={() => setShowQuick(false)}
        />
      )}
      {showFull && (
        <TransactionForm
          accounts={activeAccounts}
          categories={categories.data ?? []}
          defaultAccountId={initialAccountId}
          onSaved={() => {
            setShowFull(false);
            refresh();
          }}
          onClose={() => setShowFull(false)}
        />
      )}
      {editing && (
        <TransactionForm
          accounts={activeAccounts}
          categories={categories.data ?? []}
          initial={editing}
          onSaved={() => {
            setEditing(null);
            refresh();
          }}
          onClose={() => setEditing(null)}
        />
      )}
      {showImport && (
        <ImportWizard
          accounts={activeAccounts}
          onImported={onImported}
          onClose={() => setShowImport(false)}
        />
      )}
    </>
  );
}