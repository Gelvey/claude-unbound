// Reusable primitives built on daisyUI semantic classes. These mirror the
// old admin.css semantics (.primary-button -> btn-primary, .provider-card ->
// card, status pills -> badge, etc.) so views stay declarative.

import type { ReactNode } from "react";

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
  return <span className={badgeClass[kind]}>{children}</span>;
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
  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/60"
      onClick={(e) => {
        if (e.target === e.currentTarget) onDismiss();
      }}
    >
      <div className="modal-box max-w-md">
        <h3 className="text-lg font-bold text-warning">{title}</h3>
        <div className="mt-3">{children}</div>
      </div>
    </div>
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
