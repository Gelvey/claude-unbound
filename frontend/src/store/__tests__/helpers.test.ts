import { describe, it, expect } from "vitest";
import {
  readFieldValue,
  computeOriginal,
  computeInitialValue,
} from "../useAdminStore";
import { MASKED_SECRET, RESTART_MODAL_KEYS } from "../../types";
import type { ConfigField } from "../../types";

function field(overrides: Partial<ConfigField>): ConfigField {
  return {
    key: "TEST",
    label: "Test",
    section: "test",
    type: "text",
    value: "",
    configured: false,
    source: "default",
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

describe("computeOriginal", () => {
  it("normalizes booleans to 'true'/'false' strings", () => {
    expect(computeOriginal(field({ type: "boolean", value: "True" }))).toBe("true");
    expect(computeOriginal(field({ type: "boolean", value: false }))).toBe("false");
    expect(computeOriginal(field({ type: "boolean", value: "" }))).toBe("false");
  });

  it("returns the raw value for non-boolean fields, '' when empty", () => {
    expect(computeOriginal(field({ type: "text", value: "abc" }))).toBe("abc");
    expect(computeOriginal(field({ type: "secret", value: "" }))).toBe("");
  });
});

describe("computeInitialValue", () => {
  it("normalizes booleans", () => {
    expect(computeInitialValue(field({ type: "boolean", value: "True" }))).toBe("true");
    expect(computeInitialValue(field({ type: "boolean", value: "no" }))).toBe("false");
  });

  it("secrets start empty so the masked sentinel can show", () => {
    expect(computeInitialValue(field({ type: "secret", value: "sk-xxx" }))).toBe("");
  });

  it("select falls back to the first option when value is empty", () => {
    expect(
      computeInitialValue(field({ type: "select", value: "", options: ["a", "b"] })),
    ).toBe("a");
    expect(
      computeInitialValue(field({ type: "select", value: "b", options: ["a", "b"] })),
    ).toBe("b");
  });
});

describe("readFieldValue (MASKED_SECRET logic)", () => {
  it("masks configured secrets that the user has not retyped", () => {
    expect(
      readFieldValue(field({ type: "secret", secret: true, configured: true }), ""),
    ).toBe(MASKED_SECRET);
  });

  it("does not mask an unconfigured secret (empty stays empty)", () => {
    expect(
      readFieldValue(field({ type: "secret", secret: true, configured: false }), ""),
    ).toBe("");
  });

  it("does not mask a secret the user has started typing", () => {
    expect(
      readFieldValue(field({ type: "secret", secret: true, configured: true }), "new"),
    ).toBe("new");
  });

  it("normalizes booleans", () => {
    expect(readFieldValue(field({ type: "boolean" }), "true")).toBe("true");
    expect(readFieldValue(field({ type: "boolean" }), "anything-else")).toBe("false");
  });

  it("passes through plain text values", () => {
    expect(readFieldValue(field({ type: "text" }), "hello")).toBe("hello");
  });
});

describe("RESTART_MODAL_KEYS", () => {
  it("flags the Claude and Codex dangerous-approval keys", () => {
    expect(RESTART_MODAL_KEYS.has("CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS")).toBe(true);
    expect(RESTART_MODAL_KEYS.has("CODEX_DANGEROUSLY_BYPASS_APPROVALS")).toBe(true);
  });
});
