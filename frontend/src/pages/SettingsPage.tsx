import { useEffect, useState } from "react";

import { Button } from "../components/ui/Button";
import { Field, Input, Select } from "../components/ui/Form";
import { Card } from "../components/ui/Card";
import { Modal } from "../components/ui/Modal";
import { ErrorState, SkeletonList } from "../components/ui/States";
import { AlertIcon, CheckIcon, DownloadIcon, UploadIcon } from "../components/icons";
import { useApi } from "../hooks/useApi";
import { useMutation } from "../hooks/useMutation";
import { apiGet, apiPost, apiPut } from "../lib/api";
import {
  ALL_SECTION_IDS,
  SUPPORTED_CURRENCIES,
  dashboardToggleRow,
  orderedVisibleSections,
  pruneOrder,
  sectionLabel,
} from "../lib/settings";
import type {
  Account,
  BackupPayload,
  BackupValidation,
  Category,
  DashboardPeriod,
  SettingsResponse,
  SettingsUpdate,
} from "../types/api";
import styles from "./SettingsPage.module.css";

interface FormState {
  currency: string;
  month_start_day: string;
  minimum_reserve: string;
  default_account_id: string;
  default_expense_category_id: string;
  default_income_category_id: string;
  period: DashboardPeriod;
  sections: Record<string, boolean>;
  order: string[];
  verbosity: "concise" | "standard";
}

