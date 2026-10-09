import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

import styles from "./Form.module.css";

export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string | null;
  children: ReactNode;
}) {
  return (
    <label className={styles.field}>
      <span className={styles.label}>
        {label}
        {hint && <span className={styles.hint}>{hint}</span>}
      </span>
      {children}
      {error && <span className={styles.fieldError}>{error}</span>}
    </label>
  );
}

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
}

export function Input({ invalid, className, ...rest }: InputProps) {
  return <input className={`${styles.input} ${invalid ? styles.invalid : ""} ${className ?? ""}`} {...rest} />;
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  invalid?: boolean;
}

export function Select({ invalid, className, children, ...rest }: SelectProps) {
  return (
    <select className={`${styles.input} ${invalid ? styles.invalid : ""} ${className ?? ""}`} {...rest}>
      {children}
    </select>
  );
}

interface TextAreaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {}

export function TextArea({ className, ...rest }: TextAreaProps) {
  return <textarea className={`${styles.input} ${className ?? ""}`} {...rest} />;
}

export function ButtonGroup({ children }: { children: ReactNode }) {
  return <div className={styles.buttonGroup}>{children}</div>;
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className={styles.formError} role="alert">
      {message}
    </div>
  );
}