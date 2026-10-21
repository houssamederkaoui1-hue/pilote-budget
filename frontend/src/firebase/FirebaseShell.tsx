import { Link, NavLink, Outlet } from "react-router-dom";
import { useFirebaseAuth } from "./auth";
import { Phase1Notice } from "./Phase1Notice";
import { useOnline } from "./repo";
import styles from "./Firebase.module.css";

const NAV = [
  { to: "/firebase/dashboard", label: "Dashboard" },
  { to: "/firebase/accounts", label: "Accounts" },
  { to: "/firebase/categories", label: "Categories" },
  { to: "/firebase/transactions", label: "Transactions" },
];

export function FirebaseShell() {
  const { user, signOut, uid } = useFirebaseAuth();

  return (
    <div className={styles.shell}>
      <header className={styles.topbar}>
        <Link className={styles.link} to="/" title="FastAPI / SQLite app">
          ← FastAPI app
        </Link>
        <span className={styles.topbarBrand}>
          Pilote Budget <span className={styles.pill}>Firebase · Phase 1</span>
        </span>
        <span className={styles.spacer} />
        {user && (
          <>
            <span className={styles.userEmail}>{user.email}</span>
            <span className={styles.chip} title={`UID ${uid}`}>
              read-only
            </span>
            <button
              type="button"
              className={`${styles.button} ${styles.buttonSecondary}`}
              style={{ padding: "7px 12px" }}
              onClick={() => void signOut().catch(() => undefined)}
            >
              Sign out
            </button>
          </>
        )}
      </header>

      <nav className={styles.nav}>
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `${styles.navLink} ${isActive ? styles.navLinkActive : ""}`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      <OfflineBanner />
      <div className={styles.bannerReadonly}>
        Read-only preview: data below is displayed from Firestore under your
        UID. Writes are intentionally disabled in Phase 1.
      </div>

      <main className={styles.content}>
        <Phase1Notice />
        <Outlet />
      </main>
    </div>
  );
}

function OfflineBanner() {
  const { uid } = useFirebaseAuth();
  const online = useOnline();
  if (online) return null;
  return (
    <div className={styles.bannerOffline} style={{ display: uid ? undefined : "none" }}>
      You are offline — showing the last cached Firestore data (document id{" "}
      {uid ? `users/${uid}` : "…"}).
    </div>
  );
}