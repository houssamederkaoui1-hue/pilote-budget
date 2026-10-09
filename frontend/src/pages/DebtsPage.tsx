import { useState } from "react";

import { DebtsIcon, PencilIcon, PlusIcon, TrashIcon, WalletIcon } from "../components/icons";
import { Button } from "../components/ui/Button";
import { Badge, Card, StatCard } from "../components/ui/Card";
import { Field, FormError, Input, Select, TextArea } from "../components/ui/Form";
import { Modal } from "../components/ui/Modal";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { useApi } from "../hooks/useApi";
import { errorMessage, useMutation } from "../hooks/useMutation";
import { apiDelete, apiPatch, apiPost } from "../lib/api";
import { formatCurrency, formatDate } from "../lib/format";
import type { Account, Debt, DebtTotals } from "../types/api";
import styles from "./DebtsPage.module.css";

export function DebtsPage() {
  const debts = useApi<Debt[]>("/debts");
  const totals = useApi<DebtTotals>("/debts/totals");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Debt | null>(null);
  const currency = "EUR";

  const remove = useMutation((debt: Debt) => apiDelete(`/debts/${debt.id}`));

  const reload = () => {
    debts.reload();
    totals.reload();
  };

  const runDelete = async (debt: Debt) => {
    if (!window.confirm(`Delete debt "${debt.name}"?`)) return;
    try {
      await remove.mutate(debt);
      reload();
    } catch {
      // surfaced below
    }
  };

  const onSaved = () => {
    setCreating(false);
    setEditing(null);
    reload();
  };

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-header__eyebrow">Planning</div>
          <h1>Debts</h1>
          <p className="page-header__subtitle">
            Loans and card balances with minimums and upcoming due dates.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <PlusIcon size={15} />
          Add debt
        </Button>
      </div>

      <div className={styles.statRow}>
        <StatCard
          label="Total remaining"
          value={formatCurrency(totals.data?.total_remaining ?? 0, currency)}
          hint={`${totals.data?.active_debt_count ?? 0} active debts`}
          tone="negative"
          icon={<DebtsIcon size={15} />}
        />
        <StatCard
          label="Original"
          value={formatCurrency(totals.data?.total_original ?? 0, currency)}
          hint="Tracked original balances"
          icon={<WalletIcon size={15} />}
        />
        <StatCard
          label="Monthly minimums"
          value={formatCurrency(totals.data?.total_minimum_payment ?? 0, currency)}
          hint="Next payments required"
          icon={<WalletIcon size={15} />}
        />
      </div>

      {remove.error && (
        <div className={styles.inlineError} role="alert">
          {remove.error}
        </div>
      )}

      <div className={styles.grid}>
        <div className={styles.span7}>
          <Card title="Debts" subtitle="Tracked balances across active debts">
            {debts.loading && <LoadingState label="Loading debts…" />}
            {!debts.loading && debts.error && (
              <ErrorState message={debts.error} onRetry={debts.reload} />
            )}
            {!debts.loading && !debts.error && debts.data && debts.data.length === 0 && (
              <EmptyState
                icon={<DebtsIcon size={20} />}
                title="No debts tracked"
                description="Add a loan or credit balance to see it in your net worth."
                action={
                  <Button size="sm" onClick={() => setCreating(true)}>
                    <PlusIcon size={14} />
                    Add debt
                  </Button>
                }
              />
            )}
            {debts.data && debts.data.length > 0 && (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Debt</th>
                    <th className="amount-cell">Remaining</th>
                    <th className="amount-cell">Original</th>
                    <th className="amount-cell">Min / mo</th>
                    <th>Due</th>
                    <th aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {debts.data.map((debt) => (
                    <tr key={debt.id} className={debt.active ? undefined : styles.inactiveRow}>
                      <td>
                        <div className={styles.debtName}>
                          {debt.name}
                          {debt.creditor && <span className="chip chip-neutral">{debt.creditor}</span>}
                          {!debt.active && <Badge tone="neutral">Inactive</Badge>}
                        </div>
                        {debt.account_name && <div className="muted-label">{debt.account_name}</div>}
                      </td>
                      <td className={`amount-cell num ${debt.remaining_amount > 0 ? "negative" : ""}`}>
                        {formatCurrency(debt.remaining_amount, currency)}
                      </td>
                      <td className="amount-cell num muted-label">{formatCurrency(debt.original_amount, currency)}</td>
                      <td className="amount-cell num">
                        {debt.minimum_payment === null ? "—" : formatCurrency(debt.minimum_payment, currency)}
                      </td>
                      <td>
                        {debt.due_date ? (
                          <span className="secondary">{formatDate(debt.due_date)}</span>
                        ) : (
                          <span className="muted-label">—</span>
                        )}
                      </td>
                      <td>
                        <div className="row-actions">
                          <button type="button" className="icon-button" title="Edit" onClick={() => setEditing(debt)}>
                            <PencilIcon size={15} />
                          </button>
                          <button type="button" className="icon-button danger" title="Delete" onClick={() => runDelete(debt)}>
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
        </div>

        <div className={styles.span5}>
          <Card title="Upcoming due dates" subtitle="Next five payments across active debts">
            {totals.loading && <LoadingState label="Loading due dates…" />}
            {!totals.loading && totals.error && (
              <ErrorState message={totals.error} onRetry={totals.reload} />
            )}
            {totals.data && totals.data.upcoming_due_dates.length === 0 && (
              <EmptyState
                icon={<DebtsIcon size={20} />}
                title="No upcoming payments"
                description="Give a debt a due date to schedule its next payment here."
              />
            )}
            {totals.data && totals.data.upcoming_due_dates.length > 0 && (
              <div className={styles.dueList}>
                {totals.data.upcoming_due_dates.map((due) => (
                  <div key={due.debt_id} className={styles.dueRow}>
                    <div>
                      <div className={styles.dueName}>{due.name}</div>
                      <div className="muted-label">{formatDate(due.due_date)}</div>
                    </div>
                    <div className="amount-cell num">
                      {due.minimum_payment !== null
                        ? formatCurrency(due.minimum_payment, currency)
                        : formatCurrency(due.remaining_amount, currency)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>

      {creating && <DebtFormModal onClose={() => setCreating(false)} onSaved={onSaved} />}
      {editing && <DebtFormModal debt={editing} onClose={() => setEditing(null)} onSaved={onSaved} />}
    </>
  );
}

interface DebtFormProps {
  debt?: Debt;
  onClose: () => void;
  onSaved: () => void;
}

function DebtFormModal({ debt, onClose, onSaved }: DebtFormProps) {
  const accounts = useApi<Account[]>("/accounts");
  const [name, setName] = useState(debt?.name ?? "");
  const [creditor, setCreditor] = useState(debt?.creditor ?? "");
  const [original, setOriginal] = useState(debt ? String(debt.original_amount) : "");
  const [remaining, setRemaining] = useState(debt ? String(debt.remaining_amount) : "");
  const [interestRate, setInterestRate] = useState(debt?.interest_rate !== null && debt?.interest_rate !== undefined ? String(debt.interest_rate) : "");
  const [minimum, setMinimum] = useState(debt?.minimum_payment !== null && debt?.minimum_payment !== undefined ? String(debt.minimum_payment) : "");
  const [dueDate, setDueDate] = useState(debt?.due_date ?? "");
  const [accountId, setAccountId] = useState(debt ? String(debt.account_id ?? "none") : "none");
  const [notes, setNotes] = useState(debt?.notes ?? "");
  const [active, setActive] = useState(debt?.active ?? true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = () => {
    const payload = {
      name: name.trim(),
      creditor: creditor.trim() || null,
      original_amount: Number(original),
      remaining_amount: remaining.trim() === "" ? Number(original) : Number(remaining),
      interest_rate: interestRate.trim() === "" ? null : Number(interestRate),
      minimum_payment: minimum.trim() === "" ? null : Number(minimum),
      due_date: dueDate || null,
      account_id: accountId === "none" ? null : Number(accountId),
      notes: notes.trim() || null,
      active,
    };
    setPending(true);
    setError(null);
    const request = debt
      ? apiPatch<Debt>(`/debts/${debt.id}`, payload)
      : apiPost<Debt>("/debts", payload);
    request
      .then(onSaved)
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setPending(false));
  };

  return (
    <Modal
      title={debt ? "Edit debt" : "Add debt"}
      subtitle="Linking a debt to a liability account prevents double counting in net worth."
      onClose={onClose}
      wide
    >
      <div className={styles.formRow}>
        <Field label="Name" hint="required">
          <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Car loan" autoFocus />
        </Field>
        <Field label="Creditor" hint="optional">
          <Input value={creditor} onChange={(event) => setCreditor(event.target.value)} placeholder="e.g. ABX Bank" />
        </Field>
      </div>
      <div className={styles.formRow}>
        <Field label="Original amount" hint="required">
          <Input type="number" step="0.01" inputMode="decimal" value={original} onChange={(event) => setOriginal(event.target.value)} placeholder="0.00" />
        </Field>
        <Field label="Remaining">
          <Input type="number" step="0.01" inputMode="decimal" value={remaining} onChange={(event) => setRemaining(event.target.value)} placeholder="0.00" />
        </Field>
      </div>
      <div className={styles.formRow}>
        <Field label="Interest rate" hint="%">
          <Input type="number" step="0.01" inputMode="decimal" value={interestRate} onChange={(event) => setInterestRate(event.target.value)} placeholder="e.g. 4.5" />
        </Field>
        <Field label="Minimum payment">
          <Input type="number" step="0.01" inputMode="decimal" value={minimum} onChange={(event) => setMinimum(event.target.value)} placeholder="0.00" />
        </Field>
      </div>
      <div className={styles.formRow}>
        <Field label="Due date">
          <Input type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} />
        </Field>
        <Field label="Linked account" hint="optional">
          <Select value={accountId} onChange={(event) => setAccountId(event.target.value)}>
            <option value="none">No account link</option>
            {(accounts.data ?? [])
              .filter((account) => account.type === "credit_card" || account.type === "loan")
              .map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
          </Select>
        </Field>
      </div>
      <Field label="Notes">
        <TextArea value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Optional" />
      </Field>
      <label className={styles.checkboxRow}>
        <input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} />
        <span>Debt is active</span>
      </label>

      <div className={styles.modalActions}>
        <Button variant="ghost" onClick={onClose} disabled={pending}>
          Cancel
        </Button>
        <Button onClick={submit} loading={pending} disabled={!name.trim() || !(Number(original) >= 0)}>
          {debt ? "Save changes" : "Add debt"}
        </Button>
      </div>
      <FormError message={error} />
    </Modal>
  );
}