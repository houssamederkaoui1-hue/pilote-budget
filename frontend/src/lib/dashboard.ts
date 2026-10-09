/*
 * Dashboard presentation helpers.
 *
 * Formatting and label logic only — every number passed in here is produced
 * by the backend analytics engine; nothing in this module derives money.
 */

import { formatCurrency } from "./format";

function parseLocal(iso: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!match) return null;
  return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
}

export function currentPeriodLabel(now: Date = new Date()): string {
  return new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric" }).format(now);
}

/**
 * Calendar window for a period anchored on ``month_start_day``, mirroring the
 * backend's period logic (dates only — no money is derived here).
 * Example (day 15): Sep 15 .. Oct 14.
 */
export function currentPeriodWindow(
  monthStartDay: number,
  now: Date = new Date(),
): { period_start: Date; period_end: Date } {
  const msd = Math.min(29, Math.max(1, Math.floor(monthStartDay) || 1));
  let year = now.getFullYear();
  let month = now.getMonth(); // 0-based
  if (now.getDate() < msd) {
    const previous = new Date(year, month - 1, 1);
    year = previous.getFullYear();
    month = previous.getMonth();
  }
  const start = new Date(year, month, msd);
  const nextStart = new Date(year, month + 1, msd);
  return { period_start: start, period_end: new Date(nextStart.getFullYear(), nextStart.getMonth(), nextStart.getDate() - 1) };
}

/** "Oct 2026 · period 1–31" style line for the app header. */
export function currentPeriodLine(monthStartDay: number, now: Date = new Date()): string {
  const { period_start, period_end } = currentPeriodWindow(monthStartDay, now);
  const sameWindow =
    period_start.getFullYear() === period_end.getFullYear() &&
    period_start.getMonth() === period_end.getMonth();
  if (sameWindow) {
    const monthYear = new Intl.DateTimeFormat(undefined, { month: "short", year: "numeric" });
    return `${monthYear.format(period_start)} · period ${period_start.getDate()}–${period_end.getDate()}`;
  }
  // Cross-month window (e.g. day-15 periods): "Sep 15 – Oct 14, 2026".
  const dayMonth = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" });
  const fullDay = new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  const startPart =
    period_start.getFullYear() === period_end.getFullYear()
      ? dayMonth.format(period_start)
      : fullDay.format(period_start);
  return `${startPart} – ${fullDay.format(period_end)}`;
}

/** Short axis label for a period start date, e.g. "Sep". */
export function monthLabel(iso: string): string {
  const date = parseLocal(iso);
  if (!date) return "";
  return new Intl.DateTimeFormat(undefined, { month: "short" }).format(date);
}

/** "Oct 1 – Oct 31, 2026" style range for a period window. */
export function periodRangeLabel(window: { period_start: string; period_end: string }): string {
  const start = parseLocal(window.period_start);
  const end = parseLocal(window.period_end);
  if (!start || !end) return "";
  const dayMonth = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" });
  const fullDay = new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  const startPart =
    start.getFullYear() === end.getFullYear() ? dayMonth.format(start) : fullDay.format(start);
  return `${startPart} – ${fullDay.format(end)}`;
}

/** "+12.5% vs previous period" / "No previous period data". */
export function changeHint(changePct: number | null): string {
  if (changePct === null) return "No previous period data";
  if (changePct === 0) return "Flat vs previous period";
  return `${changePct > 0 ? "+" : ""}${changePct.toFixed(1)}% vs previous period`;
}

/** Short committed-amount hint from the Safe-to-Spend payload. */
export function safeToSpendHint(
  remainingDays: number | null,
  discretionary: number | null,
  currency: string,
): string {
  const days = remainingDays === null ? "" : ` · ${remainingDays} days left`;
  const pool =
    discretionary === null
      ? ""
      : ` · ${formatCurrency(discretionary, currency, { cents: false })} left to spend`;
  return `Per day${days}${pool}`;
}
