import { useCallback, useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { QuickAdd } from "../transactions/QuickAdd";
import { MenuIcon, ActivityIcon, AlertIcon, PlusIcon } from "../icons";
import { NAV_ITEMS } from "../../lib/navigation";
import { useHealth } from "../../hooks/useHealth";
import { useApi } from "../../hooks/useApi";
import { currentPeriodLine } from "../../lib/dashboard";
import type { OnboardingResponse, ProfileResponse } from "../../types/api";
import styles from "./AppShell.module.css";

export function AppShell() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [quickOpen, setQuickOpen] = useState(false);
  const location = useLocation();
  const health = useHealth();
  const profile = useApi<ProfileResponse>("/profile");
  const onboarding = useApi<OnboardingResponse>("/settings/onboarding");

  const closeSidebar = useCallback(() => setSidebarOpen(false), []);

  useEffect(() => {
    closeSidebar();
  }, [location.pathname, closeSidebar]);

  const pageTitle =
    NAV_ITEMS.find((item) => item.path === location.pathname)?.label ?? "Pilote Budget";

  const periodLine = profile.data
    ? currentPeriodLine(profile.data.month_start_day)
    : null;

  const needsOnboarding =
    !onboarding.loading &&
    !!onboarding.data &&
    !onboarding.data.skipped &&
    !onboarding.data.completed;

  return (
    <div className="app-shell">
      <Sidebar open={sidebarOpen} onClose={closeSidebar} />

      <div className="app-main">
        <header className={styles.topbar}>
          <button
            type="button"
            className={styles.menuButton}
            onClick={() => setSidebarOpen(true)}
            aria-label="Open navigation"
          >
            <MenuIcon size={19} />
          </button>

          <div className={styles.topbarTitle}>{pageTitle}</div>

          <div className={styles.topbarRight}>
            <button
              type="button"
              className={styles.quickAdd}
              onClick={() => setQuickOpen(true)}
              title="Quick add a transaction"
            >
              <PlusIcon size={15} />
              Quick add
            </button>
            <StatusLabel health={health} />
            {periodLine && <span className={styles.period}>{periodLine}</span>}
          </div>
        </header>

        {needsOnboarding && (
          <div className={styles.onboardingBanner}>
            <span>
              You're almost set up — pick an account, a category and a budget target.
            </span>
            <Link to="/onboarding" className={styles.onboardingLink} onClick={() => setQuickOpen(false)}>
              Continue setup →
            </Link>
          </div>
        )}

        <main className="app-content">
          <Outlet />
        </main>
      </div>

      {quickOpen && <QuickAdd onClose={() => setQuickOpen(false)} />}
    </div>
  );
}

function StatusLabel({
  health,
}: {
  health: ReturnType<typeof useHealth>;
}) {
  if (health.loading) {
    return <span className={`${styles.apiStatus} ${styles.apiPending}`}>Connecting…</span>;
  }
  if (health.error || !health.data) {
    return (
      <span className={`${styles.apiStatus} ${styles.apiDown}`} title={health.error ?? ""}>
        <AlertIcon size={13} />
        API offline
      </span>
    );
  }
  return (
    <span
      className={`${styles.apiStatus} ${health.data.status === "ok" ? styles.apiOk : styles.apiWarn}`}
      title={`API ${health.data.version} · ${health.data.database.dialect}`}
    >
      <ActivityIcon size={13} />
      {health.data.status === "ok" ? "API connected" : "API degraded"}
    </span>
  );
}
