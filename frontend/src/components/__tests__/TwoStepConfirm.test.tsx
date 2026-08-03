import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act, cleanup } from "@testing-library/react";
import { TwoStepConfirm } from "../TwoStepConfirm";

describe("<TwoStepConfirm>", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("arms on first click (label swaps to confirm label)", () => {
    const onConfirm = vi.fn();
    render(
      <TwoStepConfirm label="Delete" confirmLabel="Confirm?" onConfirm={onConfirm} />,
    );
    const btn = screen.getByRole("button", { name: "Delete" });
    fireEvent.click(btn);
    expect(screen.getByRole("button", { name: "Delete — press again to confirm" }));
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("fires onConfirm on the second click", () => {
    const onConfirm = vi.fn();
    render(
      <TwoStepConfirm label="Delete" confirmLabel="Confirm?" onConfirm={onConfirm} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete — press again to confirm" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("auto-disarms after 4s without a second click", () => {
    const onConfirm = vi.fn();
    render(
      <TwoStepConfirm label="Delete" confirmLabel="Confirm?" onConfirm={onConfirm} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    act(() => {
      vi.advanceTimersByTime(4000);
    });
    // Back to the unarmed label.
    expect(screen.getByRole("button", { name: "Delete" }));
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("resets to the armed label after firing", async () => {
    const onConfirm = vi.fn();
    render(
      <TwoStepConfirm label="Delete" confirmLabel="Confirm?" onConfirm={onConfirm} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Delete — press again to confirm" }));
    });
    expect(onConfirm).toHaveBeenCalled();
    // After firing (and the onConfirm microtask drains), the button returns to
    // the original label.
    expect(screen.getByRole("button", { name: "Delete" }));
  });

  it("does nothing when disabled", () => {
    const onConfirm = vi.fn();
    render(
      <TwoStepConfirm label="Delete" confirmLabel="Confirm?" onConfirm={onConfirm} disabled />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(onConfirm).not.toHaveBeenCalled();
    // Still showing the original label (never armed) — disabled buttons can't arm.
    expect(screen.getByRole("button", { name: "Delete" }));
  });
});
