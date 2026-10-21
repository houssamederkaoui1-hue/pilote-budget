import { useState, type FormEvent } from "react";
import { Link, Navigate } from "react-router-dom";
import { useFirebaseAuth } from "./auth";
import styles from "./Firebase.module.css";

function friendlyAuthError(error: unknown): string {
  const code =
    error && typeof error === "object" && "code" in error
      ? String((error as { code: unknown }).code)
      : "";
  switch (code) {
    case "auth/invalid-email":
      return "That email address is not valid.";
    case "auth/missing-password":
      return "Please enter your password.";
    case "auth/weak-password":
      return "Choose a password with at least 6 characters.";
    case "auth/email-already-in-use":
      return "An account already exists for that email. Try signing in.";
    case "auth/invalid-credential":
    case "auth/wrong-password":
    case "auth/user-not-found":
      return "Email or password is incorrect.";
    case "auth/too-many-requests":
      return "Too many attempts. Please wait and try again.";
    case "auth/network-request-failed":
      return "Network error. Check your connection and try again.";
    default:
      return error instanceof Error ? error.message : "Sign-in failed.";
  }
}

export function LoginPage() {
  const { user, signIn, createAccount } = useFirebaseAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/firebase/dashboard" replace />;

  async function run(action: (email: string, password: string) => Promise<void>) {
    setError(null);
    setBusy(true);
    try {
      await action(email, password);
    } catch (err) {
      setError(friendlyAuthError(err));
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void run(signIn);
  }

  return (
    <div className={styles.page}>
      <div className={styles.centre}>
        <div className={styles.card}>
          <div className={styles.brand}>Pilote Budget · Firebase</div>
          <h1 className={styles.title}>Sign in</h1>
          <p className={styles.subtitle}>
            Email/password via Firebase Authentication. This is a read-only
            preview of imported Firestore data.
          </p>

          {error && (
            <div className={styles.errorBox} role="alert" style={{ marginBottom: 16 }}>
              {error}
            </div>
          )}

          <form className={styles.form} onSubmit={onSubmit}>
            <div>
              <label className={styles.label} htmlFor="fb-email">
                Email
              </label>
              <input
                id="fb-email"
                className={styles.input}
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>
            <div>
              <label className={styles.label} htmlFor="fb-password">
                Password
              </label>
              <input
                id="fb-password"
                className={styles.input}
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </div>
            <button className={styles.button} type="submit" disabled={busy}>
              {busy ? "Please wait…" : "Sign in"}
            </button>
            <button
              className={`${styles.button} ${styles.buttonSecondary}`}
              type="button"
              disabled={busy}
              onClick={() => void run(createAccount)}
            >
              Create account
            </button>
          </form>

          <p style={{ marginTop: 18, marginBottom: 0 }}>
            <Link className={styles.link} to="/">
              ← Return to the FastAPI app
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}