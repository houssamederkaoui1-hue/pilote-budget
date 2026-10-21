import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { ErrorState, LoadingState } from "../components/ui/States";
import {
  FirebaseAuthProvider,
  useFirebaseAuth,
} from "./auth";
import { FirebaseShell } from "./FirebaseShell";
import {
  AccountsPage,
  CategoriesPage,
  DashboardPage,
  TransactionsPage,
} from "./FirebaseViews";
import { LoginPage } from "./LoginPage";
import { NotConfigured } from "./NotConfigured";
import { resolveFirebaseRedirect } from "./gate";
import styles from "./Firebase.module.css";

export default function FirebaseApp() {
  return (
    <FirebaseAuthProvider>
      <FirebaseAppInner />
    </FirebaseAuthProvider>
  );
}

function FirebaseAppInner() {
  const { gate, runtimeError, user } = useFirebaseAuth();
  const location = useLocation();

  if (gate === "not-configured") return <NotConfigured />;
  if (gate === "error") {
    return (
      <div className={styles.page}>
        <div className={styles.centre}>
          <ErrorState
            title="Firebase failed to start"
            message={`${runtimeError} — check the VITE_FIREBASE_* build configuration and your browser's storage settings, then reload.`}
          />
        </div>
      </div>
    );
  }
  if (gate === "loading") {
    return (
      <div className={styles.page}>
        <div className={styles.centre}>
          <LoadingState label="Starting Firebase…" />
        </div>
      </div>
    );
  }

  // Gate is "ready": auth state is known. Only now may we redirect, so a deep
  // link or hard refresh keeps its intended URL through initialisation.
  const redirect = resolveFirebaseRedirect(location.pathname, gate, user !== null);
  if (redirect) return <Navigate to={redirect} replace />;

  return (
    <Routes>
      <Route path="login" element={<LoginPage />} />
      <Route element={<FirebaseShell />}>
        <Route index element={<Navigate to="dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="accounts" element={<AccountsPage />} />
        <Route path="categories" element={<CategoriesPage />} />
        <Route path="transactions" element={<TransactionsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/firebase/login" replace />} />
    </Routes>
  );
}