export function SettingsPage() {
  const settings = useApi<SettingsResponse>("/settings");
  const accounts = useApi<Account[]>("/accounts");
  const categories = useApi<Category[]>("/categories");
  const [form, setForm] = useState<FormState | null>(null);
  const [savedFlash, setSavedFlash] = useState<string | null>(null);

  useEffect(() => {
    if (form === null && settings.data) {
      const dashboard = settings.data.dashboard;
      setForm({
        currency: settings.data.currency,
        month_start_day: String(settings.data.month_start_day),
        minimum_reserve: String(settings.data.minimum_reserve),
        default_account_id: String(settings.data.default_account_id ?? ""),
        default_expense_category_id: String(settings.data.default_expense_category_id ?? ""),
        default_income_category_id: String(settings.data.default_income_category_id ?? ""),
        period: dashboard.period,
        sections: { ...dashboard.sections },
        order: [...dashboard.order],
        verbosity: settings.data.assistant.verbosity,
      });
    }
  }, [settings.data, form]);

  const save = useMutation(async (payload: SettingsUpdate) => {
    await apiPut<SettingsResponse>("/settings", payload);
    settings.reload();
    setSavedFlash("Preferences saved.");
    window.setTimeout(() => setSavedFlash(null), 2500);
  });

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((current) => (current ? { ...current, [key]: value } : current));

  if (!form) {
    return (
      <div className="page-header">
        <div>
          <div className="page-header__eyebrow">Workspace</div>
          <h1>Settings</h1>
        </div>
        <SkeletonList rows={4} />
      </div>
    );
  }

  const activeAccounts = (accounts.data ?? []).filter((account) => account.active);
  const activeCategories = (categories.data ?? []).filter((category) => category.active);
  const visibleOrder = orderedVisibleSections(
    form.sections,
    form.order as (typeof ALL_SECTION_IDS)[number][],
  );

  const toggles = dashboardToggleRow(form.sections);

  const submit = () => {
    if (!form) return;
    save
      .mutate({
        currency: form.currency,
        month_start_day: Number(form.month_start_day),
        minimum_reserve: Number(form.minimum_reserve),
        default_account_id: form.default_account_id ? Number(form.default_account_id) : null,
        default_expense_category_id: form.default_expense_category_id
          ? Number(form.default_expense_category_id)
          : null,
        default_income_category_id: form.default_income_category_id
          ? Number(form.default_income_category_id)
          : null,
        dashboard: {
          period: form.period,
          sections: form.sections,
          order: pruneOrder(form.order as (typeof ALL_SECTION_IDS)[number][], () => true),
        },
        assistant: { verbosity: form.verbosity },
      })
      .catch(() => undefined);
  };

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-header__eyebrow">Workspace</div>
          <h1>Settings</h1>
          <p className="page-header__subtitle">
            Currency, period start, defaults, dashboard layout and data backup.
          </p>
        </div>
        <div className={styles.headerActions}>
          {savedFlash && (
            <span className={styles.savedFlash}>
              <CheckIcon size={14} /> {savedFlash}
            </span>
          )}
          <Button onClick={submit} loading={save.pending}>
            Save preferences
          </Button>
        </div>
      </div>

      {settings.error && (
        <ErrorState title="Cannot load settings" message={settings.error} onRetry={settings.reload} />
      )}
      {save.error && <div className={styles.pageError}>{save.error}</div>}

      <div className={styles.grid}>
        <section className={styles.column}>
          <Card title="General" subtitle="Money model and period">
            <div className={styles.fieldGrid}>
              <Field label="Currency">
                <Select
                  value={form.currency}
                  onChange={(event) => set("currency", event.target.value)}
                >
                  {SUPPORTED_CURRENCIES.map((currency) => (
                    <option key={currency.code} value={currency.code}>
                      {currency.label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Period starts on day of month" hint="1 = calendar month; 15 = mid-month periods">
                <Input
                  type="number"
                  min={1}
                  max={28}
                  value={form.month_start_day}
                  onChange={(event) => set("month_start_day", event.target.value)}
                />
              </Field>
              <Field
                label="Minimum reserve"
                hint="Held back in Safe-to-Spend before daily amounts"
              >
                <Input
                  type="number"
                  min={0}
                  step={10}
                  value={form.minimum_reserve}
                  onChange={(event) => set("minimum_reserve", event.target.value)}
                />
              </Field>
            </div>
          </Card>

          <Card title="Quick Add defaults" subtitle="Used when the form is left blank">
            <div className={styles.fieldGrid}>
              <Field label="Default account">
                <Select
                  value={form.default_account_id}
                  onChange={(event) => set("default_account_id", event.target.value)}
                >
                  <option value="">— choose —</option>
                  {activeAccounts.map((account) => (
                    <option key={account.id} value={String(account.id)}>
                      {account.name}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Default expense category">
                <Select
                  value={form.default_expense_category_id}
                  onChange={(event) => set("default_expense_category_id", event.target.value)}
                >
                  <option value="">— choose —</option>
                  {activeCategories
                    .filter((category) => category.type === "expense")
                    .map((category) => (
                      <option key={category.id} value={String(category.id)}>
                        {category.name}
                      </option>
                    ))}
                </Select>
              </Field>
              <Field label="Default income category">
                <Select
                  value={form.default_income_category_id}
                  onChange={(event) => set("default_income_category_id", event.target.value)}
                >
                  <option value="">— choose —</option>
                  {activeCategories
                    .filter((category) => category.type === "income")
                    .map((category) => (
                      <option key={category.id} value={String(category.id)}>
                        {category.name}
                      </option>
                    ))}
                </Select>
              </Field>
            </div>
          </Card>

          <Card title="Assistant" subtitle="How structured answers read">
            <Field label="Verbosity">
              <Select
                value={form.verbosity}
                onChange={(event) => set("verbosity", event.target.value as FormState["verbosity"])}
              >
                <option value="standard">Standard — full facts</option>
                <option value="concise">Concise — short answers</option>
              </Select>
            </Field>
          </Card>
        </section>

        <section className={styles.column}>
          <Card title="Dashboard layout" subtitle="Which blocks render and in what order">
            <Field label="History shown">
              <Select
                value={form.period}
                onChange={(event) => set("period", event.target.value as DashboardPeriod)}
              >
                <option value="current">Current period (full history)</option>
                <option value="last_three">Last three periods</option>
              </Select>
            </Field>

            <div className={styles.sectionList}>
              {toggles.map((toggle) => (
                <label key={toggle.section} className={styles.sectionRow}>
                  <input
                    type="checkbox"
                    checked={toggle.visible}
                    onChange={() =>
                      set("sections", {
                        ...form.sections,
                        [toggle.section]: !toggle.visible,
                      })
                    }
                  />
                  <span className={styles.sectionLabel}>{sectionLabel(toggle.section)}</span>
                </label>
              ))}
            </div>

            <div className={styles.orderBlock}>
              <div className={styles.orderTitle}>Order</div>
              <ul className={styles.orderList}>
                {visibleOrder.map((id, index) => (
                  <li key={id} className={styles.orderRow}>
                    <span className={styles.orderPosition}>{index + 1}.</span>
                    <span className={styles.orderLabel}>{sectionLabel(id)}</span>
                    <span className={styles.orderActions}>
                      <button
                        type="button"
                        className={styles.orderButton}
                        disabled={index === 0}
                        onClick={() => {
                          const next = [...form.order];
                          const from = next.indexOf(id);
                          const to = Math.max(0, from - 1);
                          const [moved] = next.splice(from, 1);
                          next.splice(to, 0, moved);
                          set("order", next);
                        }}
                        aria-label={`Move ${sectionLabel(id)} up`}
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        className={styles.orderButton}
                        disabled={index === visibleOrder.length - 1}
                        onClick={() => {
                          const next = [...form.order];
                          const from = next.indexOf(id);
                          const target = visibleOrder[index + 1];
                          const to = target ? Math.max(0, next.indexOf(target)) : from;
                          const [moved] = next.splice(from, 1);
                          next.splice(to, 0, moved);
                          set("order", next);
                        }}
                        aria-label={`Move ${sectionLabel(id)} down`}
                      >
                        ↓
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </Card>

          <Card title="Data safety" subtitle="Full offline backup and restore">
            <BackupTools />
          </Card>
        </section>
      </div>
    </>
  );
}

function BackupTools() {
  const [exported, setExported] = useState<BackupPayload | null>(null);
  const [paste, setPaste] = useState("");
  const [validated, setValidated] = useState<BackupValidation | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [restoreNote, setRestoreNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const exportRun = useMutation(async () => {
    const payload = await apiGet<BackupPayload>("/backup/export");
    setExported(payload);
    return payload;
  });

  const validateRun = useMutation(async (raw: string) => {
    const payload = JSON.parse(raw) as unknown;
    return apiPost<BackupValidation>("/backup/validate", payload);
  });

  const restoreRun = useMutation(async (payload: BackupPayload) => {
    const result = await apiPost<BackupValidation>("/backup/restore", {
      payload,
      confirmed: true,
    });
    setConfirmOpen(false);
    setRestoreNote(result.message);
    return result;
  });

  const download = () => {
    if (!exported) return;
    const blob = new Blob([JSON.stringify(exported, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `pilote-budget-backup-${exported.exported_at.slice(0, 10)}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const previewCount = exported?.counts.reduce((sum, row) => sum + row.rows, 0) ?? 0;

  return (
    <div className={styles.backup}>
      {error && (
        <div className={styles.pageError}>
          <AlertIcon size={14} /> {error}
        </div>
      )}
      {restoreNote && (
        <div className={styles.successNote}>
          <CheckIcon size={14} /> {restoreNote}
        </div>
      )}

      <div className={styles.backupBlock}>
        <div>
          <h3 className={styles.backupTitle}>Export</h3>
          <p className={styles.backupHint}>
            Downloads every table as one JSON file. Nothing leaves your machine.
          </p>
        </div>
        <div className={styles.backupActions}>
          <Button
            variant="subtle"
            onClick={() => {
              setError(null);
              exportRun
                .mutate(undefined as never)
                .then(download)
                .catch((err: unknown) =>
                  setError(err instanceof Error ? err.message : "Export failed"),
                );
            }}
            loading={exportRun.pending}
          >
            <DownloadIcon size={15} /> Export backup
          </Button>
          {exported && (
            <span className={styles.exportMeta}>
              {previewCount} rows across {exported.counts.length} tables
            </span>
          )}
        </div>
      </div>

      <div className={styles.backupBlock}>
        <div>
          <h3 className={styles.backupTitle}>Restore</h3>
          <p className={styles.backupHint}>
            Paste a backup file above, validate it, then restore. Restoring{" "}
            <strong>replaces all local data</strong> — it cannot be undone.
          </p>
        </div>
        <textarea
          className={styles.restoreArea}
          value={paste}
          onChange={(event) => {
            setPaste(event.target.value);
            setValidated(null);
            setError(null);
          }}
          rows={5}
          placeholder='Paste a "pilote-budget-backup" JSON file…'
        />
        <div className={styles.backupActions}>
          <Button
            variant="ghost"
            onClick={() => {
              setError(null);
              validateRun
                .mutate(paste)
                .then((result) => setValidated(result))
                .catch((err: unknown) =>
                  setError(err instanceof Error ? err.message : "Invalid backup file"),
                );
            }}
            loading={validateRun.pending}
            disabled={!paste.trim()}
          >
            <UploadIcon size={15} /> Validate file
          </Button>
          <Button
            variant="danger"
            disabled={!validated?.valid}
            onClick={() => setConfirmOpen(true)}
          >
            Restore from file…
          </Button>
        </div>
        {validateRun.error && <div className={styles.pageError}>{validateRun.error}</div>}
        {validated?.valid && (
          <p className={styles.successNote}>
            <CheckIcon size={14} /> {validated.message}
          </p>
        )}
      </div>

      {confirmOpen && validated && (
        <Modal
          title="Restore this backup?"
          subtitle="All current local data will be replaced by the file. This cannot be undone."
          onClose={() => setConfirmOpen(false)}
          wide
        >
          <div className={styles.confirmBody}>
            <p>
              The file contains {validated.counts.reduce((sum, row) => sum + row.rows, 0)} rows
              across {validated.counts.length} tables.
            </p>
            {validated.counts.filter((row) => row.rows > 0).map((row) => (
              <div className={styles.confirmCount} key={row.table}>
                <span>{row.table}</span>
                <span className="num">{row.rows}</span>
              </div>
            ))}
            <div className={styles.confirmActions}>
              <Button variant="ghost" onClick={() => setConfirmOpen(false)}>
                Cancel
              </Button>
              <Button
                variant="danger"
                loading={restoreRun.pending}
                onClick={() => {
                  const payload = JSON.parse(paste) as BackupPayload;
                  restoreRun.mutate(payload).catch((err: unknown) =>
                    setError(err instanceof Error ? err.message : "Restore failed"),
                  );
                }}
              >
                Restore now
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}