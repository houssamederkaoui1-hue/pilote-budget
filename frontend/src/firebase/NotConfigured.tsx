import { Link } from "react-router-dom";
import styles from "./Firebase.module.css";

/**
 * Shown when the public VITE_FIREBASE_* variables are absent. The legacy
 * FastAPI app is unaffected; this only disables the optional Firebase path.
 */
export function NotConfigured() {
  return (
    <div className={styles.page}>
      <div className={styles.centre}>
        <div className={styles.card}>
          <div className={styles.brand}>Firebase path</div>
          <h1 className={styles.title}>Not configured</h1>
          <p className={styles.subtitle}>
            This optional Firebase-backed path is disabled because the public
            web config is missing. Set the{" "}
            <code>VITE_FIREBASE_API_KEY</code>,{" "}
            <code>VITE_FIREBASE_AUTH_DOMAIN</code> and{" "}
            <code>VITE_FIREBASE_PROJECT_ID</code> build variables (see{" "}
            <code>frontend/.env.example</code>) and rebuild.
          </p>
          <p className={styles.subtitle}>
            Only the public web config is used here — never a service-account
            key. The existing FastAPI app remains fully functional.
          </p>
          <Link className={styles.link} to="/">
            ← Return to the FastAPI app
          </Link>
        </div>
      </div>
    </div>
  );
}