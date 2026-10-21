/** Single source of truth for navigation + routed sections. */

import type { ComponentType } from "react";
import {
  AnalyticsIcon,
  BudgetsIcon,
  DebtsIcon,
  DashboardIcon,
  GoalsIcon,
  RecurringIcon,
  SettingsIcon,
  TransactionsIcon,
  AccountsIcon,
  CategoriesIcon,
  BulbIcon,
} from "../components/icons";

export type NavStatus = "ready" | "planned";

/** Sidebar sections; items are grouped by this field (order preserved). */
export type NavGroup = "overview" | "planning" | "insights";

export interface NavItem {
  path: string;
  label: string;
  eyebrow?: string;
  description: string;
  icon: ComponentType<{ size?: number }>;
  status: NavStatus;
  group: NavGroup;
  /** What this section will contain in later phases. */
  features: string[];
}

export const NAV_ITEMS: NavItem[] = [
  {
    path: "/",
    label: "Dashboard",
    description: "Your financial cockpit at a glance.",
    icon: DashboardIcon,
    status: "ready",
    group: "overview",
    features: [
    "KPI summary row",
    "Spending trend + category charts",
    "Safe-to-Spend and net worth roll-ups",
    "Deterministic financial insights",
    ],
  },
  {
    path: "/transactions",
    label: "Transactions",
    description: "Manual entry, quick entry and CSV import.",
    icon: TransactionsIcon,
    status: "ready",
    group: "overview",
    features: [
    "Manual and quick transaction entry",
    "CSV import/export with dedupe",
    "Filters, search and status workflow",
    "Transfer posting to the ledger",
    ],
  },
  {
    path: "/accounts",
    label: "Accounts",
    description: "Bank, cash and credit accounts with balances.",
    icon: AccountsIcon,
    status: "ready",
    group: "overview",
    features: [
    "Bank, cash, credit and investment accounts",
    "Opening vs running balance model",
    "Per-account filters and reconciliation",
    "Account-level analytics",
    ],
  },
  {
    path: "/categories",
    label: "Categories",
    description: "Income and expense categories with hierarchy.",
    icon: CategoriesIcon,
    status: "ready",
    group: "overview",
    features: [
      "Income and expense category trees",
      "Archive instead of delete for used rows",
      "Duplicate-name guards per type",
      "Seeded starter set",
    ],
  },
  {
    path: "/budgets",
    label: "Budgets",
    description: "Monthly category plans and budget health.",
    icon: BudgetsIcon,
    status: "ready",
    group: "planning",
    features: [
    "Monthly category plans",
    "Planned vs actual tracking",
    "Budget health scoring",
    "Month-start period alignment",
    ],
  },
  {
    path: "/goals",
    label: "Goals",
    description: "Savings targets, progress and deadlines.",
    icon: GoalsIcon,
    status: "ready",
    group: "planning",
    features: [
    "Savings targets with deadlines",
    "Manual or account-backed progress",
    "Contribution schedules",
    "Goal funding priority",
    ],
  },
  {
    path: "/recurring",
    label: "Recurring",
    description: "Scheduled income, expenses and transfers.",
    icon: RecurringIcon,
    status: "ready",
    group: "planning",
    features: [
    "Scheduled income and expenses",
    "Frequency and next occurrence engine",
    "Auto-posting with audit trail",
    "Pause and edit history",
    ],
  },
  {
    path: "/debts",
    label: "Debts",
    description: "Loans, cards, interest and payoff tracking.",
    icon: DebtsIcon,
    status: "ready",
    group: "planning",
    features: [
    "Loans and credit card balances",
    "APR, minimums and due dates",
    "Payoff projections",
    "Debt snowball/avalanche views",
    ],
  },
  {
    path: "/assistant",
    label: "Assistant",
    description: "Deterministic answers and insights from your ledger.",
    icon: BulbIcon,
    status: "ready",
    group: "insights",
    features: [
      "Deterministic, rules-driven insights",
      "Prioritized findings per period",
      "Ask questions about goals, budgets, savings",
      "Estimates always labeled as estimates",
    ],
  },
  {
    path: "/analytics",
    label: "Analytics",
    description: "Trends, forecasts and deterministic insights.",
    icon: AnalyticsIcon,
    status: "ready",
    group: "insights",
    features: [
    "Trend and category analysis",
    "Cashflow forecasting",
    "Safe-to-Spend simulation",
    "Optional AI assistant hooks",
    ],
  },
  {
    path: "/settings",
    label: "Settings",
    description: "Currency, month start and financial preferences.",
    icon: SettingsIcon,
    status: "ready",
    group: "insights",
    features: [
    "Currency and locale",
    "Month start day configuration",
    "Financial preferences",
    "Data export and maintenance",
    ],
  },
];
