/** Types mirroring the backend API contracts. */

export interface DatabaseStatus {
  connected: boolean;
  dialect: string | null;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  app: string;
  version: string;
  environment: string;
  database: DatabaseStatus;
  time: string;
}

export interface ProfileResponse {
  id: number;
  currency: string;
  month_start_day: number;
  timezone: string;
  preferences: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

/* ---- Phase 2: accounts, categories, transactions, imports --------------- */

export type AccountType =
  | "bank"
  | "checking"
  | "savings"
  | "cash"
  | "credit_card"
  | "debit_card"
  | "investment"
  | "loan"
  | "other";

export interface Account {
  id: number;
  name: string;
  type: AccountType;
  opening_balance: number;
  current_balance: number;
  currency: string | null;
  active: boolean;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export type CategoryType = "income" | "expense";

export interface Category {
  id: number;
  name: string;
  type: CategoryType;
  parent_id: number | null;
  active: boolean;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export type TransactionEntity = "transaction" | "transfer";
export type TransactionKind = "income" | "expense" | "transfer";
export type TransactionStatusValue =
  | "pending"
  | "cleared"
  | "reconciled"
  | "void"
  | "completed"
  | "cancelled";

export interface TransactionRow {
  id: number;
  entity: TransactionEntity;
  type: TransactionKind;
  amount: number;
  date: string;
  description: string;
  notes: string | null;
  status: TransactionStatusValue;
  account_id: number;
  account_name: string | null;
  category_id: number | null;
  category_name: string | null;
  destination_account_id: number | null;
  destination_account_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface TransactionList {
  items: TransactionRow[];
  total: number;
  limit: number;
  offset: number;
}

export interface Summary {
  income: number;
  expense: number;
  net: number;
  transfer_volume: number;
}

export interface MessageResponse {
  message: string;
}

/* ---- CSV import --------------------------------------------------------- */

export interface ImportInspect {
  filename: string | null;
  encoding: string;
  delimiter: string;
  columns: string[];
  sample_rows: string[][];
  row_count: number;
  suggestions: Record<string, { column: number | null; format?: string | null } | null>;
  date_formats: string[];
  date_format_candidates: string[];
}

export interface PreviewRow {
  row_number: number;
  date: string | null;
  description: string;
  amount: number | null;
  type: string;
  category_name: string | null;
  account_name: string | null;
  reference: string | null;
  errors: string[];
  valid: boolean;
  raw: string[];
  account_id: number | null;
  category_state: "existing" | "new" | "none";
  dedupe_key: string | null;
  duplicate: boolean;
}

export interface ImportPreview {
  filename: string | null;
  columns: string[];
  rows: PreviewRow[];
  counts: { total: number; valid: number; invalid: number; duplicates: number };
}

export interface ImportCommit {
  batch_id: string;
  filename: string | null;
  counts: {
    total: number;
    created: number;
    skipped_duplicates: number;
    skipped_invalid: number;
    categories_created: number;
  };
  accounts_touched: number[];
  errors: { row_number: number; errors: string[] }[];
}

export interface FieldColumn {
  column: number | null;
  format?: string | null;
}

export interface ImportOptions {
  encoding?: string;
  decimal_separator?: "." | "," | "auto";
  amount_mode?: "auto" | "income" | "expense" | "flip";
  positive_is?: "income" | "expense";
  default_account_id?: number | null;
  default_category_id?: number | null;
  filename?: string | null;
}

export interface ImportMapping {
  fields: Record<string, FieldColumn>;
  options: ImportOptions;
}

/* ---- Phase 3: budgets, goals, recurring, debts, overview ----------------- */

export interface AllocationPut {
  income?: number | null;
  needs?: number | null;
  wants?: number | null;
  savings?: number | null;
  other?: number | null;
}

export interface BudgetItemPut {
  category_id: number;
  planned_amount: number;
  notes?: string | null;
}

export interface BudgetPut {
  allocation: AllocationPut | null;
  items: BudgetItemPut[];
}

export interface AllocationStats {
  income_amount: number;
  planned_total: number;
  actual_total: number;
  remaining_total: number;
  pct_used: number | null;
  over_budget: boolean;
  has_allocation: boolean;
  needs_amount: number;
  wants_amount: number;
  savings_amount: number;
  other_amount: number;
}

export type BudgetStatus = "over" | "approaching" | "healthy" | "none";

export interface BudgetItemStats {
  category_id: number;
  category_name: string;
  planned_amount: number;
  actual_amount: number;
  remaining_amount: number;
  pct_used: number | null;
  over_budget: boolean;
  status: BudgetStatus;
  notes: string | null;
}

export interface BudgetTotals {
  planned: number;
  actual: number;
  remaining: number;
  pct_used: number | null;
  over_budget: boolean;
}

export interface BudgetResponse {
  period_start: string;
  period_end: string;
  month_start_day: number;
  allocation: AllocationStats;
  items: BudgetItemStats[];
  totals: BudgetTotals;
  approaching: number[];
  exceeding: number[];
}

export interface Goal {
  id: number;
  name: string;
  target_amount: number;
  current_amount: number;
  target_date: string | null;
  account_id: number | null;
  account_name: string | null;
  active: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
  progress_pct: number;
  remaining_amount: number;
  required_monthly_saving: number | null;
  monthly_contribution: number | null;
  estimated_completion_date: string | null;
}

export type Frequency =
  | "daily"
  | "weekly"
  | "biweekly"
  | "monthly"
  | "quarterly"
  | "yearly";

export interface RecurringTemplate {
  id: number;
  account_id: number;
  account_name: string | null;
  category_id: number | null;
  category_name: string | null;
  type: TransactionKind;
  amount: number;
  frequency: Frequency;
  next_occurrence: string;
  end_date: string | null;
  description: string;
  notes: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface RecurringOccurrence {
  recurring_id: number;
  due_date: string;
  overdue: boolean;
  type: TransactionKind;
  amount: number;
  frequency: Frequency;
  description: string;
  account_id: number;
  account_name: string | null;
  category_id: number | null;
  category_name: string | null;
  end_date: string | null;
}

export interface UpcomingResponse {
  as_of: string;
  horizon_days: number;
  horizon_end: string;
  occurrences: RecurringOccurrence[];
}

export interface RecordResponse {
  recurring_id: number;
  date: string;
  next_occurrence: string;
  deactivated: boolean;
  template: RecurringTemplate;
}

export interface Debt {
  id: number;
  name: string;
  creditor: string | null;
  original_amount: number;
  remaining_amount: number;
  interest_rate: number | null;
  minimum_payment: number | null;
  due_date: string | null;
  account_id: number | null;
  account_name: string | null;
  active: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface UpcomingDue {
  debt_id: number;
  name: string;
  due_date: string;
  remaining_amount: number;
  minimum_payment: number | null;
}

export interface DebtTotals {
  total_original: number;
  total_remaining: number;
  total_minimum_payment: number;
  active_debt_count: number;
  upcoming_due_dates: UpcomingDue[];
}

export interface Overview {
  total_assets: number;
  total_liabilities: number;
  net_worth: number;
  account_assets: number;
  account_liabilities: number;
  debt_liabilities: number;
}

/* ---- Analytics: dashboard summary, forecasts, health, Safe-to-Spend ----- */

export interface PeriodWindow {
  period_start: string;
  period_end: string;
  closed: boolean;
}

export interface FlowSummary {
  current: number;
  previous: number;
  change_pct: number | null;
  trend: "up" | "down" | "flat" | "none";
}

export type SavingsRateStatus = "positive" | "neutral" | "negative" | "insufficient";

export interface SavingsSummary {
  current: number;
  previous: number;
  change_pct: number | null;
  rate: number | null;
  rate_status: SavingsRateStatus;
  historical_rate: number | null;
}

export interface CategoryBreakdown {
  category_id: number | null;
  category_name: string | null;
  amount: number;
  share_pct: number | null;
  change_pct: number | null;
}

export interface NetWorth {
  assets: number;
  liabilities: number;
  net_worth: number;
  net_worth_including_debts: number;
  previous: number | null;
  change_pct: number | null;
}

export interface NetWorthHistoryPoint {
  period_start: string;
  period_end: string;
  closed: boolean;
  assets: number;
  liabilities: number;
  net_worth: number;
}

export interface PeriodPoint {
  period_start: string;
  period_end: string;
  closed: boolean;
  income: number;
  expense: number;
  net: number;
  savings_rate: number | null;
}

export interface ForecastMetric {
  actual: number;
  estimated: number | null;
  is_estimate: boolean;
}

export interface BalanceForecast {
  opening: number;
  current: number;
  estimated_end: number | null;
  is_estimate: boolean;
}

export interface Forecasts {
  spending: ForecastMetric;
  income: ForecastMetric;
  savings: ForecastMetric;
  available: BalanceForecast;
  note: string;
}

export interface FinancialHealth {
  savings_rate: number | null;
  savings_rate_status: SavingsRateStatus;
  budget_pct_used: number | null;
  budget_over: boolean;
  recurring_expense_ratio: number | null;
  recurring_expense_ratio_status: "low" | "moderate" | "high" | null;
  debt_burden: number | null;
  debt_burden_status: "low" | "moderate" | "high" | null;
  cashflow_net: number;
  cashflow_status: "positive" | "negative" | "neutral";
  cashflow_streak: number;
  upcoming_obligations_count: number;
  upcoming_obligations_amount: number;
}

export type InsightTone = "accent" | "positive" | "negative" | "warning" | "neutral";

export interface Insight {
  key: string;
  title: string;
  description: string;
  tone: InsightTone;
}

export interface AnalyticsResponse {
  as_of: string;
  period: PeriodWindow;
  previous_period: PeriodWindow;
  month_start_day: number;
  currency: string;
  has_data: boolean;
  transactions_count: number;
  income: FlowSummary;
  expenses: FlowSummary;
  savings: SavingsSummary;
  categories: CategoryBreakdown[];
  net_worth: NetWorth;
  net_worth_history: NetWorthHistoryPoint[];
  budget: BudgetResponse;
  history: PeriodPoint[];
  forecasts: Forecasts;
  health: FinancialHealth;
  insights: Insight[];
}

export interface SafeToSpendCommitment {
  kind: "recurring" | "debt";
  description: string | null;
  amount: number;
  due_date: string | null;
}

export interface SafeToSpendResponse {
  status: "ok" | "insufficient";
  reason: string | null;
  is_estimate: boolean;
  available_money: number | null;
  obligations: SafeToSpendCommitment[];
  obligations_total: number | null;
  planned_savings: number | null;
  reserve_amount: number | null;
  committed_total: number | null;
  discretionary: number | null;
  remaining_days: number | null;
  safe_to_spend_daily: number | null;
  explanation: string;
  disclaimer: string;
}

/* ---- Financial Assistant: deterministic insights + Q&A ------------------- */

export type InsightSeverity = "info" | "warning" | "critical" | "success";

export interface InsightMetric {
  kind: string;
  label: string | null;
  current: number | null;
  previous: number | null;
  change_pct: number | null;
  unit: string;
}

export interface AssistantInsight {
  id: string;
  severity: InsightSeverity;
  category: string;
  title: string;
  explanation: string;
  metric: InsightMetric | null;
  actionable: boolean;
  priority: number;
  generated_at: string | null;
}

export interface AssistantQuestion {
  intent: string;
  question: string;
}

export interface AssistantPeriod {
  period_start: string;
  period_end: string;
}

export interface AssistantOverviewResponse {
  provider: string;
  provider_name: string;
  generated_at: string;
  period: AssistantPeriod;
  currency: string;
  has_data: boolean;
  greeting: string;
  overview: string;
  insights: AssistantInsight[];
  questions: AssistantQuestion[];
}

export interface AssistantAskRequest {
  question: string;
  intent?: string | null;
  goal_id?: number | null;
}

export interface AssistantFact {
  label: string;
  value: number | string | null;
  display: string;
}

export type AssistantSource = "ledger" | "plan" | "estimate" | "assistant";

export interface AssistantAskResponse {
  intent: string;
  question: string;
  recognized: boolean;
  answer: string;
  estimate: boolean;
  source: AssistantSource;
  facts: AssistantFact[];
  metric: InsightMetric | null;
  generated_at: string | null;
}

/* ---- Phase 7: settings, on-boarding, backup, Quick Add ------------------ */

export type DashboardPeriod = "current" | "last_three";

export type DashboardSectionId =
  | "stats"
  | "cash_flow"
  | "category_spending"
  | "net_worth"
  | "budget_vs_actual"
  | "safe_to_spend"
  | "forecast"
  | "financial_health"
  | "insights"
  | "goals"
  | "upcoming_bills"
  | "debts";

export const DASHBOARD_SECTION_META: { id: DashboardSectionId; label: string }[] = [
  { id: "stats", label: "Overview cards" },
  { id: "cash_flow", label: "Cash flow" },
  { id: "category_spending", label: "Spending by category" },
  { id: "net_worth", label: "Net worth" },
  { id: "budget_vs_actual", label: "Budget vs actual" },
  { id: "safe_to_spend", label: "Safe-to-Spend" },
  { id: "forecast", label: "Forecast" },
  { id: "financial_health", label: "Financial health" },
  { id: "insights", label: "Financial insights" },
  { id: "goals", label: "Goals" },
  { id: "upcoming_bills", label: "Upcoming recurring expenses" },
  { id: "debts", label: "Debt summary" },
];

export interface DashboardPreferences {
  period: DashboardPeriod;
  sections: Record<DashboardSectionId, boolean>;
  order: DashboardSectionId[];
}

export interface AssistantPreferences {
  verbosity: "concise" | "standard";
}

export interface SettingsResponse {
  currency: string;
  month_start_day: number;
  timezone: string;
  minimum_reserve: number;
  default_account_id: number | null;
  default_expense_category_id: number | null;
  default_income_category_id: number | null;
  dashboard: DashboardPreferences;
  assistant: AssistantPreferences;
  updated_at: string;
}

export interface SettingsUpdate {
  currency?: string;
  month_start_day?: number;
  timezone?: string;
  minimum_reserve?: number;
  default_account_id?: number | null;
  default_expense_category_id?: number | null;
  default_income_category_id?: number | null;
  dashboard?: DashboardPreferences;
  assistant?: AssistantPreferences;
}

export interface OnboardingStep {
  id: string;
  label: string;
  complete: boolean;
  optional: boolean;
}

export interface OnboardingResponse {
  completed: boolean;
  skipped: boolean;
  steps: OnboardingStep[];
  profile: ProfileResponse;
}

export interface BackupRowCount {
  table: string;
  rows: number;
}

export interface BackupPayload {
  format: string;
  version: number;
  exported_at: string;
  counts: BackupRowCount[];
  data: Record<string, unknown>;
}

export interface BackupValidation {
  valid: boolean;
  format: string;
  version: number;
  counts: BackupRowCount[];
  message: string;
}

export type SuggestionConfidence = "exact" | "similar" | "popular";

export interface CategorySuggestion {
  category_id: number;
  category_name: string;
  confidence: SuggestionConfidence;
  evidence: string | null;
  score: number | null;
}

export interface DuplicateMatch {
  id: number;
  account_id: number;
  date: string;
  amount: number;
  description: string;
  same_day: boolean;
  days_apart: number;
}

export interface QuickCaptureRequest {
  type: "expense" | "income";
  amount: number;
  description: string;
  date: string;
}

export interface QuickCaptureResponse {
  type: "expense" | "income";
  amount: number;
  date: string;
  account_id: number | null;
  category_id: number | null;
  description: string;
  categories: CategorySuggestion[];
  duplicates: DuplicateMatch[];
  warnings: string[];
}

export interface QuickCreateRequest extends QuickCaptureRequest {
  account_id?: number | null;
  category_id?: number | null;
  notes?: string | null;
  reject_duplicate?: boolean;
  check_duplicate?: boolean;
}

export interface QuickCreateResponse {
  transaction: TransactionRow;
  duplicates: DuplicateMatch[];
  warnings: string[];
}
