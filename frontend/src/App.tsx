import type { ComponentType } from "react";
import { Route, Routes } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
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
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { NAV_ITEMS } from "./lib/navigation";

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
  "/analytics": AnalyticsPage,
  "/settings": SettingsPage,
};

export default function App() {
  return (
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
  );
}
