/** Presentation formatting helpers (no business rules live here). */

const currencyFormatters = new Map<string, Intl.NumberFormat>();

function formatter(currency: string, withCents: boolean): Intl.NumberFormat {
  const key = `${currency}:${withCents ? "2" : "0"}`;
  const cached = currencyFormatters.get(key);
  if (cached) return cached;
  const created = new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    minimumFractionDigits: withCents ? 2 : 0,
    maximumFractionDigits: withCents ? 2 : 0,
  });
  currencyFormatters.set(key, created);
  return created;
}

export function formatCurrency(
  value: number | null | undefined,
  currency = "MAD",
  options: { cents?: boolean } = {},
): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return formatter(currency, options.cents ?? true).format(value);
}

export function formatCompactCurrency(value: number, currency = "MAD"): string {
  const created = new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    notation: "compact",
    maximumFractionDigits: 1,
  });
  return created.format(value);
}

export function formatPercent(value: number, fractionDigits = 1): string {
  return `${value.toFixed(fractionDigits)}%`;
}

export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function formatMonthAnchor(date: Date): string {
  return new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric" }).format(date);
}
