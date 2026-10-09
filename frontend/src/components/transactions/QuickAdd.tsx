import { useEffect, useRef, useState } from "react";

import { Button } from "../ui/Button";
import { Field, Input } from "../ui/Form";
import { Modal } from "../ui/Modal";
import { AlertIcon, CheckIcon } from "../icons";
import { useMutation } from "../../hooks/useMutation";
import { apiPost } from "../../lib/api";
import { notifyDataChanged } from "../../lib/refresh";
import { captureToCreate, duplicateTone, duplicateToneLabel, topSuggestion } from "../../lib/quick";
import type { QuickCaptureResponse, QuickCreateResponse } from "../../types/api";
import styles from "./QuickAdd.module.css";

export interface QuickAddProps {
  onClose: () => void;
}

function todayIso(): string {
  const date = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

const KIND_NAMES: Record<"expense" | "income", string> = { expense: "Expense", income: "Income" };

export function QuickAdd({ onClose }: QuickAddProps) {
  const [kind, setKind] = useState<"expense" | "income">("expense");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(todayIso());
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [capture, setCapture] = useState<QuickCaptureResponse | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saveAnother, setSaveAnother] = useState(false);
  const debounceRef = useRef<number | null>(null);

  const canCapture = description.trim().length > 0 && Number(amount) > 0;

  const captureRun = useMutation(async () => {
    setDone(null);
    setError(null);
    const result = await apiPost<QuickCaptureResponse>("/quick/capture", {
      type: kind,
      amount: Number(amount),
      description,
      date,
    });
    setCapture(result);
    setCategoryId(null);
    return result;
  });

  const createRun = useMutation(async (addAnother: boolean) => {
    if (!capture) await captureRun.mutate(undefined as never);
    const payload = captureToCreate(capture ?? (await captureRun.mutate(undefined as never)), {
      description,
      amount: Number(amount),
      date,
      categoryId,
    });
    const result = await apiPost<QuickCreateResponse>("/quick/transactions", payload);
    notifyDataChanged();
    setDone(`Added ${result.transaction.description || "transaction"}.`);
    setSaveAnother(addAnother);
    setDescription("");
    setAmount("");
    setCapture(null);
    if (!addAnother) onClose();
    return result;
  });

  useEffect(() => {
    if (!canCapture) {
      setCapture(null);
      return;
    }
    if (debounceRef.current !== null) window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => {
      captureRun
        .mutate(undefined as never)
        .catch(() => undefined);
    }, 350);
    return () => {
      if (debounceRef.current !== null) window.clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, description, amount, date]);

  const tone = duplicateTone(capture?.duplicates ?? []);
  const suggestions = capture?.categories ?? [];
  const suggested = topSuggestion(suggestions);
  const effectiveId = categoryId ?? suggested?.category_id ?? null;

  return (
    <Modal title="Quick add" subtitle="A description and an amount is all you need." onClose={onClose}>
      <div className={styles.form}>
        <div className={styles.kindRow} role="group" aria-label="Transaction kind">
          {(Object.keys(KIND_NAMES) as Array<"expense" | "income">).map((value) => (
            <button
              key={value}
              type="button"
              className={`${styles.kind} ${kind === value ? styles.kindActive : ""}`}
              onClick={() => setKind(value)}
            >
              {KIND_NAMES[value]}
            </button>
          ))}
        </div>

        <Field label="Description">
          <Input
            autoFocus
            value={description}
            placeholder={kind === "expense" ? "Coffee with Sam" : "Paycheck"}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>

        <div className={styles.numberRow}>
          <Field label="Amount">
            <Input
              type="number"
              min={0}
              step={0.01}
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              placeholder="0.00"
            />
          </Field>
          <Field label="Date" hint="Account default from Settings">
            <Input type="date" value={date} onChange={(event) => setDate(event.target.value)} />
          </Field>
        </div>

        {!capture && captureRun.pending && <div className={styles.thinking}>Looking up suggestions…</div>}

        {capture && suggestions.length > 0 && (
          <div className={styles.suggestions}>
            <div className={styles.suggestionsLabel}>Category suggestions</div>
            <div className={styles.chips}>
              {suggestions.slice(0, 5).map((suggestion) => (
                <button
                  key={suggestion.category_id}
                  type="button"
                  className={`${styles.chip} ${effectiveId === suggestion.category_id ? styles.chipActive : ""}`}
                  onClick={() => setCategoryId(suggestion.category_id)}
                  title={suggestion.evidence ?? undefined}
                >
                  {suggestion.category_name}
                  {suggestion.confidence === "exact" && <span className={styles.chipExact}>· seen</span>}
                </button>
              ))}
            </div>
          </div>
        )}

        {tone !== "none" && (
          <div className={tone === "same_day" ? styles.dupWarn : styles.dupNotice}>
            <AlertIcon size={14} />
            <span>
              <strong>{duplicateToneLabel(tone)}</strong> —{" "}
              {tone === "same_day"
                ? "the app would refuse adding again today; edit the amount/date instead."
                : "a similar entry exists within 5 days."}
            </span>
          </div>
        )}

        {error && <div className={styles.error}>{error}</div>}
        {done && (
          <div className={styles.done}>
            <CheckIcon size={14} /> {done}
            {saveAnother && <span> Add another whenever.</span>}
          </div>
        )}

        <div className={styles.actions}>
          <Button variant="ghost" onClick={onClose} disabled={createRun.pending}>
            Cancel
          </Button>
          <Button
            variant="subtle"
            disabled={!canCapture}
            loading={createRun.pending && !done}
            onClick={() => createRun.mutate(true).catch((err: unknown) => setError(err instanceof Error ? err.message : "Failed"))}
          >
            Save &amp; add another
          </Button>
          <Button
            disabled={!canCapture}
            loading={createRun.pending && !done}
            onClick={() => createRun.mutate(false).catch((err: unknown) => setError(err instanceof Error ? err.message : "Failed"))}
          >
            Add {KIND_NAMES[kind]}
          </Button>
        </div>
      </div>
    </Modal>
  );
}