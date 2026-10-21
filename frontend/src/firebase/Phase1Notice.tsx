import styles from "./Firebase.module.css";

/**
 * Phase 1 is READ-ONLY. Anything that mutates the ledger or requires a trusted
 * server is deliberately not implemented in the Firebase path and is listed
 * here so users are never misled into relying on it.
 */
export const UNAVAILABLE_OPERATIONS: string[] = [
  "Creating, editing or deleting transactions",
  "Transfers between accounts (needs two-row atomicity)",
  "Recurring transaction materialisation (needs a server scheduler)",
  "Writing cached balances / mutating the single-source snapshot",
  "CSV import commit and duplicate-proof batching",
  "Backup restore with envelope validation",
  "The financial assistant / any server-side reasoning",
];

export function Phase1Notice() {
  return (
    <div className={styles.card} style={{ maxWidth: "none" }}>
      <div className={styles.brand}>Read-only preview</div>
      <p className={styles.subtitle} style={{ marginBottom: 0 }}>
        This Firebase view only <strong>reads</strong> imported data. It is not
        a replacement for the main app. The following operations are not
        available here yet (see{" "}
        <code>FIREBASE_MIGRATION_PLAN.md</code>):
      </p>
      <ul className={styles.noticeList}>
        {UNAVAILABLE_OPERATIONS.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}