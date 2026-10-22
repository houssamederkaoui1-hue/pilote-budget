import { useState } from "react";

import { GoalsIcon, PencilIcon, PlusIcon, TrashIcon, WalletIcon } from "../components/icons";
import { Button } from "../components/ui/Button";
import { Badge, Card, ProgressBar, StatCard } from "../components/ui/Card";
import { Field, FormError, Input, Select, TextArea } from "../components/ui/Form";
import { Modal } from "../components/ui/Modal";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { useApi } from "../hooks/useApi";
import { errorMessage, useMutation } from "../hooks/useMutation";
import { apiDelete, apiPatch, apiPost } from "../lib/api";
import { formatCurrency, formatDate } from "../lib/format";
import type { Account, Goal } from "../types/api";
import styles from "./GoalsPage.module.css";

function completionLabel(goal: Goal): string {
  if (goal.estimated_completion_date) return `by ${formatDate(goal.estimated_completion_date)}`;
  if (goal.progress_pct >= 100) return "funded";
  if (goal.monthly_contribution) return "no rate yet";
  return "no rate yet";
}

export function GoalsPage() {
  const goals = useApi<Goal[]>("/goals");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Goal | null>(null);
  const currency = "MAD";

  const totalTarget = goals.data?.reduce((sum, goal) => sum + goal.target_amount, 0) ?? 0;
  const totalSaved = goals.data?.reduce((sum, goal) => sum + goal.current_amount, 0) ?? 0;
  const activeGoals = goals.data?.filter((goal) => goal.active) ?? [];

  const remove = useMutation((goal: Goal) => apiDelete(`/goals/${goal.id}`));
  const runDelete = async (goal: Goal) => {
    if (!window.confirm(`Delete goal "${goal.name}"?`)) return;
    try {
      await remove.mutate(goal);
      goals.reload();
    } catch {
      // surfaced via mutation error below
    }
  };

  const onSaved = () => {
    setCreating(false);
    setEditing(null);
    goals.reload();
  };

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-header__eyebrow">Planning</div>
          <h1>Goals</h1>
          <p className="page-header__subtitle">
            Savings targets with progress, pacing and completion estimates.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <PlusIcon size={15} />
          Add goal
        </Button>
      </div>

      <div className={styles.statRow}>
        <StatCard
          label="Goal target"
          value={formatCurrency(totalTarget, currency)}
          hint={`${activeGoals.length} active goals`}
          icon={<GoalsIcon size={15} />}
        />
        <StatCard
          label="Saved"
          value={formatCurrency(totalSaved, currency)}
          hint={totalTarget > 0 ? `${Math.round((totalSaved / totalTarget) * 100)}% of target` : "No targets yet"}
          tone="positive"
          icon={<WalletIcon size={15} />}
        />
      </div>

      <Card title="Goals" subtitle="Progress is paused while a goal is inactive.">
        {goals.loading && <LoadingState label="Loading goals…" />}
        {!goals.loading && goals.error && (
          <ErrorState message={goals.error} onRetry={goals.reload} />
        )}
        {remove.error && <FormError message={remove.error} />}
        {!goals.loading && !goals.error && goals.data && goals.data.length === 0 && (
          <EmptyState
            icon={<GoalsIcon size={20} />}
            title="No savings goals yet"
            description="Set a target and a deadline; the engine estimates the monthly saving pace."
            action={
              <Button size="sm" onClick={() => setCreating(true)}>
                <PlusIcon size={14} />
                Add goal
              </Button>
            }
          />
        )}
        {goals.data && goals.data.length > 0 && (
          <div className={styles.goalGrid}>
            {goals.data.map((goal) => (
              <section
                key={goal.id}
                className={`${styles.goalCard} ${goal.active ? "" : styles.goalInactive}`}
              >
                <div className={styles.goalHead}>
                  <div>
                    <div className={styles.goalName}>{goal.name}</div>
                    <div className="muted-label">
                      {goal.account_name ? `Funded from ${goal.account_name}` : "No funding source"}
                    </div>
                  </div>
                  <div className="row-actions">
                    <button type="button" className="icon-button" title="Edit" onClick={() => setEditing(goal)}>
                      <PencilIcon size={15} />
                    </button>
                    <button type="button" className="icon-button danger" title="Delete" onClick={() => runDelete(goal)}>
                      <TrashIcon size={15} />
                    </button>
                  </div>
                </div>

                <div className={styles.goalAmounts}>
                  <div className={styles.goalValue}>
                    <span className="num positive">{formatCurrency(goal.current_amount, currency)}</span>
                    <span className="muted-label"> of {formatCurrency(goal.target_amount, currency)}</span>
                  </div>
                  <Badge tone={goal.progress_pct >= 100 ? "positive" : "accent"}>{goal.progress_pct}%</Badge>
                </div>

                <ProgressBar value={goal.progress_pct} tone={goal.progress_pct >= 90 ? "positive" : "accent"} />

                <div className={styles.goalMeta}>
                  <Meta label="Remaining" value={formatCurrency(goal.remaining_amount, currency)} />
                  <Meta
                    label="Required / mo"
                    value={goal.required_monthly_saving === null ? "—" : formatCurrency(goal.required_monthly_saving, currency)}
                  />
                  <Meta
                    label="Contribution"
                    value={goal.monthly_contribution === null ? "—" : formatCurrency(goal.monthly_contribution, currency)}
                  />
                  <Meta label="Estimated" value={completionLabel(goal)} />
                  {goal.target_date && <Meta label="Deadline" value={formatDate(goal.target_date)} />}
                </div>

                {!goal.active && <Badge tone="neutral">Inactive</Badge>}
              </section>
            ))}
          </div>
        )}
      </Card>

      {creating && <GoalFormModal onClose={() => setCreating(false)} onSaved={onSaved} />}
      {editing && <GoalFormModal goal={editing} onClose={() => setEditing(null)} onSaved={onSaved} />}
    </>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.metaItem}>
      <div className="muted-label">{label}</div>
      <div className={`num ${styles.metaValue}`}>{value}</div>
    </div>
  );
}

