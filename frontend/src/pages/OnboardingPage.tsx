import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "../components/ui/Button";
import { Field, Input, Select } from "../components/ui/Form";
import { Card } from "../components/ui/Card";
import { CheckIcon } from "../components/icons";
import { useApi } from "../hooks/useApi";
import { useMutation } from "../hooks/useMutation";
import { apiPost, apiPut } from "../lib/api";
import { SUPPORTED_CURRENCIES } from "../lib/settings";
import type { OnboardingResponse } from "../types/api";
import styles from "./OnboardingPage.module.css";

const STEPS = ["account", "categories", "budget", "goals"] as const;

function todayIso(): string {
  const date = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function OnboardingPage() {
  const navigate = useNavigate();
  const state = useApi<OnboardingResponse>("/settings/onboarding");
  const [step, setStep] = useState<(typeof STEPS)[number]>("account");
  const [currency, setCurrency] = useState("MAD");
  const [error, setError] = useState<string | null>(null);

  const steps = useMemo(() => {
    const byId = new Map((state.data?.steps ?? []).map((s) => [s.id, s]));
    return STEPS.map((id, index) => {
      const meta = byId.get(id);
      return {
        id,
        index,
        complete: meta?.complete ?? false,
        optional: meta?.optional ?? false,
        label: meta?.label ?? id,
      };
    });
  }, [state.data]);

  const currentIndex = steps.findIndex((s) => s.id === step);
  const nextIncomplete = steps.find((s) => !s.complete && !s.optional) ?? steps.find((s) => !s.complete);
  const allDone = steps.every((s) => s.complete);
  const completedCount = steps.filter((s) => s.complete).length;

  const skip = useMutation(async () => {
    await apiPut<OnboardingResponse>("/settings/onboarding", { skipped: true });
    navigate("/");
  });

  const finish = async (extra?: () => Promise<unknown>) => {
    if (extra) await extra();
    await Promise.all([state.reload()]);
    if (currency) {
      await apiPut("/settings", { currency });
    }
    navigate("/");
  };

  return (
    <div className="page-header">
      <div>
        <div className="page-header__eyebrow">First run</div>
        <h1>Let's set up your money</h1>
        <p className="page-header__subtitle">
          Four quick steps. You can skip optional ones and change everything later in Settings.
        </p>
      </div>
      <div className={styles.headerActions}>
        <Button variant="ghost" onClick={() => skip.mutate(undefined as never).catch(() => undefined)} loading={skip.pending}>
          Skip onboarding
        </Button>
      </div>

      {error && (
        <div className={styles.pageError}>Something went wrong: {error}</div>
      )}

      <div className={styles.wizard}>
        <aside className={styles.rail}>
          <ol className={styles.railList}>
            {steps.map((entry) => (
              <li
                key={entry.id}
                className={`${styles.railStep} ${entry.complete ? styles.done : ""} ${
                  step === entry.id ? styles.active : ""
                }`}
              >
                <button
                  type="button"
                  className={styles.railButton}
                  onClick={() => {
                    setError(null);
                    setStep(entry.id);
                  }}
                >
                  <span className={styles.railIndex}>
                    {entry.complete ? <CheckIcon size={13} /> : entry.index + 1}
                  </span>
                  <span>
                    <span className={styles.railLabel}>{entry.label}</span>
                    {entry.optional && <span className={styles.railOptional}>optional</span>}
                  </span>
                </button>
              </li>
            ))}
          </ol>
          <div className={styles.progress}>
            <div className={styles.progressLabel}>
              <span>{completedCount}/{steps.length} done</span>
              <span className="num">{Math.round((completedCount / steps.length) * 100)}%</span>
            </div>
            <div className={styles.progressTrack}>
              <div
                className={styles.progressBar}
                style={{ width: `${(completedCount / steps.length) * 100}%` }}
              />
            </div>
          </div>
        </aside>

        <Card className={styles.stage} bodyClassName={styles.stageBody}>
          <StepForm
            step={step}
            currency={currency}
            onCurrency={setCurrency}
            onError={setError}
            onDone={() => {
              state.reload();
              if (currentIndex < steps.length - 1) setStep(steps[currentIndex + 1].id);
              else setStep("account");
            }}
            onFinish={() => finish()}
          />
          <div className={styles.stageNav}>
            <Button
              variant="subtle"
              disabled={currentIndex <= 0}
              onClick={() => setStep(steps[currentIndex - 1].id)}
            >
              Previous
            </Button>
            {allDone ? (
              <div className={styles.finishActions}>
                <Field label="Display currency">
                  <Select value={currency} onChange={(event) => setCurrency(event.target.value)}>
                    {SUPPORTED_CURRENCIES.map((entry) => (
                      <option key={entry.code} value={entry.code}>
                        {entry.label}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Button onClick={() => finish().catch(() => undefined)}>Finish setup</Button>
              </div>
            ) : (
              <Button
                variant="subtle"
                disabled={!nextIncomplete}
                onClick={() => setStep(nextIncomplete?.id ?? steps[steps.length - 1].id)}
              >
                {step === "goals" ? "Done for now" : "Next"}
              </Button>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}

function StepForm({
  step,
  currency,
  onCurrency,
  onError,
  onDone,
  onFinish,
}: {
  step: (typeof STEPS)[number];
  currency: string;
  onCurrency: (currency: string) => void;
  onError: (error: string | null) => void;
  onDone: () => void;
  onFinish: () => void;
}) {
  if (step === "account") return <AccountStep onError={onError} onDone={onDone} />;
  if (step === "categories") return <CategoryStep onError={onError} onDone={onDone} />;
  if (step === "budget") return <BudgetStep onError={onError} onDone={onDone} />;
  return <GoalStep currency={currency} onCurrency={onCurrency} onError={onError} onDone={onFinish} />;
}

function AccountStep({ onError, onDone }: { onError: (e: string | null) => void; onDone: () => void }) {
  const [name, setName] = useState("");
  const [type, setType] = useState("checking");
  const [opening, setOpening] = useState("0");
  const save = useMutation(async () => {
    const response = await apiPost("/accounts", {
      name,
      type,
      opening_balance: Number(opening) || 0,
    });
    return response;
  });

  return (
    <div className={styles.formBody}>
      <h2 className={styles.stepTitle}>Add your first account</h2>
      <p className={styles.stepText}>Where your money lives — a checking account is a great start.</p>
      <div className={styles.fields}>
        <Field label="Account name">
          <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Checking" />
        </Field>
        <Field label="Type">
          <Select value={type} onChange={(event) => setType(event.target.value)}>
            <option value="checking">Checking</option>
            <option value="savings">Savings</option>
            <option value="cash">Cash</option>
            <option value="credit_card">Credit card</option>
            <option value="investment">Investment</option>
          </Select>
        </Field>
        <Field label="Opening balance" hint="Current balance if you already have money">
          <Input type="number" value={opening} onChange={(event) => setOpening(event.target.value)} />
        </Field>
      </div>
      <div className={styles.stepActions}>
        <Button
          disabled={!name.trim()}
          loading={save.pending}
          onClick={() =>
            save
              .mutate(undefined as never)
              .then(() => {
                onError(null);
                onDone();
              })
              .catch((err: unknown) => onError(err instanceof Error ? err.message : "Save failed"))
          }
        >
          Save account
        </Button>
      </div>
    </div>
  );
}

function CategoryStep({ onError, onDone }: { onError: (e: string | null) => void; onDone: () => void }) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState("expense");
  const save = useMutation(async () => {
    const response = await apiPost("/categories", { name, type: kind });
    return response;
  });

  return (
    <div className={styles.formBody}>
      <h2 className={styles.stepTitle}>Create a category</h2>
      <p className={styles.stepText}>
        Categories group your spending. Add one now — you can bulk-manage them on the Categories
        page later.
      </p>
      <div className={styles.fields}>
        <Field label="Category name">
          <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Groceries" />
        </Field>
        <Field label="Kind">
          <Select value={kind} onChange={(event) => setKind(event.target.value)}>
            <option value="expense">Expense</option>
            <option value="income">Income</option>
          </Select>
        </Field>
      </div>
      <div className={styles.stepActions}>
        <Button
          disabled={!name.trim()}
          loading={save.pending}
          onClick={() =>
            save
              .mutate(undefined as never)
              .then(() => {
                setName("");
                onError(null);
                onDone();
              })
              .catch((err: unknown) => onError(err instanceof Error ? err.message : "Save failed"))
          }
        >
          Add category
        </Button>
      </div>
      <p className={styles.stepHint}>Tip: add a second one for income if you like (e.g. Salary).</p>
    </div>
  );
}

function BudgetStep({ onError, onDone }: { onError: (e: string | null) => void; onDone: () => void }) {
  const categories = useApi<{ id: number; name: string; type: string }[]>("/categories");
  const [categoryId, setCategoryId] = useState("");
  const [amount, setAmount] = useState("");
  const save = useMutation(async () => {
    const response = await apiPut(`/budgets?period=${todayIso()}`, {
      items: [{ category_id: Number(categoryId), planned_amount: Number(amount) || 0 }],
    });
    return response;
  });

  const expenseCategories = (categories.data ?? []).filter(
    (category) => category.type === "expense" && categoryId !== "",
  );

  return (
    <div className={styles.formBody}>
      <h2 className={styles.stepTitle}>Set a budget (optional)</h2>
      <p className={styles.stepText}>
        Give one category a monthly target so the dashboard can compare plan vs actual.
      </p>
      <div className={styles.fields}>
        <Field label="Expense category">
          <Select value={categoryId} onChange={(event) => setCategoryId(event.target.value)}>
            <option value="">— choose —</option>
            {(categories.data ?? [])
              .filter((category) => category.type === "expense")
              .map((category) => (
                <option key={category.id} value={String(category.id)}>
                  {category.name}
                </option>
              ))}
          </Select>
        </Field>
        <Field label="Planned amount per month">
          <Input
            type="number"
            min={0}
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            placeholder="300"
          />
        </Field>
      </div>
      <div className={styles.stepActions}>
        <Button
          variant="ghost"
          disabled={!categoryId}
          loading={save.pending}
          onClick={() =>
            save
              .mutate(undefined as never)
              .then(() => {
                onError(null);
                onDone();
              })
              .catch((err: unknown) => onError(err instanceof Error ? err.message : "Save failed"))
          }
        >
          Set budget
        </Button>
        <Button variant="subtle" onClick={onDone}>
          Skip for now
        </Button>
      </div>
      {expenseCategories.length === 0 && <p className={styles.stepHint}>Create an expense category in the previous step first.</p>}
    </div>
  );
}

function GoalStep({
  currency,
  onCurrency,
  onError,
  onDone,
}: {
  currency: string;
  onCurrency: (currency: string) => void;
  onError: (e: string | null) => void;
  onDone: () => void;
}) {
  const [name, setName] = useState("");
  const [target, setTarget] = useState("");
  const save = useMutation(async () => {
    const response = await apiPost("/goals", {
      name,
      target_amount: Number(target) || 0,
      current_amount: 0,
    });
    return response;
  });

  return (
    <div className={styles.formBody}>
      <h2 className={styles.stepTitle}>Create a goal (optional)</h2>
      <p className={styles.stepText}>A savings target that the assistant can talk about.</p>
      <div className={styles.fields}>
        <Field label="Goal name">
          <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Emergency fund" />
        </Field>
        <Field label="Target amount">
          <Input type="number" min={1} value={target} onChange={(event) => setTarget(event.target.value)} />
        </Field>
        <Field label="Display currency">
          <Select value={currency} onChange={(event) => onCurrency(event.target.value)}>
            {SUPPORTED_CURRENCIES.map((entry) => (
              <option key={entry.code} value={entry.code}>
                {entry.label}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <div className={styles.stepActions}>
        <Button
          disabled={!name.trim() || !(Number(target) > 0)}
          loading={save.pending}
          onClick={() =>
            save
              .mutate(undefined as never)
              .then(() => {
                onError(null);
                onDone();
              })
              .catch((err: unknown) => onError(err instanceof Error ? err.message : "Save failed"))
          }
        >
          Create goal
        </Button>
        <Button variant="subtle" onClick={onDone}>
          Skip for now
        </Button>
      </div>
    </div>
  );
}