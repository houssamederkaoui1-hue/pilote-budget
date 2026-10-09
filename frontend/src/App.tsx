import type { ComponentType } from "react";
import { useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { SignInOverlay } from "./components/auth/SignInOverlay";
import { DashboardPage } from "./pages/DashboardPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";
import { AccountsPage } from "./pages/AccountsPage";
import { CategoriesPage } from "./pages/CategoriesPage";
import { TransactionsPage } from "./pages/TransactionsPage";
import { BudgetsPage } from "./pages/BudgetsPage";
import { GoalsPage } from "./pages/GoalsPage";
import { RecurringPage } from "./pages/RecurringPage";
import { DebtsPage } from "./pages/DebtsPage";
import { AssistantPage } from "./pages/AssistantPage";
import { SettingsPage } from "./pages/SettingsPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { NAV_ITEMS } from "./lib/navigation";
import { apiGet } from "./lib/api";
import { getAuthToken, subscribeAuth } from "./lib/auth";

/** Paths that have a real implementation; everything else is a scaffold. */
const READY_PAGES: Record<string, ComponentType> = {
  "/transactions": TransactionsPage,
  "/accounts": AccountsPage,
  "/categories": CategoriesPage,
  "/budgets": BudgetsPage,
  "/goals": GoalsPage,
  "/recurring": RecurringPage,
  "/debts": DebtsPage,
  "/assistant": AssistantPage,
  "/settings": SettingsPage,
};

interface PublicConfig {
  app: string;
  version: string;
  environment: string;
  api_prefix: string;
  auth_required: boolean;
}

export default function App() {
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [authError, setAuthError] = useState(false);
  const [token, setToken] = useState<string | null>(getAuthToken());

  // Reload the (public) bootstrap config whenever the token changes so a
  // fresh session re-checks whether auth is now required.
  useEffect(() => {
    let active = true;
    apiGet<PublicConfig>("/config")
      .then((cfg) => {
        if (active) setConfig(cfg);
      })
      .catch(() => {
        // Backend unreachable: fall back to an open app; screens keep their
        // own offline/error banners rather than blocking the whole UI.
        if (active) setConfig({ auth_required: false } as PublicConfig);
      });
    return () => {
      active = false;
    };
  }, [token]);

  useEffect(() => {
    const onChange = () => setToken(getAuthToken());
    return subscribeAuth(onChange);
  }, []);

  useEffect(() => {
    const onUnauthorized = () => setAuthError(true);
    window.addEventListener("pilote:unauthorized", onUnauthorized);
    return () => window.removeEventListener("pilote:unauthorized", onUnauthorized);
  }, []);

  const needsToken = Boolean(config?.auth_required) && token === null;

  return (
    <>
      {needsToken && <SignInOverlay error={authError} />}
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<DashboardPage />} />
          {NAV_ITEMS.filter((item) => item.path !== "/").map((item) => {
            const Page = READY_PAGES[item.path] ?? PlaceholderPage;
            return <Route key={item.path} path={item.path} element={<Page />} />;
          })}
          <Route path="/onboarding" element={<OnboardingPage />} />
          <Route path="*" element={<PlaceholderPage />} />
        </Route>
      </Routes>
    </>
  );
}