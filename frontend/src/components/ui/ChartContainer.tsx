import type { ReactNode } from "react";
import { EmptyState } from "./States";
import styles from "./ChartContainer.module.css";

interface ChartContainerProps {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  height?: number;
  /** Placeholder copy shown inside the plot area. */
  emptyHint?: string;
  emptyDescription?: string;
  children?: ReactNode;
}

/**
 * Frame for every dashboard chart. Without children it renders axis
 * scaffolding plus an explicit empty-state; with children it is a plain
 * framed plot area and the real renderer owns the canvas.
 */
export function ChartContainer({
  title,
  subtitle,
  action,
  height = 220,
  emptyHint = "No data yet",
  emptyDescription = "Visuals render once transaction data lands in this phase.",
  children,
}: ChartContainerProps) {
  const hasChildren = children !== undefined && children !== null;
  return (
    <section className={styles.container}>
      <header className={styles.header}>
        <div>
          <h2 className={styles.title}>{title}</h2>
          {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
        </div>
        {action}
      </header>
      <div className={styles.plot} style={{ height }}>
        {!hasChildren && (
          <div className={styles.axisY} aria-hidden>
            <span>100%</span>
            <span>75%</span>
            <span>50%</span>
            <span>25%</span>
            <span>0%</span>
          </div>
        )}
        <div className={hasChildren ? `${styles.canvas} ${styles.canvasReal}` : styles.canvas}>
          {!hasChildren && <div className={styles.grid} aria-hidden />}
          {hasChildren ? (
            children
          ) : (
            <div className={styles.overlay}>
              <EmptyState compact title={emptyHint} description={emptyDescription} />
            </div>
          )}
        </div>
      </div>
      {!hasChildren && (
        <div className={styles.xAxis} aria-hidden>
          <span>W1</span>
          <span>W2</span>
          <span>W3</span>
          <span>W4</span>
          <span>W5</span>
          <span>W6</span>
        </div>
      )}
    </section>
  );
}
