// Reusable primitives built on daisyUI semantic classes. These mirror the
// old admin.css semantics (.primary-button -> btn-primary, .provider-card ->
// card, status pills -> badge, etc.) so views stay declarative.

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { motion } from "motion/react";

type ButtonVariant = "primary" | "secondary" | "ghost";

const buttonClass = (variant: ButtonVariant, disabled = false) => {
  const base = "btn btn-sm rounded-lg font-bold text-[13px]";
  const variantClass =
    variant === "primary"
      ? "btn-primary"
      : variant === "secondary"
        ? "btn-neutral"
        : "btn-ghost";
  return disabled ? `${base} ${variantClass} btn-disabled` : `${base} ${variantClass}`;
};

export function Button({
  variant = "secondary",
  type = "button",
  disabled,
  onClick,
  children,
  title,
}: {
  variant?: ButtonVariant;
  type?: "button" | "submit";
  disabled?: boolean;
  onClick?: () => void;
  children: ReactNode;
  title?: string;
}) {
  return (
    <button
      type={type}
      className={buttonClass(variant, disabled)}
      disabled={disabled}
      onClick={onClick}
      title={title}
    >
      {children}
    </button>
  );
}

export function Input({
  id,
  type = "text",
  value,
  onChange,
  disabled,
  placeholder,
  autoComplete,
  list,
}: {
  id?: string;
  type?: string;
  value: string;
  onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
  disabled?: boolean;
  placeholder?: string;
  autoComplete?: string;
  list?: string;
}) {
  return (
    <input
      id={id}
      type={type}
      value={value}
      onChange={onChange}
      disabled={disabled}
      placeholder={placeholder}
      autoComplete={autoComplete}
      list={list}
      className="input input-sm w-full"
    />
  );
}

export function Textarea({
  id,
  value,
  onChange,
  disabled,
  placeholder,
}: {
  id?: string;
  value: string;
  onChange?: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  disabled?: boolean;
  placeholder?: string;
}) {
  return (
    <textarea
      id={id}
      value={value}
      onChange={onChange}
      disabled={disabled}
      placeholder={placeholder}
      className="textarea textarea-sm w-full min-h-[90px] resize-y"
    />
  );
}

export function Select({
  id,
  value,
  onChange,
  disabled,
  children,
}: {
  id?: string;
  value: string;
  onChange?: (e: React.ChangeEvent<HTMLSelectElement>) => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <select
      id={id}
      value={value}
      onChange={onChange}
      disabled={disabled}
      className="select select-sm w-full"
    >
      {children}
    </select>
  );
}

export function Toggle({
  id,
  checked,
  onChange,
  disabled,
}: {
  id?: string;
  checked: boolean;
  onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
  disabled?: boolean;
}) {
  return (
    <input
      id={id}
      type="checkbox"
      checked={checked}
      onChange={onChange}
      disabled={disabled}
      className="checkbox checkbox-sm"
    />
  );
}

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`card bg-base-200 border border-base-300 rounded-xl p-4 ${className}`}>
      {children}
    </div>
  );
}

type BadgeKind = "ok" | "warn" | "error" | "neutral";

const badgeClass: Record<BadgeKind, string> = {
  ok: "badge badge-success badge-sm",
  warn: "badge badge-warning badge-sm",
  error: "badge badge-error badge-sm",
  neutral: "badge badge-ghost badge-sm",
};

export function Badge({
  kind = "neutral",
  children,
}: {
  kind?: BadgeKind;
  children: ReactNode;
}) {
  return <span className={`${badgeClass[kind]} shrink-0 whitespace-nowrap`}>{children}</span>;
}

export function statusBadgeClass(status: string): BadgeKind {
  if (["configured", "reachable", "running", "ok"].includes(status)) return "ok";
  if (["missing_key", "missing_url", "unknown", "partial"].includes(status)) return "warn";
  if (["offline", "error"].includes(status)) return "error";
  return "neutral";
}

export function Alert({
  kind = "neutral",
  children,
}: {
  kind?: BadgeKind;
  children: ReactNode;
}) {
  const cls =
    kind === "error"
      ? "alert alert-error"
      : kind === "ok"
        ? "alert alert-success"
        : kind === "warn"
          ? "alert alert-warning"
          : "alert";
  return <div className={`${cls} py-2 px-3 rounded-lg text-sm`}>{children}</div>;
}

export function Modal({
  title,
  children,
  onDismiss,
}: {
  title: string;
  children: ReactNode;
  onDismiss: () => void;
}) {
  const [closing, setClosing] = useState(false);
  const handleClose = () => {
    if (closing) return;
    setClosing(true);
    window.setTimeout(onDismiss, 170);
  };
  // Esc-to-close + focus the box on mount.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") handleClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
  // Portal to document.body so the overlay escapes the view's motion.div
  // wrapper: an ancestor with `transform` (even translateY(0)) becomes the
  // containing block for position:fixed descendants and traps them in a
  // sub-stacking-context below the fixed ActionBar/sidebar, hiding the modal.
  return createPortal(
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center"
      onClick={(e) => {
        if (e.target === e.currentTarget) handleClose();
      }}
    >
      <motion.div
        className="absolute inset-0 bg-black/60"
        initial={{ opacity: 0 }}
        animate={{ opacity: closing ? 0 : 1 }}
        transition={{ duration: 0.17, ease: "easeOut" }}
      />
      <motion.div
        className="modal-box max-w-md relative"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        initial={{ opacity: 0, scale: 0.96, y: 8 }}
        animate={{
          opacity: closing ? 0 : 1,
          scale: closing ? 0.96 : 1,
          y: closing ? 8 : 0,
        }}
        transition={{ duration: 0.17, ease: "easeOut" }}
        autoFocus
      >
        <h3 className="text-lg font-bold text-warning">{title}</h3>
        <div className="mt-3">{children}</div>
      </motion.div>
    </div>,
    document.body,
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`skeleton h-8 w-full rounded-lg ${className}`}
      aria-hidden
    />
  );
}
