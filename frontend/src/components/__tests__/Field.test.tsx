import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import type { ConfigField } from "../../types";
import { Field } from "../Field";

// Stub the store hook — Field only needs fieldValues + setFieldValue. Using
// vi.hoisted keeps the stub reference alive across the mock factory and the
// test body (the factory is evaluated before top-level `let` bindings).
const { stub } = vi.hoisted(() => ({
  stub: {
    fieldValues: new Map<string, string>(),
    setFieldValue: () => {},
  },
}));

vi.mock("../../store/useAdminStore", () => ({
  useAdminStore: () => stub,
}));

function field(overrides: Partial<ConfigField>): ConfigField {
  return {
    key: "TEST",
    label: "Test",
    section: "s",
    type: "text",
    value: "",
    configured: false,
    source: "managed_env",
    locked: false,
    secret: false,
    advanced: false,
    restart_required: false,
    session_sensitive: false,
    options: [],
    model_options: false,
    description: "",
    ...overrides,
  };
}

function withField(f: ConfigField, children: ReactNode = null) {
  return (
    <div>
      <Field field={f} />
      {children}
    </div>
  );
}

beforeEach(() => {
  stub.fieldValues = new Map();
  stub.setFieldValue = vi.fn();
});
afterEach(() => cleanup());

describe("<Field> input types", () => {
  it("renders a text input for type=text", () => {
    render(withField(field({ type: "text", value: "abc" })));
    stub.fieldValues.set("TEST", "abc");
    const input = screen.getByLabelText("Test");
    expect(input).toHaveAttribute("type", "text");
  });

  it("renders a number input for type=number", () => {
    render(withField(field({ type: "number", value: "5" })));
    const input = screen.getByLabelText("Test");
    expect(input).toHaveAttribute("type", "number");
  });

  it("renders a checkbox for type=boolean", () => {
    render(withField(field({ type: "boolean", value: "true" })));
    stub.fieldValues.set("TEST", "true");
    expect(screen.getByLabelText("Test")).toHaveAttribute("type", "checkbox");
  });

  it("renders a 3-option select for tri_boolean", () => {
    render(withField(field({ type: "tri_boolean" })));
    const select = screen.getByLabelText("Test") as HTMLSelectElement;
    expect(select.tagName).toBe("SELECT");
    expect(Array.from(select.options).map((o) => o.value)).toEqual(["", "true", "false"]);
  });

  it("renders options from field.options for type=select", () => {
    render(withField(field({ type: "select", options: ["a", "b", "c"] })));
    const select = screen.getByLabelText("Test") as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => o.value)).toEqual(["a", "b", "c"]);
  });

  it("renders a textarea for type=textarea", () => {
    render(withField(field({ type: "textarea", value: "line" })));
    expect(screen.getByLabelText("Test").tagName).toBe("TEXTAREA");
  });

  it("disables the input when locked", () => {
    render(withField(field({ type: "text", locked: true })));
    // The source span appends "locked" to the label text; match by prefix.
    expect(screen.getByLabelText(/^Test/)).toBeDisabled();
  });
});

describe("<Field> secret masking", () => {
  it("uses a password input and a configured placeholder when configured", () => {
    render(withField(field({ type: "secret", secret: true, configured: true })));
    const input = screen.getByLabelText("Test");
    expect(input).toHaveAttribute("type", "password");
    expect(input).toHaveAttribute("placeholder", "Configured - enter a new value to replace");
  });

  it("reveals the value when the eye toggle is clicked", async () => {
    render(withField(field({ type: "secret", secret: true, configured: false })));
    const input = screen.getByLabelText("Test");
    expect(input).toHaveAttribute("type", "password");
    await userEvent.click(screen.getByTitle("Show/hide"));
    expect(input).toHaveAttribute("type", "text");
  });
});

describe("<Field> dirty-state", () => {
  it("calls setFieldValue when the text input changes", async () => {
    render(withField(field({ type: "text" })));
    await userEvent.type(screen.getByLabelText("Test"), "x");
    expect(stub.setFieldValue).toHaveBeenCalledWith("TEST", "x");
  });

  it("toggles a boolean to 'true'/'false' strings", async () => {
    render(withField(field({ type: "boolean", value: "false" })));
    const checkbox = screen.getByLabelText("Test");
    await userEvent.click(checkbox);
    expect(stub.setFieldValue).toHaveBeenCalledWith("TEST", "true");
  });
});

describe("<Field> restart modal", () => {
  it("shows the restart modal when a RESTART_MODAL_KEYS boolean flips to true", async () => {
    render(
      withField(
        field({
          key: "CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS",
          label: "Skip perms",
          type: "boolean",
          value: "false",
        }),
      ),
    );
    expect(screen.queryByRole("dialog")).toBeNull();
    const checkbox = screen.getByLabelText("Skip perms");
    await userEvent.click(checkbox);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/Restart Required/i)).toBeInTheDocument();
  });

  it("does not show the restart modal for a non-restart boolean key", async () => {
    render(withField(field({ key: "OTHER_BOOL", type: "boolean", value: "false" })));
    await userEvent.click(screen.getByLabelText("Test"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
