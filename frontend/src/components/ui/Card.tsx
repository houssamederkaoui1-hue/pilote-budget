import type { ReactNode } from "react";
import styles from "./Card.module.css";

interface CardProps {
  title?: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}

export function Card({ title, subtitle, action, children, className, bodyClassName }: CardProps) {
  const classes = [styles.card, className].filter(Boolean).join(" ");
  return (
    <section className={classes}>
      {(title ?? action) && (
        <header className={styles.header}>
          <div className={styles.headerText}>
            {title && <h2 className={styles.title}>{title}</h2>}
            {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
          </div>
          {action && <div className={styles.action}>{action}</div>}
        </header>
      )}
      <div className={[styles.body, bodyClassName].filter(Boolean).join(" ")}>{children}</div>
    </section>
  );
}

interface StatCardProps {
  label: string;
  value: string;
  hint?: string;
  icon?: ReactNode;
  tone?: "default" | "positive" | "negative" | "warning";
  footer?: ReactNode;
}

export function StatCard({ label, value, hint, icon, tone = "default", footer }: StatCardProps) {
  const valueClass = [
    styles.statValue,
    "num",
    tone === "positive" ? "positive" : "",
    tone === "negative" ? "negative" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <section className={styles.stat}>
      <div className={styles.statTop}>
        <span className={styles.statLabel}>{label}</span>
        {icon && <span className={`${styles.statIcon} ${styles[tone]}`}>{icon}</span>}
      </div>
      <div className={valueClass}>{value}</div>
      {hint && <div className={styles.statHint}>{hint}</div>}
      {footer}
    </section>
  );
}

interface ProgressBarProps {
  value: number;
  label?: string;
  tone?: "accent" | "positive" | "warning" | "negative";
}

export function ProgressBar({ value, label, tone = "accent" }: ProgressBarProps) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className={styles.progressWrap}>
      {label && (
        <div className={styles.progressLabel}>
          <span>{label}</span>
          <span className="num">{clamped.toFixed(0)}%</span>
        </div>
      )}
      <div className={styles.progressTrack}>
        <div className={`${styles.progressFill} ${styles[`fill_${tone}`]}`} style={{ width: `${clamped}%` }} />
      </div>
    </div>
  );
}

type BadgeTone = "neutral" | "positive" | "negative" | "warning" | "accent";

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: BadgeTone }) {
  return <span className={`${styles.badge} ${styles[`badge_${tone}`]}`}>{children}</span>;
}
