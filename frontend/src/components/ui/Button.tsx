import type { ComponentPropsWithoutRef, ReactNode } from "react";

import styles from "./buttons.module.css";

interface ButtonProps extends ComponentPropsWithoutRef<"button"> {
  variant?: "primary" | "ghost" | "danger" | "subtle";
  size?: "sm" | "md";
  loading?: boolean;
  children: ReactNode;
}

/** Shared button with robust (primary/ghost/danger/subtle) styling. */
export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  children,
  className,
  ...rest
}: ButtonProps) {
  const classes = [
    styles.button,
    styles[variant],
    styles[size],
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button type="button" className={classes} disabled={disabled || loading} {...rest}>
      {loading && <span className={styles.spinner} aria-hidden />}
      {children}
    </button>
  );
}