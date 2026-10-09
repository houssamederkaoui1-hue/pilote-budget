import { useMemo } from "react";
import {
  ActivityIcon,
  AlertIcon,
  ArrowDownIcon,
  ArrowUpIcon,
  BulbIcon,
  DebtsIcon,
  GoalsIcon,
  InfoIcon,
  RecurringIcon,
  WalletIcon,
} from "../components/icons";
import { CashFlowBars, Donut, TrendLine } from "../components/charts/Charts";
import { Badge, Card, ProgressBar, StatCard } from "../components/ui/Card";
import { ChartContainer } from "../components/ui/ChartContainer";
import { EmptyState, ErrorState, Skeleton, SkeletonList } from "../components/ui/States";
import { useApi } from "../hooks/useApi";
import {
  changeHint,
  currentPeriodLabel,
  monthLabel,
  periodRangeLabel,
  safeToSpendHint,
} from "../lib/dashboard";
import { formatCurrency, formatDate, formatDateTime, formatPercent } from "../lib/format";
import { orderedVisibleSections, usesThreeMonthHistory } from "../lib/settings";
import { DASHBOARD_SECTION_META } from "../types/api";
import type {
  AnalyticsResponse,
  DashboardPeriod,
  DashboardSectionId,
  DebtTotals,
  Goal,
  HealthResponse,
  Insight,
  ProfileResponse,
  SafeToSpendResponse,
  SettingsResponse,
  UpcomingResponse,
} from "../types/api";
import styles from "./Dashboard.module.css";

interface StatProps {
  id: string;
  label: string;
  value: string;
  hint: string;
  tone: "default" | "positive" | "negative" | "warning";
  icon: React.ReactNode;
}

interface ForecastRowProps {
  label: string;
  actual: number;
  estimated: number | null;
  currency: string;
}

function ForecastRow({ label, actual, estimated, currency }: ForecastRowProps) {
  return (
    <div className={styles.forecastRow}>
      <span className={styles.forecastLabel}>{label}</span>
      <span className={styles.forecastValues}>
        <span className="num">{formatCurrency(actual, currency)}</span>
        {estimated !== null && (
          <>
            <span className={styles.forecastArrow} aria-hidden>
              →
            </span>
            <span className={`num ${styles.forecastEst}`}>{formatCurrency(estimated, currency)}</span>
            <Badge tone="warning">est</Badge>
          </>
        )}
      </span>
    </div>
  );
}

const INSIGHT_TONES: Insight["tone"][] = ["accent", "positive", "negative", "warning", "neutral"];

const RATE_BADGES: Record<string, { tone: "positive" | "neutral" | "negative"; label: string }> = {
  positive: { tone: "positive", label: "healthy" },
  neutral: { tone: "neutral", label: "ok" },
  negative: { tone: "negative", label: "negative" },
  insufficient: { tone: "neutral", label: "no data" },
};

const LEVEL_BADGES: Record<string, { tone: "positive" | "neutral" | "warning" | "negative"; label: string }> = {
  low: { tone: "positive", label: "low" },
  moderate: { tone: "warning", label: "moderate" },
  high: { tone: "negative", label: "high" },
};

