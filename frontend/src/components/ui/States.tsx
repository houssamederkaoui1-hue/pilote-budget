import type { ReactNode } from "react";
import { AlertIcon, RefreshIcon } from "../icons";
import styles from "./States.module.css";

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  compact?: boolean;
}

export function EmptyState({ icon, title, description, action, compact }: EmptyStateProps) {
  return (
    <div className={`${styles.empty} ${compact ? styles.compact : ""}`}>
      {icon && <div className={styles.emptyIcon}>{icon}</div>}
      <div className={styles.emptyTitle}>{title}</div>
      {description && <p className={styles.emptyDescription}>{description}</p>}
      {action && <div className={styles.emptyAction}>{action}</div>}
    </div>
  );
}

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className={styles.loading} role="status" aria-live="polite">
      <span className={styles.spinner} aria-hidden />
      <span className={styles.loadingLabel}>{label}</span>
    </div>
  );
}

export function Skeleton({ height = 16, width = "100%" }: { height?: number; width?: number | string }) {
  return <span className={styles.skeleton} style={{ height, width }} aria-hidden />;
}

export function SkeletonList({ rows = 4 }: { rows?: number }) {
  return (
    <div className={styles.skeletonList} aria-hidden>
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className={styles.skeletonRow}>
          <Skeleton height={12} width={44} />
          <Skeleton height={12} width="45%" />
          <Skeleton height={12} width={64} />
        </div>
      ))}
    </div>
  );
}

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export function ErrorState({ title = "Something went wrong", message, onRetry }: ErrorStateProps) {
  return (
    <div className={styles.error} role="alert">
      <div className={styles.errorIcon}>
        <AlertIcon size={20} />
      </div>
      <div className={styles.errorText}>
        <div className={styles.errorTitle}>{title}</div>
        <p className={styles.errorMessage}>{message}</p>
      </div>
      {onRetry && (
        <button type="button" className={styles.retryButton} onClick={onRetry}>
          <RefreshIcon size={15} />
          Retry
        </button>
      )}
    </div>
  );
}
