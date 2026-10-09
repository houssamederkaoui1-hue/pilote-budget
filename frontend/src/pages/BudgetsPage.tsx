import { useMemo, useState } from "react";

import {
  AlertIcon,
  BudgetsIcon,
  CheckIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  PencilIcon,
  PlusIcon,
  TrashIcon,
  WalletIcon,
} from "../components/icons";
import { Button } from "../components/ui/Button";
import { Badge, Card, ProgressBar, StatCard } from "../components/ui/Card";
import { Field, FormError, Input, Select } from "../components/ui/Form";
import { Modal } from "../components/ui/Modal";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { useApi } from "../hooks/useApi";
import { errorMessage } from "../hooks/useMutation";
import { apiPut, apiUrl } from "../lib/api";
import { formatCurrency, formatMonthAnchor } from "../lib/format";
import type {
  AllocationPut,
  BudgetItemStats,
  BudgetPut,
  BudgetResponse,
  Category,
} from "../types/api";
import styles from "./BudgetsPage.module.css";

function shiftMonth(iso: string, delta: number): string {
  const [year, month] = iso.split("-").map(Number);
  const date = new Date(year, month - 1 + delta, 1);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-01`;
}

function statusBadge(item: BudgetItemStats) {
  if (item.status === "over") return <Badge tone="negative">Over</Badge>;
  if (item.status === "approaching") return <Badge tone="warning">Approaching</Badge>;
  if (item.status === "healthy") return <Badge tone="positive">On track</Badge>;
  return <Badge tone="neutral">No plan</Badge>;
}

export function BudgetsPage() {
  const [anchor, setAnchor] = useState(new Date().toISOString().slice(0, 10));
  const [editing, setEditing] = useState(false);
  const budget = useApi<BudgetResponse>(apiUrl("/budgets", { period: anchor }));
  const currency = "EUR";
  const data = budget.data;

  const monthLabel = useMemo(
    () =>
      data
        ? formatMonthAnchor(new Date(`${data.period_start}T00:00:00`))
        : "–",
    [data],
  );

  const move = (delta: number) => setAnchor(shiftMonth(anchor, delta));

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-header__eyebrow">Planning</div>
          <h1>Budgets</h1>
          <p className="page-header__subtitle">
            Monthly plans per category with planned vs actual utilisation.
          </p>
        </div>
        <Button onClick={() => setEditing(true)} disabled={!data}>
          <PencilIcon size={15} />
          Edit budget
        </Button>
      </div>

      <div className={styles.monthBar}>
        <button type="button" className="icon-button" onClick={() => move(-1)} title="Previous month">
          <ChevronLeftIcon size={16} />
        </button>
        <div className={styles.monthLabel}>
          {data
            ? `${monthLabel} · ${formatDateRange(data)} · month starts on day ${data.month_start_day}`
            : monthLabel}
        </div>
        <button type="button" className="icon-button" onClick={() => move(1)} title="Next month">
          <ChevronRightIcon size={16} />
        </button>
        <Button variant="subtle" size="sm" onClick={() => setAnchor(new Date().toISOString().slice(0, 10))}>
          This month
        </Button>
      </div>

      {budget.loading && <LoadingState label="Building budget…" />}
      {!budget.loading && budget.error && (
        <ErrorState message={budget.error} onRetry={budget.reload} />
      )}

      {!budget.loading && !budget.error && data && (
        <>
          <div className={styles.statRow}>
            <StatCard
              label="Planned"
              value={formatCurrency(data.totals.planned, currency)}
              hint="Category plans for this period"
              icon={<BudgetsIcon size={15} />}
            />
            <StatCard
              label="Spent"
              value={formatCurrency(data.totals.actual, currency)}
              hint="Posted expenses this period"
              icon={<WalletIcon size={15} />}
            />
            <StatCard
              label="Remaining"
              value={formatCurrency(data.totals.remaining, currency)}
              tone={data.totals.over_budget ? "negative" : "positive"}
              hint={
                data.totals.over_budget
                  ? "Over the plan"
                  : `${data.totals.pct_used ?? 0}% used`
              }
              icon={<CheckIcon size={15} />}
            />
          </div>

          <div className={styles.grid}>
            <div className={styles.span7}>
              <Card
                title="Category budgets"
                subtitle="Planned vs actual per expense category"
                action={
                  data.exceeding.length > 0 ? (
                    <Badge tone="negative">{data.exceeding.length} over</Badge>
                  ) : data.approaching.length > 0 ? (
                    <Badge tone="warning">{data.approaching.length} approaching</Badge>
                  ) : (
                    <Badge tone="positive">On track</Badge>
                  )
                }
              >
                {data.items.length === 0 ? (
                  <EmptyState
                    icon={<BudgetsIcon size={20} />}
                    title="No plan for this period"
                    description="Give each expense category a monthly plan and the engine tracks utilisation until the period ends."
                    action={
                      <Button size="sm" onClick={() => setEditing(true)}>
                        <PlusIcon size={14} />
                        Plan this month
                      </Button>
                    }
                  />
                ) : (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Category</th>
                        <th className="amount-cell">Planned</th>
                        <th className="amount-cell">Actual</th>
                        <th className="amount-cell">Remaining</th>
                        <th className="amount-cell">Used</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.items.map((item) => (
                        <tr key={item.category_id}>
                          <td>
                            <div className={styles.categoryCell}>
                              {item.category_name}
                              {item.over_budget && <AlertIcon size={13} />}
                            </div>
                            {item.notes && <div className="muted-label">{item.notes}</div>}
                          </td>
                          <td className="amount-cell num">{formatCurrency(item.planned_amount, currency)}</td>
                          <td className="amount-cell num">{formatCurrency(item.actual_amount, currency)}</td>
                          <td className={`amount-cell num ${item.remaining_amount < 0 ? "negative" : item.remaining_amount === 0 ? "" : "positive"}`}>
                            {formatCurrency(item.remaining_amount, currency)}
                          </td>
                          <td className="amount-cell num">
                            {item.pct_used === null ? "—" : `${item.pct_used}%`}
                          </td>
                          <td>{statusBadge(item)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Card>
            </div>

            <div className={styles.span5}>
              <Card
                title="Monthly allocation"
                subtitle={data.allocation.has_allocation ? "Planned vs incoming" : "No allocation set"}
                className={styles.full}
              >
                <div className={styles.allocationRows}>
                  <AllocationRow
                    label="Planned"
                    value={data.allocation.planned_total}
                    currency={currency}
                    pct={data.allocation.pct_used}
                  />
                  <AllocationRow
                    label="Incoming"
                    value={data.allocation.income_amount}
                    currency={currency}
                  />
                  <AllocationRow
                    label="Spent"
                    value={data.allocation.actual_total}
                    currency={currency}
                  />
                  <AllocationRow
                    label="Remaining"
                    value={data.allocation.remaining_total}
                    currency={currency}
                    tone={data.allocation.over_budget ? "negative" : "positive"}
                  />
                </div>
                <ProgressBar
                  value={data.allocation.pct_used ?? 0}
                  label="Allocated income used"
                  tone={data.allocation.over_budget ? "negative" : "accent"}
                />
                <div className={styles.allocBreakdown}>
                  {(["needs", "wants", "savings", "other"] as const).map((key) => (
                    <div key={key} className={styles.allocRow}>
                      <span className="secondary capitalize">{key}</span>
                      <span className="num">
                        {formatCurrency(data.allocation[`${key}_amount`], currency)}
                      </span>
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          </div>
        </>
      )}

{editing && data && (
        <BudgetFormModal
          period={data.period_start}
          initial={data}
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            budget.reload();
          }}
        />
      )}
    </>
  );
}

function formatDateRange(budget: BudgetResponse): string {
  const start = new Date(`${budget.period_start}T00:00:00`);
  const end = new Date(`${budget.period_end}T00:00:00`);
  const dayMonth = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" });
  const fullDay = new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  return `${dayMonth.format(start)} – ${fullDay.format(end)}`;
}

function AllocationRow({
  label,
  value,
  currency,
  pct,
  tone,
}: {
  label: string;
  value: number;
  currency: string;
  pct?: number | null;
  tone?: "positive" | "negative";
}) {
  return (
    <div className={styles.allocRow}>
      <span className="secondary">
        {label}
        {typeof pct === "number" && <span className="muted-label"> · {pct}% used</span>}
      </span>
      <span className={`num ${tone === "negative" ? "negative" : tone === "positive" ? "positive" : ""}`}>
        {formatCurrency(value, currency)}
      </span>
    </div>
  );
}

interface BudgetFormProps {
  period: string;
  initial: BudgetResponse;
  onClose: () => void;
  onSaved: () => void;
}

function BudgetFormModal({ period, initial, onClose, onSaved }: BudgetFormProps) {
  const categories = useApi<Category[]>("/categories");
  const [allocation, setAllocation] = useState<AllocationPut>({
    income: initial.allocation.has_allocation ? initial.allocation.income_amount : null,
    needs: initial.allocation.has_allocation ? initial.allocation.needs_amount : null,
    wants: initial.allocation.has_allocation ? initial.allocation.wants_amount : null,
    savings: initial.allocation.has_allocation ? initial.allocation.savings_amount : null,
    other: initial.allocation.has_allocation ? initial.allocation.other_amount : null,
  });
  const [items, setItems] = useState<{ category_id: number | null; planned: string }[]>(
    initial.items.map((item) => ({ category_id: item.category_id, planned: String(item.planned_amount) })),
  );
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const expenseCategories = useMemo(
    () =>
      (categories.data ?? [])
        .filter((category) => category.type === "expense" && category.active)
        .sort((a, b) => a.name.localeCompare(b.name)),
    [categories.data],
  );

  const usedIds = new Set(items.map((item) => item.category_id).filter((id): id is number => id !== null));

  const addItem = () => {
    const free = expenseCategories.find((category) => !usedIds.has(category.id));
    if (free) setItems([...items, { category_id: free.id, planned: "0" }]);
  };

  const patchItem = (index: number, patch: Partial<{ category_id: number | null; planned: string }>) => {
    setItems(items.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  };

  const submit = () => {
    const payload: BudgetPut = {
      allocation:
        allocation.income !== null ||
        allocation.needs !== null ||
        allocation.wants !== null ||
        allocation.savings !== null ||
        allocation.other !== null
          ? {
              income: allocation.income ?? 0,
              needs: allocation.needs ?? 0,
              wants: allocation.wants ?? 0,
              savings: allocation.savings ?? 0,
              other: allocation.other ?? 0,
            }
          : null,
      items: items
        .filter((item) => item.category_id !== null && item.planned !== "")
        .map((item) => ({
          category_id: item.category_id as number,
          planned_amount: Number(item.planned) || 0,
        })),
    };
    setPending(true);
    setError(null);
    apiPut<BudgetResponse>(apiUrl("/budgets", { period }), payload)
      .then(onSaved)
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setPending(false));
  };

  return (
    <Modal
      title={`Edit budget · ${formatMonthAnchor(new Date(`${period}T00:00:00`))}`}
      subtitle="Replaces this month's plan entirely."
      onClose={onClose}
      wide
    >
      <div className={styles.formSection}>
        <h3 className={styles.formSectionTitle}>Monthly allocation</h3>
        <div className={styles.allocGrid}>
          <Field label="Expected income">
            <Input
              type="number"
              step="0.01"
              inputMode="decimal"
              value={allocation.income ?? ""}
              placeholder="0"
              onChange={(event) => setAllocation({ ...allocation, income: event.target.value === "" ? null : Number(event.target.value) })}
            />
          </Field>
          <Field label="Needs">
            <Input
              type="number"
              step="0.01"
              inputMode="decimal"
              value={allocation.needs ?? ""}
              placeholder="0"
              onChange={(event) => setAllocation({ ...allocation, needs: event.target.value === "" ? null : Number(event.target.value) })}
            />
          </Field>
          <Field label="Wants">
            <Input
              type="number"
              step="0.01"
              inputMode="decimal"
              value={allocation.wants ?? ""}
              placeholder="0"
              onChange={(event) => setAllocation({ ...allocation, wants: event.target.value === "" ? null : Number(event.target.value) })}
            />
          </Field>
          <Field label="Savings">
            <Input
              type="number"
              step="0.01"
              inputMode="decimal"
              value={allocation.savings ?? ""}
              placeholder="0"
              onChange={(event) => setAllocation({ ...allocation, savings: event.target.value === "" ? null : Number(event.target.value) })}
            />
          </Field>
          <Field label="Other">
            <Input
              type="number"
              step="0.01"
              inputMode="decimal"
              value={allocation.other ?? ""}
              placeholder="0"
              onChange={(event) => setAllocation({ ...allocation, other: event.target.value === "" ? null : Number(event.target.value) })}
            />
          </Field>
        </div>
      </div>

      <div className={styles.formSection}>
        <div className={styles.sectionHead}>
          <h3 className={styles.formSectionTitle}>Category plans</h3>
          <Button size="sm" variant="subtle" onClick={addItem} disabled={expenseCategories.length === 0 || usedIds.size >= expenseCategories.length}>
            <PlusIcon size={14} />
            Add category
          </Button>
        </div>
        {expenseCategories.length === 0 && !categories.loading && (
          <p className="muted-label">No active expense categories — create some first.</p>
        )}
        {items.map((item, index) => (
          <div key={index} className={styles.itemRow}>
            <Select value={item.category_id ?? ""} onChange={(event) => patchItem(index, { category_id: event.target.value === "" ? null : Number(event.target.value) })}>
              {!item.category_id && <option value="">Choose category…</option>}
              {expenseCategories
                .filter((category) => category.id === item.category_id || !usedIds.has(category.id))
                .map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
            </Select>
            <Input
              type="number"
              step="0.01"
              inputMode="decimal"
              value={item.planned}
              placeholder="Monthly plan"
              onChange={(event) => patchItem(index, { planned: event.target.value })}
            />
            <button type="button" className="icon-button danger" title="Remove" onClick={() => setItems(items.filter((_, i) => i !== index))}>
              <TrashIcon size={14} />
            </button>
          </div>
        ))}
      </div>

      <div className={styles.modalActions}>
        <Button variant="ghost" onClick={onClose} disabled={pending}>
          Cancel
        </Button>
        <Button onClick={submit} loading={pending}>
          Save budget
        </Button>
      </div>
      <FormError message={error} />
    </Modal>
  );
}