interface GoalFormProps {
  goal?: Goal;
  onClose: () => void;
  onSaved: () => void;
}

function GoalFormModal({ goal, onClose, onSaved }: GoalFormProps) {
  const accounts = useApi<Account[]>("/accounts");
  const [name, setName] = useState(goal?.name ?? "");
  const [target, setTarget] = useState(goal ? String(goal.target_amount) : "");
  const [current, setCurrent] = useState(goal ? String(goal.current_amount) : "0");
  const [targetDate, setTargetDate] = useState(goal?.target_date ?? "");
  const [accountId, setAccountId] = useState(goal ? String(goal.account_id ?? "none") : "none");
  const [notes, setNotes] = useState(goal?.notes ?? "");
  const [active, setActive] = useState(goal?.active ?? true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = () => {
    const payload = {
      name: name.trim(),
      target_amount: Number(target),
      current_amount: Number(current) || 0,
      target_date: targetDate || null,
      account_id: accountId === "none" ? null : Number(accountId),
      notes: notes.trim() || null,
      active,
    };
    setPending(true);
    setError(null);
    const request = goal
      ? apiPatch<Goal>(`/goals/${goal.id}`, payload)
      : apiPost<Goal>("/goals", payload);
    request
      .then(onSaved)
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setPending(false));
  };

  return (
    <Modal
      title={goal ? "Edit goal" : "Add goal"}
      subtitle="The goal engine computes pacing from your recent savings."
      onClose={onClose}
      wide
    >
      <div className={styles.formRow}>
        <Field label="Name" hint="required">
          <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Emergency fund" autoFocus />
        </Field>
        <Field label="Target amount" hint="required">
          <Input type="number" step="0.01" inputMode="decimal" value={target} onChange={(event) => setTarget(event.target.value)} placeholder="0.00" />
        </Field>
      </div>
      <div className={styles.formRow}>
        <Field label="Current amount">
          <Input type="number" step="0.01" inputMode="decimal" value={current} onChange={(event) => setCurrent(event.target.value)} placeholder="0.00" />
        </Field>
        <Field label="Deadline">
          <Input type="date" value={targetDate} onChange={(event) => setTargetDate(event.target.value)} />
        </Field>
      </div>
      <Field label="Fund from account" hint="optional">
        <Select value={accountId} onChange={(event) => setAccountId(event.target.value)}>
          <option value="none">No account link</option>
          {(accounts.data ?? []).map((account) => (
            <option key={account.id} value={account.id}>
              {account.name}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Notes">
        <TextArea value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Optional" />
      </Field>
      <label className={styles.checkboxRow}>
        <input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} />
        <span>Goal is active</span>
      </label>

      <div className={styles.modalActions}>
        <Button variant="ghost" onClick={onClose} disabled={pending}>
          Cancel
        </Button>
        <Button onClick={submit} loading={pending} disabled={!name.trim() || !(Number(target) > 0)}>
          {goal ? "Save changes" : "Add goal"}
        </Button>
      </div>
      <FormError message={error} />
    </Modal>
  );
}