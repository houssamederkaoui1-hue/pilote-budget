import { useState } from "react";

import { ArchiveIcon, PencilIcon, PlusIcon, TrashIcon, WalletIcon } from "../components/icons";
import { Button } from "../components/ui/Button";
import { Card, StatCard } from "../components/ui/Card";
import { Field, Input, Select, TextArea } from "../components/ui/Form";
import { Modal } from "../components/ui/Modal";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { useApi } from "../hooks/useApi";
import { useMutation, errorMessage } from "../hooks/useMutation";
import { apiDelete, apiPatch, apiPost } from "../lib/api";
import { formatCurrency } from "../lib/format";
import type { Account, AccountType } from "../types/api";
import styles from "./AccountsPage.module.css";

const ACCOUNT_TYPES: { value: AccountType; label: string }[] = [
  { value: "bank", label: "Bank account" },
  { value: "checking", label: "Checking" },
  { value: "savings", label: "Savings" },
  { value: "cash", label: "Cash" },
  { value: "credit_card", label: "Credit card" },
  { value: "debit_card", label: "Debit card" },
  { value: "investment", label: "Investment" },
  { value: "loan", label: "Loan" },
  { value: "other", label: "Other" },
];

function typeLabel(type: AccountType): string {
  return ACCOUNT_TYPES.find((entry) => entry.value === type)?.label ?? type;
}

