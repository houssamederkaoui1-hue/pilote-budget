import { useState } from "react";
import { Card, StatCard } from "../components/ui/Card";
import { ChartContainer } from "../components/ui/ChartContainer";
import { CashFlowBars, Donut, TrendLine } from "../components/charts/Charts";
import { EmptyState, ErrorState, Skeleton } from "../components/ui/States";
import { useApi } from "../hooks/useApi";
import { formatCurrency, formatPercent } from "../lib/format";
import type { AnalyticsResponse } from "../types/api";

export function AnalyticsPage() {
  const [months, setMonths] = useState<number>(7);
  const analytics = useApi<AnalyticsResponse>(`/analytics?months=${months}`);

  if (analytics.loading && !analytics.data) {
    return (
      <div className="space-y">
        <div className="page-header">
          <div>
            <div className="page-header__eyebrow">Insights & History</div>
            <h1>Analytics</h1>
            <p className="page-header__subtitle">Comprehensive historical trends, cash flow and forecasts.</p>
          </div>
        </div>
        <Skeleton height={200} />
      </div>
    );
  }

  if (analytics.error) {
    return (
      <Card>
        <ErrorState message={analytics.error} />
      </Card>
    );
  }

  const data = analytics.data;
  if (!data) return null;

  const currency = data.currency;

  const cashFlowPoints = data.history.map((point) => {
    const d = new Date(point.period_start);
    const label = d.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
    return {
      label,
      income: point.income,
      expense: point.expense,
      current: point.closed === false,
    };
  });

  const netWorthPoints = data.net_worth_history.map((point) => {
    const d = new Date(point.period_start);
    const label = d.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
    return {
      label,
      value: point.net_worth,
    };
  });

  const categorySegments = data.categories.map((cat, idx) => ({
    key: String(cat.category_id ?? idx),
    label: cat.category_name ?? "Unassigned",
    value: cat.amount,
  }));

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-header__eyebrow">Insights & History</div>
          <h1>Analytics</h1>
          <p className="page-header__subtitle">Historical trends, income vs expenses, and multi-month analytics.</p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>History window:</span>
          {[3, 6, 7, 12].map((m) => (
            <button
              key={m}
              onClick={() => setMonths(m)}
              style={{
                padding: "6px 12px",
                borderRadius: 6,
                border: "1px solid var(--color-border)",
                background: months === m ? "var(--color-primary)" : "var(--color-bg-card)",
                color: months === m ? "white" : "var(--color-text)",
                cursor: "pointer",
                fontWeight: 500,
              }}
            >
              {m}m
            </button>
          ))}
        </div>
      </div>

      {!data.has_data ? (
        <Card>
          <EmptyState
            title="No transaction history yet"
            description="Add accounts and transactions to see deep analytics, trends and savings rates."
          />
        </Card>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          {/* Top KPI Cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16 }}>
            <StatCard
              label="Period Income"
              value={formatCurrency(data.income.current, currency)}
              hint={data.income.change_pct !== null ? `${data.income.change_pct >= 0 ? "+" : ""}${formatPercent(data.income.change_pct)} vs previous` : "Current period"}
              tone={data.income.trend === "up" ? "positive" : "default"}
            />
            <StatCard
              label="Period Expenses"
              value={formatCurrency(data.expenses.current, currency)}
              hint={data.expenses.change_pct !== null ? `${data.expenses.change_pct >= 0 ? "+" : ""}${formatPercent(data.expenses.change_pct)} vs previous` : "Current period"}
              tone={data.expenses.trend === "down" ? "positive" : "default"}
            />
            <StatCard
              label="Savings Rate"
              value={data.savings.rate !== null ? `${data.savings.rate.toFixed(1)}%` : "N/A"}
              hint={`Current savings: ${formatCurrency(data.savings.current, currency)}`}
              tone={data.savings.rate_status === "positive" ? "positive" : "warning"}
            />
            <StatCard
              label="Net Worth"
              value={formatCurrency(data.net_worth.net_worth, currency)}
              hint={`Assets: ${formatCurrency(data.net_worth.assets, currency)}`}
              tone="positive"
            />
          </div>

          {/* Cash Flow Chart */}
          <ChartContainer title="Cash Flow History" subtitle={`Income vs Expenses across the last ${months} months`} height={200}>
            <CashFlowBars points={cashFlowPoints} currency={currency} height={160} />
          </ChartContainer>

          {/* Grid: Net Worth Trend + Category Spending */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 24 }}>
            <ChartContainer title="Net Worth Trend" subtitle="Growth over historical periods" height={180}>
              {netWorthPoints.length > 0 ? (
                <TrendLine points={netWorthPoints} currency={currency} height={140} />
              ) : (
                <EmptyState title="No net worth history" description="Add assets and liabilities to track growth." />
              )}
            </ChartContainer>

            <Card title="Spending by Category" subtitle="Top expense categories this period">
              {categorySegments.length > 0 ? (
                <Donut segments={categorySegments} currency={currency} centerLabel="expenses" />
              ) : (
                <EmptyState title="No expenses recorded" description="Categorised expenses will appear here." />
              )}
            </Card>
          </div>

          {/* Financial Health & Insights Summary */}
          <Card title="Financial Health & Forecasts" subtitle="Automated guidance based on your ledger">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16 }}>
              <div style={{ padding: 16, background: "var(--color-bg-subtle)", borderRadius: 8 }}>
                <h4 style={{ marginBottom: 8, fontSize: "var(--font-size-md)" }}>End-of-Month Forecast</h4>
                <p style={{ color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)", marginBottom: 12 }}>
                  {data.forecasts.note}
                </p>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span>Estimated ending balance:</span>
                  <span className="num" style={{ fontWeight: 600 }}>
                    {data.forecasts.available.estimated_end !== null
                      ? formatCurrency(data.forecasts.available.estimated_end, currency)
                      : formatCurrency(data.forecasts.available.current, currency)}
                  </span>
                </div>
              </div>

              <div style={{ padding: 16, background: "var(--color-bg-subtle)", borderRadius: 8 }}>
                <h4 style={{ marginBottom: 8, fontSize: "var(--font-size-md)" }}>Key Insights</h4>
                {data.insights.length > 0 ? (
                  <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 8 }}>
                    {data.insights.slice(0, 3).map((insight) => (
                      <li key={insight.key} style={{ fontSize: "var(--font-size-sm)", display: "flex", gap: 8, alignItems: "flex-start" }}>
                        <span style={{ color: "var(--color-primary)" }}>•</span>
                        <div>
                          <strong>{insight.title}:</strong> {insight.description}
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p style={{ color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)" }}>No critical insights at this time.</p>
                )}
              </div>
            </div>
          </Card>
        </div>
      )}
    </>
  );
}