export function DashboardPage() {
  const profile = useApi<ProfileResponse>("/profile");
  const health = useApi<HealthResponse>("/health");
  const settings = useApi<SettingsResponse>("/settings");
  const period = (settings.data?.dashboard?.period ?? "current_month") as DashboardPeriod;
  const analytics = useApi<AnalyticsResponse>(usesThreeMonthHistory(period) ? "/analytics?months=3" : "/analytics");
  const safeToSpend = useApi<SafeToSpendResponse>("/analytics/safe-to-spend");
  const goals = useApi<Goal[]>("/goals");
  const upcoming = useApi<UpcomingResponse>("/recurring/upcoming?days=30");
  const debtTotals = useApi<DebtTotals>("/debts/totals");

  const sectionOrder = settings.data?.dashboard?.sections
    ? orderedVisibleSections(settings.data.dashboard.sections, settings.data.dashboard.order)
    : null;
  const visibleIds = new Set<DashboardSectionId>(sectionOrder ?? []);
  const on = (id: DashboardSectionId) => visibleIds.has(id) || sectionOrder === null;

  /** Grid `order` so personalization reordering works without moving the DOM. */
  const rank = (id: DashboardSectionId): number => {
    const canonical = DASHBOARD_SECTION_META.findIndex((entry) => entry.id === id);
    if (!sectionOrder) return canonical < 0 ? 99 : canonical;
    return sectionOrder.indexOf(id) < 0 ? 99 : sectionOrder.indexOf(id);
  };

  const a = analytics.data;
  const sts = safeToSpend.data;
  const currency = a?.currency ?? profile.data?.currency ?? "EUR";

  const stats = useMemo<StatProps[]>(() => {
    if (!a) return [];
    const nw = a.net_worth;
    const savingsTone =
      a.savings.rate_status === "negative"
        ? "negative"
        : a.savings.rate_status === "positive"
          ? "positive"
          : "default";
    const safeStat: StatProps =
      sts?.status === "ok"
        ? {
            id: "safe-to-spend",
            label: "Safe-to-Spend",
            value: formatCurrency(sts.safe_to_spend_daily, currency),
            hint: safeToSpendHint(sts.remaining_days, sts.discretionary, currency),
            tone: "warning",
            icon: <BulbIcon size={15} />,
          }
        : {
            id: "safe-to-spend",
            label: "Safe-to-Spend",
            value: "—",
            hint: sts?.reason ?? "Waiting on the ledger…",
            tone: "warning",
            icon: <BulbIcon size={15} />,
          };
    return [
      {
        id: "total-balance",
        label: "Total Balance",
        value: formatCurrency(a.forecasts.available.current, currency),
        hint:
          nw.liabilities > 0
            ? `${formatCurrency(nw.liabilities, currency, { cents: false })} owed on credit`
            : "Across all accounts",
        tone: "default",
        icon: <WalletIcon size={15} />,
      },
      {
        id: "income",
        label: "Income",
        value: formatCurrency(a.income.current, currency),
        hint: changeHint(a.income.change_pct),
        tone: "positive",
        icon: <ArrowUpIcon size={15} />,
      },
      {
        id: "expenses",
        label: "Expenses",
        value: formatCurrency(a.expenses.current, currency),
        hint: changeHint(a.expenses.change_pct),
        tone: "negative",
        icon: <ArrowDownIcon size={15} />,
      },
      {
        id: "savings",
        label: "Savings",
        value: formatCurrency(a.savings.current, currency),
        hint:
          a.savings.rate !== null
            ? `${formatPercent(a.savings.rate)} of income`
            : "No income recorded this period",
        tone: savingsTone,
        icon: <GoalsIcon size={15} />,
      },
      {
        id: "net-worth",
        label: "Net Worth",
        value: formatCurrency(nw.net_worth, currency),
        hint: changeHint(nw.change_pct),
        tone: nw.net_worth < 0 ? "negative" : "default",
        icon: <ActivityIcon size={15} />,
      },
      safeStat,
    ];
  }, [a, sts, currency]);

  const budgetItems = a?.budget.items ?? [];
  const overBudget = a?.budget.totals.over_budget ?? false;
  const upcomingExpenses = (upcoming.data?.occurrences ?? []).filter(
    (occurrence) => occurrence.type === "expense",
  );

  const healthRows = a
    ? [
        {
          label: "Savings rate",
          value: a.health.savings_rate !== null ? formatPercent(a.health.savings_rate) : "—",
          badge: RATE_BADGES[a.health.savings_rate_status] ?? RATE_BADGES.insufficient,
        },
        {
          label: "Budget used",
          value: a.health.budget_pct_used !== null ? formatPercent(a.health.budget_pct_used, 0) : "—",
          badge: a.health.budget_over
            ? { tone: "negative" as const, label: "over" }
            : a.health.budget_pct_used !== null
              ? { tone: "warning" as const, label: "approaching" }
              : { tone: "neutral" as const, label: "no plan" },
        },
        {
          label: "Recurring share",
          value: a.health.recurring_expense_ratio !== null ? formatPercent(a.health.recurring_expense_ratio) : "—",
          badge: a.health.recurring_expense_ratio_status
            ? LEVEL_BADGES[a.health.recurring_expense_ratio_status]
            : { tone: "neutral" as const, label: "no data" },
        },
        {
          label: "Debt burden",
          value: a.health.debt_burden !== null ? formatPercent(a.health.debt_burden) : "—",
          badge: a.health.debt_burden_status
            ? LEVEL_BADGES[a.health.debt_burden_status]
            : { tone: "neutral" as const, label: "no debt" },
        },
        {
          label: "Cash flow",
          value: formatCurrency(a.health.cashflow_net, currency),
          badge:
            a.health.cashflow_status === "positive"
              ? { tone: "positive" as const, label: `${a.health.cashflow_streak}-mo streak` }
              : a.health.cashflow_status === "negative"
                ? { tone: "negative" as const, label: "negative" }
                : { tone: "neutral" as const, label: "neutral" },
        },
        {
          label: "Upcoming obligations",
          value: formatCurrency(a.health.upcoming_obligations_amount, currency),
          badge:
            a.health.upcoming_obligations_count > 0
              ? { tone: "warning" as const, label: `${a.health.upcoming_obligations_count} due` }
              : { tone: "neutral" as const, label: "none" },
        },
      ]
    : [];

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-header__eyebrow">Overview</div>
          <h1>Dashboard</h1>
          <p className="page-header__subtitle">
            {a ? periodRangeLabel(a.period) : currentPeriodLabel()}
            {profile.data ? ` · month starts on day ${profile.data.month_start_day}` : ""}
          </p>
        </div>
        <div className={styles.headerBadges}>
          <Badge tone="accent">Analytics</Badge>
          <Badge tone="neutral">Live data</Badge>
        </div>
      </div>

      {profile.error && (
        <div className={styles.errorWrap}>
          <ErrorState title="Cannot load settings" message={profile.error} onRetry={profile.reload} />
        </div>
      )}
      {analytics.error && (
        <div className={styles.errorWrap}>
          <ErrorState title="Cannot load analytics" message={analytics.error} onRetry={analytics.reload} />
        </div>
      )}

      {on("stats") && (
        <div className={styles.statGrid}>
          {!a
            ? Array.from({ length: 6 }, (_, index) => (
                <div key={index} className={styles.statSkeleton}>
                  <Skeleton height={11} width="55%" />
                  <Skeleton height={24} width="72%" />
                  <Skeleton height={11} width="82%" />
                </div>
              ))
            : stats.map((stat) => (
                <StatCard
                  key={stat.id}
                  label={stat.label}
                  value={stat.value}
                  hint={stat.hint}
                  tone={stat.tone}
                  icon={stat.icon}
                />
              ))}
        </div>
      )}

      <div className="section-title">
        <h2>Analytics</h2>
        <span>{a ? periodRangeLabel(a.period) : "from the ledger"}</span>
      </div>

      <div className={styles.grid}>
        {on("cash_flow") && (
          <div className={styles.span8} style={{ order: rank("cash_flow") }}>
            <ChartContainer
              title="Cash Flow"
              subtitle="Income vs expenses per period · current period highlighted"
              height={248}
              emptyHint="No cash flow yet"
              emptyDescription="Record or import income and expenses; the bars are drawn from the ledger."
            >
              {a && a.history.length > 0 ? (
                <CashFlowBars
                  currency={currency}
                  height={200}
                  points={a.history.map((point) => ({
                    label: monthLabel(point.period_start),
                    income: point.income,
                    expense: point.expense,
                    current: !point.closed,
                  }))}
                />
              ) : null}
            </ChartContainer>
          </div>
        )}

        {on("net_worth") && (
          <div className={styles.span4} style={{ order: rank("net_worth") }}>
          <Card
            title="Net Worth"
            subtitle="Accounts, with tracked debts folded in where they differ"
            className={styles.full}
            action={
              a ? (
                <Badge tone={(a.net_worth.change_pct ?? 0) >= 0 ? "positive" : "negative"}>
                  {a.net_worth.change_pct !== null ? `${a.net_worth.change_pct > 0 ? "+" : ""}${a.net_worth.change_pct}%` : "—"}
                </Badge>
              ) : undefined
            }
          >
            {a ? (
              <div className={styles.netWorth}>
                <div
                  className={`${styles.netWorthValue} num ${a.net_worth.net_worth < 0 ? "negative" : "positive"}`}
                >
                  {formatCurrency(a.net_worth.net_worth, currency)}
                </div>
                <div className={styles.netWorthHint}>
                  {a.net_worth.previous !== null
                    ? `${formatCurrency(a.net_worth.previous, currency)} at previous period end`
                    : "First period on record"}
                </div>
                <TrendLine
                  currency={currency}
                  height={76}
                  points={a.net_worth_history.map((point) => ({
                    label: monthLabel(point.period_start),
                    value: point.net_worth,
                  }))}
                />
                <div className={styles.netWorthRows}>
                  <div className={styles.netWorthRow}>
                    <span className="secondary">Assets</span>
                    <span className="num positive">{formatCurrency(a.net_worth.assets, currency)}</span>
                  </div>
                  <div className={styles.netWorthRow}>
                    <span className="secondary">Liabilities</span>
                    <span className="num negative">{formatCurrency(a.net_worth.liabilities, currency)}</span>
                  </div>
                  {a.net_worth.net_worth_including_debts !== a.net_worth.net_worth && (
                    <div className={styles.netWorthRow}>
                      <span className="secondary">Including tracked debts</span>
                      <span className="num">
                        {formatCurrency(a.net_worth.net_worth_including_debts, currency)}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <SkeletonList rows={3} />
            )}
          </Card>
        </div>
        )}

        {on("category_spending") && (
        <div className={styles.span4} style={{ order: rank("category_spending") }}>
          <ChartContainer
            title="Spending by Category"
            subtitle="Share of this period's expenses"
            height={236}
            emptyHint="No expenses this period"
            emptyDescription="Category shares appear as soon as expenses are recorded."
          >
            {a && a.categories.length > 0 ? (
              <Donut
                currency={currency}
                segments={a.categories.map((category) => ({
                  key: String(category.category_id ?? "uncategorized"),
                  label: category.category_name ?? "Uncategorized",
                  value: category.amount,
                }))}
              />
            ) : null}
          </ChartContainer>
        </div>
        )}

        {on("budget_vs_actual") && (
        <div className={styles.span4} style={{ order: rank("budget_vs_actual") }}>
          <Card
            title="Budget vs Actual"
            subtitle={a ? periodRangeLabel(a.budget) : "current period"}
            action={
              a ? (
                <Badge tone={overBudget ? "negative" : "positive"}>{overBudget ? "over" : "on track"}</Badge>
              ) : undefined
            }
          >
            {!a ? (
              <SkeletonList rows={3} />
            ) : budgetItems.length > 0 || a.budget.totals.planned > 0 ? (
              <div className={styles.budgetList}>
                <ProgressBar
                  value={a.budget.totals.pct_used ?? 0}
                  label="Overall"
                  tone={overBudget ? "negative" : "accent"}
                />
                {budgetItems.slice(0, 5).map((item) => (
                  <div key={item.category_id} className={styles.budgetRow}>
                    <div className={styles.budgetRowTop}>
                      <span className={styles.budgetRowName}>{item.category_name}</span>
                      <span className={`num ${item.over_budget ? "negative" : "secondary"}`}>
                        {formatCurrency(item.actual_amount, currency, { cents: false })} /{" "}
                        {formatCurrency(item.planned_amount, currency, { cents: false })}
                      </span>
                    </div>
                    <ProgressBar
                      value={item.pct_used ?? 0}
                      tone={
                        item.status === "over"
                          ? "negative"
                          : item.status === "approaching"
                            ? "warning"
                            : item.status === "healthy"
                              ? "positive"
                              : "accent"
                      }
                    />
                  </div>
                ))}
                {budgetItems.length > 5 && (
                  <span className={styles.more}>+{budgetItems.length - 5} more categories</span>
                )}
              </div>
) : (
                <EmptyState
                  icon={<InfoIcon size={20} />}
                  title="No budget set"
                  description="Pick planned amounts per category on the Budgets page to compare them here."
                />
              )}
          </Card>
        </div>
        )}

        {on("safe_to_spend") && (
        <div className={styles.span4} style={{ order: rank("safe_to_spend") }}>
          <Card
            title="Safe-to-Spend"
            subtitle="What is left for the rest of the period"
            action={sts?.status === "ok" ? <Badge tone="accent">estimate</Badge> : undefined}
          >
            {safeToSpend.error ? (
              <ErrorState
                title="Cannot load Safe-to-Spend"
                message={safeToSpend.error}
                onRetry={safeToSpend.reload}
              />
            ) : !sts ? (
              <SkeletonList rows={3} />
            ) : sts.status === "ok" ? (
              <div className={styles.sts}>
                <div className={styles.stsHeadline}>
                  <span className={`${styles.stsValue} num`}>{formatCurrency(sts.safe_to_spend_daily, currency)}</span>
                  <span className={styles.stsUnit}>
                    per day · {sts.remaining_days} days left · {formatCurrency(sts.discretionary, currency)} available
                  </span>
                </div>
                <dl className={styles.stsRows}>
                  <div className={styles.stsRow}>
                    <dt>Available money</dt>
                    <dd className="num">{formatCurrency(sts.available_money, currency)}</dd>
                  </div>
                  <div className={styles.stsRow}>
                    <dt>Upcoming obligations ({sts.obligations.length})</dt>
                    <dd className="num negative">{formatCurrency(sts.obligations_total, currency)}</dd>
                  </div>
                  <div className={styles.stsRow}>
                    <dt>Planned savings</dt>
                    <dd className="num negative">{formatCurrency(sts.planned_savings, currency)}</dd>
                  </div>
                  <div className={styles.stsRow}>
                    <dt>Minimum reserve</dt>
                    <dd className="num negative">{formatCurrency(sts.reserve_amount, currency)}</dd>
                  </div>
                  <div className={`${styles.stsRow} ${styles.stsRowStrong}`}>
                    <dt>Discretionary</dt>
                    <dd className="num">{formatCurrency(sts.discretionary, currency)}</dd>
                  </div>
                </dl>
                <p className={styles.stsNote}>{sts.explanation}</p>
                <p className={styles.stsDisclaimer}>{sts.disclaimer}</p>
              </div>
            ) : (
              <EmptyState
                icon={<AlertIcon size={20} />}
                title="Not enough history"
                description={sts.reason ?? sts.explanation}
              />
            )}
          </Card>
        </div>
        )}

        {on("forecast") && (
        <div className={styles.span4} style={{ order: rank("forecast") }}>
          <Card
            title="Forecast"
            subtitle="Month-end projection from the pace so far"
            action={
              a && a.forecasts.available.is_estimate ? <Badge tone="warning">estimated</Badge> : undefined
            }
          >
            {a ? (
              <>
                <div className={styles.forecastList}>
                  <ForecastRow label="Income" actual={a.forecasts.income.actual} estimated={a.forecasts.income.estimated} currency={currency} />
                  <ForecastRow label="Spending" actual={a.forecasts.spending.actual} estimated={a.forecasts.spending.estimated} currency={currency} />
                  <ForecastRow label="Savings" actual={a.forecasts.savings.actual} estimated={a.forecasts.savings.estimated} currency={currency} />
                  <ForecastRow label="Balance" actual={a.forecasts.available.current} estimated={a.forecasts.available.estimated_end} currency={currency} />
                </div>
                <p className={styles.forecastNote}>{a.forecasts.note}</p>
              </>
            ) : (
              <SkeletonList rows={3} />
            )}
          </Card>
        </div>
        )}

        {on("financial_health") && (
        <div className={styles.span4} style={{ order: rank("financial_health") }}>
          <Card title="Financial Health" subtitle="Deterministic indicators">
            {!a ? (
              <SkeletonList rows={4} />
            ) : (
              <ul className={styles.healthList}>
                {healthRows.map((row) => (
                  <li key={row.label} className={styles.healthRow}>
                    <span className={styles.healthLabel}>{row.label}</span>
                    <span className={`${styles.healthValue} num`}>{row.value}</span>
                    <Badge tone={row.badge.tone}>{row.badge.label}</Badge>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
        )}

        {on("insights") && (
        <div className={styles.span4} style={{ order: rank("insights") }}>
          <Card title="Insights" subtitle="Rule-based, straight from the ledger">
            {!a ? (
              <SkeletonList rows={3} />
            ) : (
              <ul className={styles.insightList}>
                {a.insights.map((insight) => (
                  <li key={insight.key} className={styles.insightItem}>
                    <span
                      className={`${styles.insightIcon} ${INSIGHT_TONES.includes(insight.tone) ? styles[insight.tone] : styles.accent}`}
                    >
                      <BulbIcon size={14} />
                    </span>
                    <div>
                      <div className={styles.insightTitle}>{insight.title}</div>
                      <p className={styles.insightText}>{insight.description}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
        )}
      </div>

      <div className="section-title">
        <h2>Planning</h2>
        <span>Goals · upcoming bills · debts</span>
      </div>

      <div className={styles.grid}>
        {on("goals") && (
        <div className={styles.span4} style={{ order: rank("goals") }}>
          <Card
            title="Goals"
            subtitle="Savings targets"
            action={<Badge tone="neutral">{goals.data ? `${goals.data.length}` : "…"}</Badge>}
          >
            {goals.loading && <SkeletonList rows={3} />}
            {!goals.loading && goals.error && <ErrorState message={goals.error} onRetry={goals.reload} />}
            {!goals.loading && !goals.error && goals.data && goals.data.length === 0 && (
              <EmptyState
                icon={<GoalsIcon size={20} />}
                title="No goals yet"
                description="Create a savings goal and its progress shows up here."
              />
            )}
            {!goals.loading && goals.data && goals.data.length > 0 && (
              <ul className={styles.goalList}>
                {goals.data.slice(0, 4).map((goal) => (
                  <li key={goal.id} className={styles.goalItem}>
                    <div className={styles.goalTop}>
                      <span className={styles.goalName}>{goal.name}</span>
                      <span className={`${styles.goalPct} num`}>{goal.progress_pct.toFixed(0)}%</span>
                    </div>
                    <ProgressBar
                      value={goal.progress_pct}
                      tone={goal.progress_pct >= 100 ? "positive" : "accent"}
                    />
                    <div className={styles.goalMeta}>
                      <span className="num">
                        {formatCurrency(goal.current_amount, currency, { cents: false })} of{" "}
                        {formatCurrency(goal.target_amount, currency, { cents: false })}
                      </span>
                      {goal.target_date && <span className={styles.goalDate}>due {formatDate(goal.target_date)}</span>}
                    </div>
                  </li>
                ))}
                {goals.data.length > 4 && <li className={styles.more}>+{goals.data.length - 4} more</li>}
              </ul>
            )}
          </Card>
        </div>
        )}

        {on("upcoming_bills") && (
        <div className={styles.span4} style={{ order: rank("upcoming_bills") }}>
          <Card
            title="Upcoming Bills"
            subtitle="Recurring expenses due in the next 30 days"
            action={<RecurringIcon size={16} />}
          >
            {upcoming.loading && <SkeletonList rows={3} />}
            {!upcoming.loading && upcoming.error && <ErrorState message={upcoming.error} onRetry={upcoming.reload} />}
            {!upcoming.loading && !upcoming.error && upcoming.data && (
              upcomingExpenses.length === 0 ? (
                  <EmptyState
                    icon={<InfoIcon size={20} />}
                    title="Nothing due soon"
                    description="Recurring templates you create will be listed here before they are due."
                  />
                ) : (
                  <ul className={styles.dueList}>
                    {upcomingExpenses.slice(0, 6).map((occurrence, index) => (
                      <li key={`${occurrence.recurring_id}-${occurrence.due_date}-${index}`} className={styles.dueItem}>
                        <span className={styles.dueBadge}>{formatDate(occurrence.due_date)}</span>
                        <span className={styles.dueName}>{occurrence.description}</span>
                        <span className="num negative">
                          −{formatCurrency(occurrence.amount, currency, { cents: false })}
                        </span>
                      </li>
                    ))}
                  </ul>
                )
            )}
          </Card>
        </div>
        )}

        {on("debts") && (
        <div className={styles.span4} style={{ order: rank("debts") }}>
          <Card
            title="Debts"
            subtitle="Active balances and minimum payments"
            action={<DebtsIcon size={16} />}
          >
            {debtTotals.loading && <SkeletonList rows={3} />}
            {!debtTotals.loading && debtTotals.error && (
              <ErrorState message={debtTotals.error} onRetry={debtTotals.reload} />
            )}
            {!debtTotals.loading && !debtTotals.error && debtTotals.data && (
              <>
                {debtTotals.data.active_debt_count === 0 ? (
                  <EmptyState
                    icon={<InfoIcon size={20} />}
                    title="No active debts"
                    description="Add a loan or card balance to track repayments here."
                  />
                ) : (
                  <div className={styles.debtWrap}>
                    <div className={styles.debtStats}>
                      <div className={styles.debtStat}>
                        <div className={styles.debtStatLabel}>Remaining</div>
                        <div className={`${styles.debtStatValue} num negative`}>
                          {formatCurrency(debtTotals.data.total_remaining, currency, { cents: false })}
                        </div>
                      </div>
                      <div className={styles.debtStat}>
                        <div className={styles.debtStatLabel}>Min. payment</div>
                        <div className={`${styles.debtStatValue} num`}>
                          {formatCurrency(debtTotals.data.total_minimum_payment, currency, { cents: false })}
                        </div>
                      </div>
                      <div className={styles.debtStat}>
                        <div className={styles.debtStatLabel}>Active</div>
                        <div className={`${styles.debtStatValue} num`}>{debtTotals.data.active_debt_count}</div>
                      </div>
                    </div>
                    {debtTotals.data.upcoming_due_dates.length > 0 && (
                      <ul className={styles.dueList}>
                        {debtTotals.data.upcoming_due_dates.slice(0, 3).map((due) => (
                          <li key={due.debt_id} className={styles.dueItem}>
                            <span className={styles.dueBadge}>{formatDate(due.due_date)}</span>
                            <span className={styles.dueName}>{due.name}</span>
                            <span className="num">
                              {due.minimum_payment !== null ? formatCurrency(due.minimum_payment, currency, { cents: false }) : "—"}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </>
            )}
          </Card>
        </div>
        )}
      </div>

      <div className="section-title">
        <h2>System</h2>
        <span>Live API status</span>
      </div>

      <Card>
        {health.loading && <SkeletonList rows={2} />}
        {!health.loading && health.error && <ErrorState message={health.error} onRetry={health.reload} />}
        {!health.loading && !health.error && health.data && (
          <div className={styles.systemRow}>
            <div>
              <div className={styles.systemLabel}>Backend</div>
              <div className={styles.systemValue}>
                {health.data.app} · v{health.data.version} ({health.data.environment})
              </div>
            </div>
            <div>
              <div className={styles.systemLabel}>Database</div>
              <div className={styles.systemValue}>
                {health.data.database.connected ? `connected · ${health.data.database.dialect}` : "disconnected"}
              </div>
            </div>
            <div>
              <div className={styles.systemLabel}>Last health check</div>
              <div className={styles.systemValue}>{formatDateTime(health.data.time)}</div>
            </div>
            <Badge tone={health.data.status === "ok" ? "positive" : "warning"}>{health.data.status}</Badge>
          </div>
        )}
      </Card>
    </>
  );
}