export function AccountsPage() {
  const accounts = useApi<Account[]>("/accounts");
  const [showArchived, setShowArchived] = useState(false);
  const [editing, setEditing] = useState<Account | null>(null);
  const [creating, setCreating] = useState(false);

  const currency = "EUR";

  const stopped = accounts.data?.filter((account) => !account.active) ?? [];
  const activeBalance =
    accounts.data?.filter((account) => account.active).reduce((sum, account) => sum + account.current_balance, 0) ?? 0;

  const visible = showArchived ? accounts.data : accounts.data?.filter((account) => account.active);

  const archive = useMutation((account: Account) =>
    apiPatch<Account>(`/accounts/${account.id}`, { active: false }),
  );
  const activate = useMutation((account: Account) =>
    apiPatch<Account>(`/accounts/${account.id}`, { active: true }),
  );
  const remove = useMutation((account: Account) => apiDelete(`/accounts/${account.id}`));

  const runToggle = async (account: Account) => {
    try {
      if (account.active) await archive.mutate(account);
      else await activate.mutate(account);
      accounts.reload();
    } catch {
      // error surfaced via mutation state
    }
  };

  const runDelete = async (account: Account) => {
    if (!window.confirm(`Delete "${account.name}"? Accounts with history are kept by archiving instead.`)) return;
    try {
      await remove.mutate(account);
      accounts.reload();
    } catch {
      // surfaced below
    }
  };

  const onSaved = () => {
    setCreating(false);
    setEditing(null);
    accounts.reload();
  };

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-header__eyebrow">Overview</div>
          <h1>Accounts</h1>
          <p className="page-header__subtitle">
            Bank, cash and credit accounts. Balances update automatically as transactions land.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <PlusIcon size={15} />
          Add account
        </Button>
      </div>

      <div className={styles.statRow}>
        <StatCard label="Total balance" value={formatCurrency(activeBalance, currency)} hint="Across active accounts" icon={<WalletIcon size={15} />} />
        <StatCard label="Active accounts" value={String(accounts.data?.filter((a) => a.active).length ?? "—")} hint={`${stopped.length} archived`} />
      </div>

      {(archive.error || activate.error || remove.error) && (
        <div className={styles.inlineError} role="alert">
          {archive.error || activate.error || remove.error}
        </div>
      )}

      <Card
        title="Accounts"
        subtitle={showArchived ? "All accounts including archived" : "Active accounts"}
        action={
          <div className="tabs">
            <button type="button" className={!showArchived ? "active" : ""} onClick={() => setShowArchived(false)}>
              Active
            </button>
            <button type="button" className={showArchived ? "active" : ""} onClick={() => setShowArchived(true)}>
              All
            </button>
          </div>
        }
      >
        {accounts.loading && <LoadingState label="Loading accounts…" />}
        {!accounts.loading && accounts.error && (
          <ErrorState message={accounts.error} onRetry={accounts.reload} />
        )}
        {!accounts.loading && !accounts.error && visible && visible.length === 0 && (
          <EmptyState
            icon={<WalletIcon size={20} />}
            title={showArchived ? "No archived accounts" : "No accounts yet"}
            description="Add your first bank, cash or credit account to start tracking balances."
            action={
              <Button size="sm" onClick={() => setCreating(true)}>
                <PlusIcon size={14} />
                Add account
              </Button>
            }
          />
        )}
        {visible && visible.length > 0 && (
          <table className="data-table">
            <thead>
              <tr>
                <th>Account</th>
                <th>Type</th>
                <th className="amount-cell">Opening</th>
                <th className="amount-cell">Balance</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {visible.map((account) => (
                <tr key={account.id} className={!account.active ? styles.archivedRow : undefined}>
                  <td>
                    <div className={styles.accountName}>
                      {account.name}
                      {!account.active && <span className="chip chip-neutral">archived</span>}
                    </div>
                    {account.description && <div className="muted-label">{account.description}</div>}
                  </td>
                  <td>
                    <span className="chip chip-neutral">{typeLabel(account.type)}</span>
                  </td>
                  <td className="amount-cell muted-label num">{formatCurrency(account.opening_balance, currency)}</td>
                  <td className={`amount-cell num ${account.current_balance >= 0 ? "positive" : "negative"}`}>
                    {formatCurrency(account.current_balance, currency)}
                  </td>
                  <td>
                    <div className="row-actions">
                      <button
                        type="button"
                        className="icon-button"
                        title="Edit"
                        onClick={() => setEditing(account)}
                      >
                        <PencilIcon size={15} />
                      </button>
                      <button
                        type="button"
                        className="icon-button"
                        title={account.active ? "Archive" : "Restore"}
                        onClick={() => runToggle(account)}
                      >
                        <ArchiveIcon size={15} />
                      </button>
                      <button
                        type="button"
                        className="icon-button danger"
                        title="Delete"
                        onClick={() => runDelete(account)}
                      >
                        <TrashIcon size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {creating && <AccountFormModal onClose={() => setCreating(false)} onSaved={onSaved} />}
      {editing && (
        <AccountFormModal
          account={editing}
          onClose={() => setEditing(null)}
          onSaved={onSaved}
        />
      )}
    </>
  );
}

interface AccountFormProps {
  account?: Account;
  onClose: () => void;
  onSaved: () => void;
}

function AccountFormModal({ account, onClose, onSaved }: AccountFormProps) {
  const [name, setName] = useState(account?.name ?? "");
  const [type, setType] = useState<AccountType>(account?.type ?? "bank");
  const [openingBalance, setOpeningBalance] = useState(
    account ? String(account.opening_balance) : "0",
  );
  const [currency, setCurrency] = useState(account?.currency ?? "EUR");
  const [description, setDescription] = useState(account?.description ?? "");
  const [active, setActive] = useState(account?.active ?? true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = () => {
    const payload = {
      name: name.trim(),
      type,
      opening_balance: Number(openingBalance) || 0,
      currency: currency.trim().toUpperCase() || null,
      description: description.trim() || null,
      active,
    };
    setPending(true);
    setError(null);
    const request = account
      ? apiPatch<Account>(`/accounts/${account.id}`, payload)
      : apiPost<Account>("/accounts", payload);
    request
      .then(() => onSaved())
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setPending(false));
  };

  return (
    <Modal
      title={account ? "Edit account" : "Add account"}
      subtitle="Opening balance seeds the running balance."
      onClose={onClose}
    >
      <Field label="Name" hint="required">
        <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Main checking" autoFocus />
      </Field>
      <Field label="Type">
        <Select value={type} onChange={(event) => setType(event.target.value as AccountType)}>
          {ACCOUNT_TYPES.map((entry) => (
            <option key={entry.value} value={entry.value}>
              {entry.label}
            </option>
          ))}
        </Select>
      </Field>
      <div className={styles.formRow}>
        <Field label="Opening balance">
          <Input value={openingBalance} onChange={(event) => setOpeningBalance(event.target.value)} type="number" step="0.01" inputMode="decimal" />
        </Field>
        <Field label="Currency">
          <Input value={currency} onChange={(event) => setCurrency(event.target.value)} placeholder="EUR" maxLength={3} />
        </Field>
      </div>
      <Field label="Description">
        <TextArea value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Optional notes about this account" />
      </Field>
      <label className={styles.checkboxRow}>
        <input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} />
        <span>Account is active</span>
      </label>

      <div className={styles.modalActions}>
        <Button variant="ghost" onClick={onClose} disabled={pending}>
          Cancel
        </Button>
        <Button onClick={submit} loading={pending} disabled={!name.trim()}>
          {account ? "Save changes" : "Add account"}
        </Button>
      </div>
      {error && (
        <div className={styles.modalError} role="alert">
          {error}
        </div>
      )}
    </Modal>
  );
}