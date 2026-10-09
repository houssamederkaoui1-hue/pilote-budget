import { useEffect, useMemo, useState } from "react";

import { Field, Input, Select } from "../../components/ui/Form";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { errorMessage } from "../../hooks/useMutation";
import { apiPatch, apiPost } from "../../lib/api";
import { duplicateTone, duplicateToneLabel } from "../../lib/quick";
import type {
  Account,
  Category,
  QuickCaptureResponse,
  TransactionKind,
  TransactionRow,
  TransactionStatusValue,
} from "../../types/api";
import styles from "./TransactionForm.module.css";

const KIND_OPTIONS: { value: TransactionKind; label: string }[] = [
  { value: "expense", label: "Expense" },
  { value: "income", label: "Income" },
  { value: "transfer", label: "Transfer" },
];

const TRANSACTION_STATUSES: { value: TransactionStatusValue; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "cleared", label: "Cleared" },
  { value: "reconciled", label: "Reconciled" },
  { value: "void", label: "Void" },
];

const TRANSFER_STATUSES: { value: TransactionStatusValue; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "completed", label: "Completed" },
  { value: "cancelled", label: "Cancelled" },
];

function todayIso(): string {
  const date = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

interface TransactionFormProps {
  accounts: Account[];
  categories: Category[];
  /** Row being edited (full mode only); omit for create. */
  initial?: TransactionRow;
  /** Compact variant used by quick entry: keeps only the essentials. */
  quick?: boolean;
  /** Default account preselected when creating. */
  defaultAccountId?: number;
  onSaved: (row: TransactionRow) => void;
  onClose: () => void;
}

interface TransactionFormState {
  kind: TransactionKind;
  amount: string;
  accountId: string;
  destinationAccountId: string;
  categoryId: string;
  date: string;
  description: string;
  notes: string;
  status: TransactionStatusValue;
}

export function TransactionForm({
  accounts,
  categories,
  initial,
  quick,
  defaultAccountId,
  onSaved,
  onClose,
}: TransactionFormProps) {
  const editingTransfer = initial?.entity === "transfer";
  const editingKind: TransactionKind = initial?.type ?? "expense";

  const [form, setForm] = useState<TransactionFormState>({
    kind: editingKind,
    amount: initial ? String(initial.amount) : "",
    accountId: String(initial?.account_id ?? defaultAccountId ?? accounts[0]?.id ?? ""),
    destinationAccountId: String(initial?.destination_account_id ?? ""),
    categoryId: String(initial?.category_id ?? ""),
    date: initial?.date ?? todayIso(),
    description: initial?.description ?? "",
    notes: initial?.notes ?? "",
    status: initial
      ? (initial.status as TransactionStatusValue)
      : editingTransfer
        ? "completed"
        : "cleared",
  });
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [capture, setCapture] = useState<QuickCaptureResponse | null>(null);
  const [captureBusy, setCaptureBusy] = useState(false);
  const [forceAdd, setForceAdd] = useState(false);
  const [tick, setTick] = useState(0);

  const set = <K extends keyof TransactionFormState>(key: K, value: TransactionFormState[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  const isTransfer = form.kind === "transfer";
  const isEditingTransfer = isTransfer && editingTransfer;
  const statusOptions = isTransfer ? TRANSFER_STATUSES : TRANSACTION_STATUSES;

  /** Suggestions + duplicate feedback only make sense for new expense/income rows. */
  const suggestible = Boolean(!initial && !isTransfer && form.amount && Number(form.amount) > 0 && form.description.trim());

  const tone = capture ? duplicateTone(capture.duplicates) : "none";

  useEffect(() => {
    if (!suggestible) {
      setCapture(null);
      setForceAdd(false);
      return;
    }
    setCapture(null);
    setForceAdd(false);
    setCaptureBusy(true);
    const timer = window.setTimeout(() => {
      apiPost<QuickCaptureResponse>("/quick/capture", {
        type: form.kind,
        amount: Number(form.amount),
        description: form.description.trim(),
        date: form.date,
      })
        .then((result) => setCapture(result))
        .catch(() => setCapture(null))
        .finally(() => setCaptureBusy(false));
    }, 350);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [suggestible, form.kind, form.amount, form.description, form.date, tick]);

  const blockDuplicate = tone === "same_day" && !forceAdd;

  const categoryOptions = useMemo(
    () =>
      categories.filter(
        (category) =>
          category.active && (isTransfer ? false : category.type === form.kind),
      ),
    [categories, form.kind, isTransfer],
  );

  const canSubmit = Boolean(
    form.amount &&
      Number(form.amount) > 0 &&
      form.accountId &&
      form.date &&
      (!isTransfer || form.destinationAccountId),
  );

  const submit = () => {
    if (!canSubmit) return;
    if (blockDuplicate) {
      setError(
        "Looks like a duplicate — this exact amount and description was recorded today. Tick “Add anyway” if you really mean it.",
      );
      setCapture(null);
      setTick((value) => value + 1);
      return;
    }
    setPending(true);
    setError(null);

    const common = {
      amount: Number(form.amount),
      date: form.date,
      description: form.description.trim(),
      notes: form.notes.trim() || null,
    };

    const request: Promise<TransactionRow> = isTransfer
      ? isEditingTransfer
        ? apiPatch<TransactionRow>(`/transfers/${initial?.id}`, {
            ...common,
            source_account_id: Number(form.accountId),
            destination_account_id: Number(form.destinationAccountId),
            status: form.status,
          })
        : apiPost<TransactionRow>("/transfers", {
            ...common,
            source_account_id: Number(form.accountId),
            destination_account_id: Number(form.destinationAccountId),
            status: form.status,
          })
      : initial
        ? apiPatch<TransactionRow>(`/transactions/${initial.id}`, {
            type: form.kind,
            ...common,
            account_id: Number(form.accountId),
            category_id: form.categoryId ? Number(form.categoryId) : null,
            status: form.status,
          })
        : apiPost<TransactionRow>("/transactions", {
            type: form.kind,
            ...common,
            account_id: Number(form.accountId),
            category_id: form.categoryId ? Number(form.categoryId) : null,
            status: form.status,
          });

    request
      .then(onSaved)
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setPending(false));
  };

  return (
    <Modal
      title={initial ? "Edit transaction" : quick ? "Quick entry" : "New transaction"}
      subtitle={
        quick
          ? "Add a single transaction fast; details come later."
          : "Record income, an expense or a transfer between accounts."
      }
      onClose={onClose}
    >
      {!quick && (
        <div className="tabs">
          {KIND_OPTIONS.map((option) => (
            <button
              type="button"
              key={option.value}
              className={form.kind === option.value ? "active" : ""}
              onClick={() =>
                setForm((current) => ({
                  ...current,
                  kind: option.value,
                  categoryId: "",
                }))
              }
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
      {quick && <p className={styles.quickKind}>recorded as {form.kind}</p>}

      <div className={styles.form}>
        <div className={styles.row}>
          <Field label="Amount" hint="required, positive">
            <Input
              type="number"
              min="0"
              step="0.01"
              inputMode="decimal"
              value={form.amount}
              onChange={(event) => set("amount", event.target.value)}
              placeholder="0.00"
              autoFocus
            />
          </Field>
          <Field label="Date" hint="required">
            <Input
              type="date"
              value={form.date}
              onChange={(event) => set("date", event.target.value)}
            />
          </Field>
        </div>

        <div className={styles.row}>
          <Field label={isTransfer ? "From account" : "Account"}>
            <Select
              value={form.accountId}
              onChange={(event) => set("accountId", event.target.value)}
            >
              {accounts.length === 0 && <option value="">No accounts</option>}
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
            </Select>
          </Field>
          {isTransfer ? (
            <Field label="To account">
              <Select
                value={form.destinationAccountId}
                onChange={(event) => set("destinationAccountId", event.target.value)}
              >
                <option value="">Choose account…</option>
                {accounts
                  .filter((account) => account.id !== Number(form.accountId))
                  .map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.name}
                    </option>
                  ))}
              </Select>
            </Field>
          ) : (
            <Field label="Category">
              <Select
                value={form.categoryId}
                onChange={(event) => set("categoryId", event.target.value)}
              >
                <option value="">No category</option>
                {categoryOptions.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </Select>
            </Field>
          )}
        </div>

        {suggestible && capture && capture.categories.length > 0 && (
          <div className={styles.suggestions}>
            <span className={styles.suggestionsLabel}>Suggested categories</span>
            <div className={styles.chips}>
              {capture.categories.slice(0, 5).map((suggestion) => (
                <button
                  key={suggestion.category_id}
                  type="button"
                  className={`${styles.chip} ${
                    form.categoryId === String(suggestion.category_id) ? styles.chipActive : ""
                  }`}
                  onClick={() => set("categoryId", String(suggestion.category_id))}
                  title={suggestion.evidence ?? undefined}
                >
                  {suggestion.category_name}
                  {suggestion.confidence === "exact" && <span className={styles.chipExact}>· seen</span>}
                </button>
              ))}
            </div>
          </div>
        )}
        {suggestible && captureBusy && !capture && (
          <div className={styles.suggestHint}>Checking for duplicates…</div>
        )}

        {suggestible && tone !== "none" && !blockDuplicate && (
          <div className={tone === "same_day" ? styles.dupWarn : styles.dupNotice}>
            <strong>{duplicateToneLabel(tone)}.</strong>{" "}
            {tone === "same_day" ? "This will be rejected on save." : "A similar entry exists within 5 days."}
          </div>
        )}
        {suggestible && tone === "same_day" && (
          <label className={styles.forceAdd}>
            <input
              type="checkbox"
              checked={forceAdd}
              onChange={(event) => setForceAdd(event.target.checked)}
            />
            Add anyway (I meant this entry to exist twice)
          </label>
        )}

        <Field label="Description">
          <Input
            value={form.description}
            onChange={(event) => set("description", event.target.value)}
            placeholder="e.g. Groceries, Paycheck, Rent…"
          />
        </Field>

        {!quick && (
          <div className={styles.row}>
            <Field label="Status">
              <Select
                value={form.status}
                onChange={(event) => set("status", event.target.value as TransactionStatusValue)}
              >
                {statusOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Notes">
              <Input
                value={form.notes}
                onChange={(event) => set("notes", event.target.value)}
                placeholder="Optional notes"
              />
            </Field>
          </div>
        )}
      </div>

      {error && (
        <div className={styles.formError} role="alert">
          {error}
        </div>
      )}

      <div className={styles.actions}>
        <Button variant="ghost" onClick={onClose} disabled={pending}>
          Cancel
        </Button>
        <Button onClick={submit} loading={pending} disabled={!canSubmit}>
          {initial ? "Save changes" : quick ? "Add" : "Add transaction"}
        </Button>
      </div>
    </Modal>
  );
}