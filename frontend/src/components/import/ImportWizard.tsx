import { useState } from "react";

import { Button } from "../../components/ui/Button";
import { Field, Input, Select } from "../../components/ui/Form";
import { Modal } from "../../components/ui/Modal";
import { errorMessage } from "../../hooks/useMutation";
import { apiUpload } from "../../lib/api";
import type {
  Account,
  FieldColumn,
  ImportCommit,
  ImportInspect,
  ImportMapping,
  ImportPreview,
} from "../../types/api";
import styles from "./ImportWizard.module.css";

type WizardStep = "file" | "mapping" | "preview" | "done";

const FIELD_DEFS: { key: keyof FieldColumnMap; label: string; hint?: string }[] = [
  { key: "date", label: "Date", hint: "required" },
  { key: "description", label: "Description" },
  { key: "amount", label: "Amount", hint: "or debit + credit" },
  { key: "debit", label: "Debit"}, { key: "credit", label: "Credit" },
  { key: "category", label: "Category" },
  { key: "account", label: "Account", hint: "or a default below" },
  { key: "reference", label: "Reference" },
];

// eslint-disable-next-line @typescript-eslint/no-empty-object-type
interface FieldColumnMap extends Record<string, FieldColumn | undefined> {}

interface ImportWizardProps {
  accounts: Account[];
  onClose: () => void;
  onImported: () => void;
}

