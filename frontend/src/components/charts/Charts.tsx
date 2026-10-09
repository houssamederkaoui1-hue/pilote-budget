import { formatCompactCurrency, formatCurrency } from "../../lib/format";
import styles from "./Charts.module.css";

/**
 * Hand-rolled chart primitives. They are purely presentational: every number
 * they draw comes from the analytics API, and the only maths here is scaling
 * values to pixels/degrees for drawing.
 */

const PALETTE = [
  "#4f8cff",
  "#f26d6d",
  "#e8b04b",
  "#35c48a",
  "#9d7bff",
  "#57c7d4",
  "#f28fc7",
  "#f29e52",
];

/* ---- Grouped bars (income vs expense per period) ------------------------ */

export interface CashFlowPoint {
  label: string;
  income: number;
  expense: number;
  current: boolean;
}

interface CashFlowBarsProps {
  points: CashFlowPoint[];
  currency: string;
  /** Plot height in px (bars are scaled inside it). */
  height?: number;
}

export function CashFlowBars({ points, currency, height = 168 }: CashFlowBarsProps) {
  const max = Math.max(1, ...points.flatMap((point) => [point.income, point.expense]));
  const scale = (value: number) => Math.max(value > 0 ? 2 : 0, Math.round((value / max) * height));

  return (
    <div className={styles.bars} style={{ height: height + 22 }}>
      {points.map((point) => (
        <div key={point.label} className={styles.barGroup}>
          <div className={styles.barPair} style={{ height }}>
            <span
              className={`${styles.bar} ${styles.barIncome}`}
              style={{ height: scale(point.income) }}
              title={`Income: ${formatCurrency(point.income, currency)}`}
            />
            <span
              className={`${styles.bar} ${styles.barExpense}`}
              style={{ height: scale(point.expense) }}
              title={`Expenses: ${formatCurrency(point.expense, currency)}`}
            />
          </div>
          <span className={point.current ? styles.barLabelCurrent : styles.barLabel}>
            {point.label}
          </span>
        </div>
      ))}
    </div>
  );
}

/* ---- Trend line (net worth over time) ----------------------------------- */

export interface TrendPoint {
  label: string;
  value: number;
}

interface TrendLineProps {
  points: TrendPoint[];
  currency: string;
  height?: number;
}

export function TrendLine({ points, currency, height = 76 }: TrendLineProps) {
  if (points.length === 0) return null;

  const values = points.map((point) => point.value);
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) {
    const pad = Math.max(1, Math.abs(min) * 0.1);
    min -= pad;
    max += pad;
  }
  const span = max - min;

  const coords = points.map((point, index) => ({
    ...point,
    x: points.length === 1 ? 50 : (index / (points.length - 1)) * 100,
    y: 100 - ((point.value - min) / span) * 100,
  }));

  const line = coords.map((coord) => `${coord.x},${coord.y}`).join(" ");
  const area = `0,100 ${line} 100,100`;
  const lastIndex = coords.length - 1;

  return (
    <div className={styles.trend} style={{ height }}>
      <svg
        className={styles.trendSvg}
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        aria-hidden
      >
        <polygon className={styles.trendArea} points={area} />
        <polyline
          className={styles.trendLine}
          points={line}
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      {coords.map((coord, index) => (
        <span
          key={coord.label}
          className={index === lastIndex ? styles.trendDotLast : styles.trendDot}
          style={{ left: `${coord.x}%`, top: `${coord.y}%` }}
          title={`${coord.label}: ${formatCurrency(coord.value, currency)}`}
        />
      ))}
      <div className={styles.trendLabels}>
        <span>{coords[0].label}</span>
        <span>{coords[lastIndex].label}</span>
      </div>
    </div>
  );
}

/* ---- Donut (category shares) -------------------------------------------- */

export interface DonutSegment {
  key: string;
  label: string;
  value: number;
}

interface DonutProps {
  segments: DonutSegment[];
  currency: string;
  centerLabel?: string;
}

export function Donut({ segments, currency, centerLabel = "spent" }: DonutProps) {
  const total = segments.reduce((sum, segment) => sum + segment.value, 0);
  if (total <= 0 || segments.length === 0) return null;

  let offset = 0;
  const stops = segments.map((segment, index) => {
    const from = (offset / total) * 360;
    offset += segment.value;
    const to = (offset / total) * 360;
    return `${PALETTE[index % PALETTE.length]} ${from.toFixed(2)}deg ${to.toFixed(2)}deg`;
  });

  return (
    <div className={styles.donutWrap}>
      <div className={styles.donut} style={{ background: `conic-gradient(${stops.join(", ")})` }}>
        <div className={styles.donutHole}>
          <span className={`${styles.donutValue} num`}>
            {formatCompactCurrency(total, currency)}
          </span>
          <span className={styles.donutLabel}>{centerLabel}</span>
        </div>
      </div>
      <ul className={styles.legend}>
        {segments.map((segment, index) => (
          <li key={segment.key} className={styles.legendItem}>
            <span
              className={styles.legendSwatch}
              style={{ background: PALETTE[index % PALETTE.length] }}
            />
            <span className={styles.legendLabel}>{segment.label}</span>
            <span className={`${styles.legendValue} num`}>
              {formatCurrency(segment.value, currency, { cents: false })}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
