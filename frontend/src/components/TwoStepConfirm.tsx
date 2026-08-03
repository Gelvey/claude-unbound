// Two-step confirm button: first click arms (label swaps, 4s auto-disarm),
// second click fires. Ports wireTwoStepConfirm from the old admin.js.

import { useEffect, useRef, useState } from "react";

type Variant = "primary" | "secondary" | "ghost";

const variantClass = (variant: Variant) =>
  variant === "primary" ? "btn-primary" : variant === "secondary" ? "btn-neutral" : "btn-ghost";

export function TwoStepConfirm({
  label,
  confirmLabel = "Confirm?",
  onConfirm,
  variant = "ghost",
  disabled = false,
  title,
}: {
  label: string;
  confirmLabel?: string;
  onConfirm: () => Promise<void> | void;
  variant?: Variant;
  disabled?: boolean;
  title?: string;
}) {
  const [armed, setArmed] = useState(false);
  const [working, setWorking] = useState(false);
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const reset = () => {
    setArmed(false);
    if (resetTimer.current) {
      clearTimeout(resetTimer.current);
      resetTimer.current = null;
    }
  };

  useEffect(() => () => reset(), []);

  const handleClick = async () => {
    if (working || disabled) return;
    if (!armed) {
      setArmed(true);
      resetTimer.current = setTimeout(reset, 4000);
      return;
    }
    setWorking(true);
    try {
      await onConfirm();
    } finally {
      setWorking(false);
      reset();
    }
  };

  const base = "btn btn-sm rounded-lg font-bold text-[13px]";
  const cls = working
    ? `${base} ${variantClass(variant)} btn-disabled`
    : `${base} ${variantClass(variant)}${armed ? " btn-warning" : ""}`;

  return (
    <button
      type="button"
      className={cls}
      disabled={disabled || working}
      onClick={handleClick}
      title={title}
    >
      {working ? "Working..." : armed ? confirmLabel : label}
    </button>
  );
}
