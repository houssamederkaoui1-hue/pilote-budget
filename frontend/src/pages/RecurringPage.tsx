import { useState } from "react";

import {
  AlertIcon,
  CheckIcon,
  ChevronRightIcon,
  PencilIcon,
  PlusIcon,
  RecurringIcon,
  TrashIcon,
} from "../components/icons";
import { Button } from "../components/ui/Button";
import { Badge, Card } from "../components/ui/Card";
import { Field, FormError, Input, Select, TextArea } from "../components/ui/Form";
import { Modal } from "../components/ui/Modal";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { useApi } from "../hooks/useApi";
import { errorMessage, useMutation } from "../hooks/useMutation";
import { apiDelete, apiPatch, apiPost, apiUrl } from "../lib/api";
import { formatCurrency, formatDate } from "../lib/format";
import type { Account, Category, Frequency, RecurringOccurrence, RecurringTemplate } from "../types/api";
import styles from "./RecurringPage.module.css";

const FREQUENCIES: { value: Frequency; label: string }[] = [
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "biweekly", label: "Every 2 weeks" },
  { value: "monthly", label: "Monthly" },
  { value: "quarterly", label: "Quarterly" },
  { value: "yearly", label: "Yearly" },
];

function frequencyLabel(frequency: string): string {
  return FREQUENCIES.find((entry) => entry.value === frequency)?.label ?? frequency;
}

