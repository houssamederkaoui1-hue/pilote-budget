import { useState } from "react";
import { Link } from "react-router-dom";
import { setAuthToken } from "../../lib/auth";
import styles from "./SignInOverlay.module.css";

interface SignInOverlayProps {
  error?: boolean;
}

/**
 * Full-screen gate shown when the backend has an access token configured and
 * the visitor has not provided one yet. The token is kept in sessionStorage
 * (never persisted, cleared when the browser tab closes).
 */
export function SignInOverlay({ error = false }: SignInOverlayProps) {
  const [value, setValue] = useState("");

  return (
    <div className={styles.gate} role="presentation">
      <div className={styles.card} role="dialog" aria-modal="true" aria-label="Sign in">
        <div className={styles.brand}>Pilote Budget</div>
        <h1 className={styles.title}>Sign in</h1>
        <p className={styles.subtitle}>
          This installation is protected. Enter your access token to continue.
        </p>
        {error && (
          <div className={styles.error} role="alert">
            That token was rejected by the server. Check it and try again.
          </div>
        )}
        <form
          className={styles.form}
          onSubmit={(event) => {
            event.preventDefault();
            if (value.trim()) setAuthToken(value);
          }}
        >
          <label htmlFor="access-token" className={styles.label}>
            Access token
          </label>
          <input
            id="access-token"
            type="password"
            autoComplete="current-password"
            className={styles.input}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder="••••••••••••"
            autoFocus
            required
          />
          <button type="submit" className={styles.submit} disabled={!value.trim()}>
            Unlock
          </button>
        </form>
        <p className={styles.subtitle}>
          <Link to="/firebase/login">
            Try the read-only Firebase preview →
          </Link>
        </p>
      </div>
    </div>
  );
}