export function ImportWizard({ accounts, onClose, onImported }: ImportWizardProps) {
  const [step, setStep] = useState<WizardStep>("file");
  const [file, setFile] = useState<File | null>(null);
  const [inspect, setInspect] = useState<ImportInspect | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [commit, setCommit] = useState<ImportCommit | null>(null);

  const [columns, setColumns] = useState<Record<string, string>>({});
  const [dateFormat, setDateFormat] = useState<string>("");
  const [decimalSeparator, setDecimalSeparator] = useState<"auto" | "." | ",">("auto");
  const [amountMode, setAmountMode] = useState<ImportMapping["options"]["amount_mode"]>("auto");
  const [defaultAccountId, setDefaultAccountId] = useState<string>("");

  const [busy, setBusy] = useState<(string | null)[]>([]);
  const [error, setError] = useState<string | null>(null);

  const working = busy.some(Boolean);

  const pickFile = (file: File) => {
    setBusy(["file"]);
    setError(null);
    setFile(file);
    apiUpload<ImportInspect>("/imports/inspect", file, {}, file.name)
      .then((result) => {
        setInspect(result);
        const initial: Record<string, string> = {};
        for (const [key, suggestion] of Object.entries(result.suggestions)) {
          if (suggestion?.column !== undefined && suggestion.column !== null) {
            initial[key] = String(suggestion.column);
          }
        }
        setColumns((current) => ({ ...initial, ...current }));
        // Use the format the parser detected from the sample rows; fall back
        // to auto-detection only when nothing matched.
        setDateFormat(result.date_formats[0] ?? "");
        setStep("mapping");
      })
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setBusy([]));
  };

  const buildMapping = (): ImportMapping => {
    const fields: Record<string, FieldColumn> = {};
    for (const def of FIELD_DEFS) {
      const raw = columns[def.key];
      const column = raw === undefined || raw === "" ? null : Number(raw);
      if (column !== null) {
        fields[def.key] = { column, format: def.key === "date" && dateFormat ? dateFormat : null };
      }
    }
    return {
      fields,
      options: {
        decimal_separator: decimalSeparator,
        amount_mode: amountMode,
        default_account_id: defaultAccountId ? Number(defaultAccountId) : null,
        filename: inspect?.filename ?? null,
      },
    };
  };

  const mappingValid = () => {
    const hasAmount = columns.amount !== undefined && columns.amount !== "";
    const hasDebit = columns.debit !== undefined && columns.debit !== "";
    const hasCredit = columns.credit !== undefined && columns.credit !== "";
    const hasAccount = defaultAccountId !== "" || (columns.account !== undefined && columns.account !== "");
    const hasDate = columns.date !== undefined && columns.date !== "";
    return {
      ok: (hasAmount || hasDebit || hasCredit) && hasAccount && hasDate,
      messages: [
        !hasAmount && !hasDebit && !hasCredit
          ? "Map an Amount column, or Debit and/or Credit columns."
          : null,
        !hasAccount ? "Map an Account column or pick a default account below." : null,
        !hasDate ? "Date must be mapped to a column." : null,
      ].filter(Boolean) as string[],
    };
  };

  const runPreview = () => {
    const validation = mappingValid();
    if (!validation.ok) {
      setError(validation.messages.join(" "));
      return;
    }
    if (!file) {
      setError("The uploaded file is no longer available — please start again.");
      return;
    }
    setBusy(["preview"]);
    setError(null);
    apiUpload<ImportPreview>(
      "/imports/preview",
      file,
      { mapping: JSON.stringify(buildMapping()) },
      inspect?.filename ?? file.name,
    )
      .then((result) => {
        setPreview(result);
        setStep("preview");
      })
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setBusy([]));
  };

  const runCommit = () => {
    if (!file) {
      setError("The uploaded file is no longer available — please start again.");
      return;
    }
    setBusy(["commit"]);
    setError(null);
    apiUpload<ImportCommit>(
      "/imports/commit",
      file,
      { mapping: JSON.stringify(buildMapping()) },
      inspect?.filename ?? file.name,
    )
      .then((result) => {
        setCommit(result);
        setStep("done");
        onImported();
      })
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setBusy([]));
  };

  return (
    <Modal
      title="Import CSV"
      subtitle={
        step === "file"
          ? "Upload a bank or card export; it is never stored."
          : step === "mapping"
            ? "Tell us which column holds what."
            : step === "preview"
              ? "Review what will be recorded."
              : "Import finished."
      }
      onClose={onClose}
      wide
    >
      <ol className={styles.steps}>
        {(["file", "mapping", "preview", "done"] as WizardStep[]).map((name, index) => (
          <li key={name} className={step === name ? styles.stepActive : index < (["file", "mapping", "preview", "done"].indexOf(step)) ? styles.stepDone : ""}>
            <span>{index + 1}</span>
            {name[0].toUpperCase() + name.slice(1)}
          </li>
        ))}
      </ol>

      {error && (
        <div className={styles.error} role="alert">
          {error}
        </div>
      )}

      {step === "file" && (
        <div className={styles.fileStep}>
          <label className={styles.dropzone}>
            <Input
              type="file"
              accept=".csv,.tsv,.txt"
              disabled={working}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) pickFile(file);
              }}
            />
            <span className={styles.dropzoneText}>
              {working ? "Reading file…" : "Choose a CSV or TSV file"}
            </span>
          </label>
          <p className={styles.fileHint}>
            Headers are auto-detected. After the first step your columns are suggested automatically.
          </p>
        </div>
      )}

      {step === "mapping" && inspect && (
        <>
          <div className={styles.mappingTable}>
            <div className={styles.mappingHead}>
              <span>Field</span>
              <span>Column</span>
            </div>
            {FIELD_DEFS.map((def) => (
              <div key={def.key} className={styles.mappingRow}>
                <span className={styles.fieldLabel}>
                  {def.label}
                  {def.hint && <em>{def.hint}</em>}
                </span>
                <Select
                  aria-label={`Map "${def.label}" to a column`}
                  value={columns[def.key] ?? ""}
                  onChange={(event) =>
                    setColumns((current) => ({ ...current, [def.key]: event.target.value }))
                  }
                >
                  <option value="">Unmapped</option>
                  {inspect.columns.map((column, index) => (
                    <option key={`${index}-${column}`} value={index}>
                      {index + 1}. {column || "(unnamed)"}
                    </option>
                  ))}
                </Select>
              </div>
            ))}

            {columns.date !== undefined && columns.date !== "" && (
              <div className={styles.mappingRow}>
                <span className={styles.fieldLabel}>
                  Date format<em>pattern</em>
                </span>
                <Select
                  aria-label="Date format pattern"
                  value={dateFormat}
                  onChange={(event) => setDateFormat(event.target.value)}
                >
                  <option value="">Detect automatically</option>
                  {(inspect.date_formats.length > 0 ? inspect.date_formats : inspect.date_format_candidates).map(
                    (format) => (
                      <option key={format} value={format}>
                        {format}
                      </option>
                    ),
                  )}
                </Select>
              </div>
            )}
          </div>

          <div className={styles.optionsRow}>
            <Field label="Decimal separator">
              <Select
                value={decimalSeparator}
                onChange={(event) => setDecimalSeparator(event.target.value as "auto" | "." | ",")}
              >
                <option value="auto">Auto-detect</option>
                <option value=".">Dot (12.34)</option>
                <option value=",">Comma (12,34)</option>
              </Select>
            </Field>
            <Field label="Amount mode">
              <Select
                value={amountMode}
                onChange={(event) => setAmountMode(event.target.value as ImportMapping["options"]["amount_mode"])}
              >
                <option value="auto">Auto (pos = income)</option>
                <option value="income">Force income</option>
                <option value="expense">Force expense</option>
                <option value="flip">Flip signs</option>
              </Select>
            </Field>
            <Field label="Default account">
              <Select value={defaultAccountId} onChange={(event) => setDefaultAccountId(event.target.value)}>
                <option value="">Map account column…</option>
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          <div className={styles.actions}>
            <Button variant="ghost" onClick={() => setStep("file")} disabled={working}>
              Back
            </Button>
            <Button onClick={runPreview} loading={working && busy.includes("preview")}>
              Preview import
            </Button>
          </div>
        </>
      )}

      {step === "preview" && preview && (
        <>
          <div className={styles.counts}>
            <div className={styles.count}>
              <strong>{preview.counts.total}</strong>
              <span>total</span>
            </div>
            <div className={styles.countGood}>
              <strong>{preview.counts.valid}</strong>
              <span>valid</span>
            </div>
            <div className={styles.countBad}>
              <strong>{preview.counts.invalid}</strong>
              <span>invalid</span>
            </div>
            <div className={styles.countWarn}>
              <strong>{preview.counts.duplicates}</strong>
              <span>duplicates</span>
            </div>
          </div>

          <div className={styles.tableWrap}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Date</th>
                  <th>Description</th>
                  <th className="amount-cell">Amount</th>
                  <th>Account</th>
                  <th>Category</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.slice(0, 12).map((row) => (
                  <tr key={row.row_number}>
                    <td className="muted-label">{row.row_number}</td>
                    <td>{row.date ?? <span className="muted-label">—</span>}</td>
                    <td>{row.description || <span className="muted-label">—</span>}</td>
                    <td className={`amount-cell ${row.amount === null ? "" : row.type === "income" ? "positive" : "negative"}`}>
                      {row.amount === null ? "—" : row.amount.toFixed(2)}
                    </td>
                    <td>
                      {row.account_name ?? <span className="muted-label">—</span>}
                      {row.duplicate && <span className="chip chip-warning">dup</span>}
                    </td>
                    <td>
                      {row.category_name ? (
                        <span className={`chip ${row.category_state === "new" ? "chip-income" : "chip-neutral"}`}>
                          {row.category_name}
                        </span>
                      ) : (
                        <span className="muted-label">—</span>
                      )}
                    </td>
                    <td>
                      {row.valid ? (
                        <span className={`chip ${row.type === "income" ? "chip-income" : "chip-expense"}`}>
                          {row.type}
                        </span>
                      ) : (
                        <span className="chip chip-warning">invalid</span>
                      )}
                      {!row.valid && row.errors.length > 0 && (
                        <p className={styles.rowErrors}>
                          Row {row.row_number}: {row.errors.join(" · ")}
                        </p>
                      )}
                      {row.duplicate && <p className={styles.rowErrors}>Duplicate of a transaction already in your ledger.</p>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className={styles.fileHint}>
            Showing the first {Math.min(preview.rows.length, 12)} of {preview.rows.length} rows.
            Invalid rows and duplicates are skipped on commit.
          </p>

          <div className={styles.actions}>
            <Button variant="ghost" onClick={() => setStep("mapping")} disabled={working}>
              Back
            </Button>
            <Button
              onClick={runCommit}
              loading={working && busy.includes("commit")}
              disabled={preview.counts.valid === 0}
            >
              Commit {preview.counts.valid} transaction{preview.counts.valid === 1 ? "" : "s"}
            </Button>
          </div>
        </>
      )}

      {step === "done" && commit && (
        <>
          <div className={styles.counts}>
            <div className={styles.countGood}>
              <strong>{commit.counts.created}</strong>
              <span>created</span>
            </div>
            <div className={styles.countWarn}>
              <strong>{commit.counts.skipped_duplicates}</strong>
              <span>duplicates skipped</span>
            </div>
            <div className={styles.countBad}>
              <strong>{commit.counts.skipped_invalid}</strong>
              <span>invalid skipped</span>
            </div>
            {commit.counts.categories_created > 0 && (
              <div className={styles.count}>
                <strong>{commit.counts.categories_created}</strong>
                <span>categories created</span>
              </div>
            )}
          </div>

          {commit.errors.length > 0 && (
            <div className={styles.commitErrors}>
              {commit.errors.map((entry) => (
                <p key={entry.row_number}>
                  Row {entry.row_number}: {entry.errors.join(" · ")}
                </p>
              ))}
            </div>
          )}

          <div className={styles.actions}>
            <Button onClick={onClose}>Done</Button>
          </div>
        </>
      )}
    </Modal>
  );
}