export function RecurringPage() {
  const templates = useApi<RecurringTemplate[]>("/recurring");
  const upcoming = useApi<{ occurrences: RecurringOccurrence[] }>("/recurring/upcoming?days=60");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<RecurringTemplate | null>(null);

  const record = useMutation(({ id, date }: { id: number; date: string }) =>
    apiPost(apiUrl(`/recurring/${id}/record`, date ? { date } : {}), undefined),
  );
  const advance = useMutation((id: number) => apiPost(`/recurring/${id}/advance`));
  const toggle = useMutation((template: RecurringTemplate) =>
    apiPatch<RecurringTemplate>(`/recurring/${template.id}`, { active: !template.active }),
  );
  const remove = useMutation((template: RecurringTemplate) => apiDelete(`/recurring/${template.id}`));

  const reload = () => {
    templates.reload();
    upcoming.reload();
  };

  const runRecord = async (occurrence: RecurringOccurrence) => {
    try {
      await record.mutate({ id: occurrence.recurring_id, date: occurrence.due_date });
      reload();
    } catch {
      // surfaced below
    }
  };

  const runSkip = async (id: number) => {
    try {
      await advance.mutate(id);
      reload();
    } catch {
      // surfaced below
    }
  };

  const runToggle = async (template: RecurringTemplate) => {
    try {
      await toggle.mutate(template);
      reload();
    } catch {
      // surfaced below
    }
  };

  const runDelete = async (template: RecurringTemplate) => {
    if (!window.confirm(`Delete "${template.description || template.frequency}" template?`)) return;
    try {
      await remove.mutate(template);
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

  const mutationsError = record.error || advance.error || toggle.error || remove.error;

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-header__eyebrow">Planning</div>
          <h1>Recurring</h1>
          <p className="page-header__subtitle">
            Scheduled income and expenses. Templates never post themselves — record or skip each due date.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <PlusIcon size={15} />
          Add template
        </Button>
      </div>

      {mutationsError && (
        <div className={styles.inlineError} role="alert">
          {mutationsError}
        </div>
      )}

      <div className={styles.grid}>
        <div className={styles.span7}>
          <Card title="Upcoming" subtitle="Projected due dates over the next 60 days">
            {upcoming.loading && <LoadingState label="Projecting occurrences…" />}
            {!upcoming.loading && upcoming.error && (
              <ErrorState message={upcoming.error} onRetry={upcoming.reload} />
            )}
            {!upcoming.loading && !upcoming.error && upcoming.data && upcoming.data.occurrences.length === 0 && (
              <EmptyState
                icon={<RecurringIcon size={20} />}
                title="Nothing due"
                description="Create a recurring template to see its next occurrences here."
              />
            )}
            {upcoming.data && upcoming.data.occurrences.length > 0 && (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Due</th>
                    <th>Description</th>
                    <th className="amount-cell">Amount</th>
                    <th>Frequency</th>
                    <th aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {upcoming.data.occurrences.map((occurrence, index) => (
                    <tr key={`${occurrence.recurring_id}-${occurrence.due_date}-${index}`} className={occurrence.overdue ? styles.overdueRow : undefined}>
                      <td>
                        <div className={styles.dueCell}>
                          {formatDate(occurrence.due_date)}
                          {occurrence.overdue && (
                            <Badge tone="warning">
                              <AlertIcon size={11} />
                              Overdue
                            </Badge>
                          )}
                        </div>
                        {occurrence.category_name && <div className="muted-label">{occurrence.category_name}</div>}
                      </td>
                      <td>
                        <div className={styles.descCell}>
                          {occurrence.description || "Recurring entry"}
                          {occurrence.account_name && <span className="muted-label"> · {occurrence.account_name}</span>}
                        </div>
                      </td>
                      <td className={`amount-cell num ${occurrence.type === "expense" ? "negative" : "positive"}`}>
                        {occurrence.type === "expense" ? "−" : "+"}{formatCurrency(occurrence.amount, "MAD")}
                      </td>
                      <td>
                        <span className="chip chip-neutral">{frequencyLabel(occurrence.frequency)}</span>
                      </td>
                      <td>
                        <div className="row-actions">
                          <button
                            type="button"
                            className="icon-button"
                            title="Record this occurrence"
                            onClick={() => runRecord(occurrence)}
                            disabled={record.pending || advance.pending}
                          >
                            <CheckIcon size={15} />
                          </button>
                          <button
                            type="button"
                            className="icon-button"
                            title="Skip this occurrence"
                            onClick={() => runSkip(occurrence.recurring_id)}
                            disabled={advance.pending || record.pending}
                          >
                            <ChevronRightIcon size={15} />
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
          <Card title="Templates" subtitle="Schedules that produce the projections">
            {templates.loading && <LoadingState label="Loading templates…" />}
            {!templates.loading && templates.error && (
              <ErrorState message={templates.error} onRetry={templates.reload} />
            )}
            {!templates.loading && !templates.error && templates.data && templates.data.length === 0 && (
              <EmptyState
                icon={<RecurringIcon size={20} />}
                title="No recurring templates"
                description="Add a monthly salary or subscription to start scheduling."
                action={
                  <Button size="sm" onClick={() => setCreating(true)}>
                    <PlusIcon size={14} />
                    Add template
                  </Button>
                }
              />
            )}
            {templates.data && templates.data.length > 0 && (
              <div className={styles.templateList}>
                {templates.data.map((template) => (
                  <section key={template.id} className={`${styles.template} ${template.active ? "" : styles.templateInactive}`}>
                    <div className={styles.templateHead}>
                      <div className={styles.templateTitle}>
                        {template.description || "Recurring entry"}
                        {!template.active && <Badge tone="neutral">Paused</Badge>}
                      </div>
                      <div className="row-actions">
                        <button type="button" className="icon-button" title="Edit" onClick={() => setEditing(template)}>
                          <PencilIcon size={14} />
                        </button>
                        <button type="button" className="icon-button danger" title="Delete" onClick={() => runDelete(template)}>
                          <TrashIcon size={14} />
                        </button>
                      </div>
                    </div>
                    <div className={styles.templateBody}>
                      <span className={`num ${template.type === "expense" ? "negative" : "positive"}`}>
                        {template.type === "expense" ? "−" : "+"}{formatCurrency(template.amount, "MAD")}
                      </span>
                      <span className="chip chip-neutral">{frequencyLabel(template.frequency)}</span>
                      <span className="secondary">next {formatDate(template.next_occurrence)}</span>
                    </div>
                    <div className={styles.templateFoot}>
                      <span className="muted-label">
                        {template.account_name ?? "No account"} · next due {formatDate(template.next_occurrence)}
                        {template.end_date ? ` · until ${formatDate(template.end_date)}` : ""}
                      </span>
                      <Button
                        size="sm"
                        variant="subtle"
                        onClick={() => runToggle(template)}
                      >
                        {template.active ? "Pause" : "Resume"}
                      </Button>
                    </div>
                  </section>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>

      {creating && <RecurringFormModal onClose={() => setCreating(false)} onSaved={onSaved} />}
      {editing && <RecurringFormModal template={editing} onClose={() => setEditing(null)} onSaved={onSaved} />}
    </>
  );
}

interface RecurringFormProps {
  template?: RecurringTemplate;
  onClose: () => void;
  onSaved: () => void;
}

function RecurringFormModal({ template, onClose, onSaved }: RecurringFormProps) {
  const accounts = useApi<Account[]>("/accounts");
  const categories = useApi<Category[]>("/categories");
  const [accountId, setAccountId] = useState(template ? String(template.account_id) : "");
  const [type, setType] = useState<"income" | "expense">(template?.type === "income" ? "income" : "expense");
  const [amount, setAmount] = useState(template ? String(template.amount) : "");
  const [frequency, setFrequency] = useState<Frequency>(template?.frequency ?? "monthly");
  const [description, setDescription] = useState(template?.description ?? "");
  const [nextOccurrence, setNextOccurrence] = useState(template?.next_occurrence ?? "");
  const [endDate, setEndDate] = useState(template?.end_date ?? "");
  const [categoryId, setCategoryId] = useState(template ? String(template.category_id ?? "none") : "none");
  const [notes, setNotes] = useState(template?.notes ?? "");
  const [active, setActive] = useState(template?.active ?? true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const typeCategories = (categories.data ?? [])
    .filter((category) => category.type === type && category.active)
    .sort((a, b) => a.name.localeCompare(b.name));

  const submit = () => {
    const payload = {
      account_id: Number(accountId),
      type,
      amount: Number(amount),
      frequency,
      description: description.trim(),
      next_occurrence: nextOccurrence || null,
      end_date: endDate || null,
      category_id: categoryId === "none" ? null : Number(categoryId),
      notes: notes.trim() || null,
      active,
    };
    setPending(true);
    setError(null);
    const request = template
      ? apiPatch<RecurringTemplate>(`/recurring/${template.id}`, payload)
      : apiPost<RecurringTemplate>("/recurring", payload);
    request
      .then(onSaved)
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setPending(false));
  };

  return (
    <Modal
      title={template ? "Edit template" : "Add recurring template"}
      subtitle="Templates are scheduled manually — record or skip each due occurrence."
      onClose={onClose}
      wide
    >
      <div className={styles.formRow}>
        <Field label="Account" hint="required">
          <Select value={accountId} onChange={(event) => setAccountId(event.target.value)}>
            <option value="">Choose account…</option>
            {(accounts.data ?? []).map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Type">
          <Select value={type} onChange={(event) => setType(event.target.value as "income" | "expense")}>
            <option value="expense">Expense</option>
            <option value="income">Income</option>
          </Select>
        </Field>
      </div>
      <div className={styles.formRow}>
        <Field label="Amount" hint="required">
          <Input type="number" step="0.01" inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="0.00" />
        </Field>
        <Field label="Frequency">
          <Select value={frequency} onChange={(event) => setFrequency(event.target.value as Frequency)}>
            {FREQUENCIES.map((entry) => (
              <option key={entry.value} value={entry.value}>
                {entry.label}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <div className={styles.formRow}>
        <Field label="Next occurrence" hint="required">
          <Input type="date" value={nextOccurrence} onChange={(event) => setNextOccurrence(event.target.value)} />
        </Field>
        <Field label="End date" hint="optional">
          <Input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
        </Field>
      </div>
      <Field label="Description">
        <Input value={description} onChange={(event) => setDescription(event.target.value)} placeholder="e.g. Monthly rent" />
      </Field>
      <Field label="Category">
        <Select value={categoryId} onChange={(event) => setCategoryId(event.target.value)}>
          <option value="none">No category</option>
          {typeCategories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.name}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Notes">
        <TextArea value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Optional" />
      </Field>
      <label className={styles.checkboxRow}>
        <input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} />
        <span>Template is active</span>
      </label>

      <div className={styles.modalActions}>
        <Button variant="ghost" onClick={onClose} disabled={pending}>
          Cancel
        </Button>
        <Button
          onClick={submit}
          loading={pending}
          disabled={!accountId || !(Number(amount) > 0) || !nextOccurrence}
        >
          {template ? "Save changes" : "Add template"}
        </Button>
      </div>
      <FormError message={error} />
    </Modal>
  );
}