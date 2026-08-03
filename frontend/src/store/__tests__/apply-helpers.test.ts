import { describe, it, expect } from "vitest";
import type { ConfigField } from "../../types";
import { MASKED_SECRET } from "../../types";
import {
  collectCurrentValues,
  stripMaskedSecret,
  describeApplyResult,
} from "../useAdminStore";

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

describe("collectCurrentValues", () => {
  it("includes non-locked fields as their readFieldValue", () => {
    const fields = [
      field({ key: "A", type: "text", value: "x" }),
      field({ key: "B", type: "boolean", value: "true" }),
    ];
    const out = collectCurrentValues(fields, new Map());
    expect(out).toEqual({ A: "x", B: "true" });
  });

  it("drops locked fields entirely", () => {
    const fields = [field({ key: "A", locked: true, value: "x" })];
    expect(collectCurrentValues(fields, new Map())).toEqual({});
  });

  it("routes CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS into the payload", () => {
    // The backend apply route reads this key to write ~/.claude/settings.json,
    // so it must be present (not stripped, not dropped) — same as any field.
    const fields = [
      field({
        key: "CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS",
        type: "boolean",
        value: "false",
      }),
    ];
    expect(collectCurrentValues(fields, new Map())).toEqual({
      CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS: "false",
    });
  });

  it("surfaces configured secrets as MASKED_SECRET when not retyped", () => {
    const fields = [
      field({
        key: "OPENROUTER_API_KEY",
        type: "secret",
        secret: true,
        configured: true,
        value: "sk-stored",
      }),
    ];
    // computeInitialValue -> "" for secrets; readFieldValue -> MASKED_SECRET.
    expect(collectCurrentValues(fields, new Map())).toEqual({
      OPENROUTER_API_KEY: MASKED_SECRET,
    });
  });
});

describe("stripMaskedSecret", () => {
  it("removes MASKED_SECRET entries so the server preserves stored values", () => {
    const out = stripMaskedSecret({
      KEEP: "value",
      SECRET: MASKED_SECRET,
      OTHER: "abc",
    });
    expect(out).toEqual({ KEEP: "value", OTHER: "abc" });
    expect(JSON.stringify(out)).not.toContain(MASKED_SECRET);
  });

  it("does not strip a retyped secret value that happens to differ", () => {
    expect(stripMaskedSecret({ SECRET: "new-value" })).toEqual({
      SECRET: "new-value",
    });
  });
});

describe("describeApplyResult", () => {
  it("reports an error message when not applied", () => {
    const msg = describeApplyResult({
      applied: false,
      errors: ["bad value", "missing key"],
    });
    expect(msg.kind).toBe("error");
    expect(msg.text).toContain("bad value");
    expect(msg.text).toContain("missing key");
    expect(msg.redirect).toBeUndefined();
  });

  it("redirects when an automatic restart is required", () => {
    const msg = describeApplyResult({
      applied: true,
      restart: {
        required: true,
        automatic: true,
        admin_url: "/admin",
        fields: [],
      },
    });
    expect(msg.kind).toBe("ok");
    expect(msg.text).toContain("Restarting");
    expect(msg.redirect).toBe("/admin");
  });

  it("lists pending fields when a manual restart is required", () => {
    const msg = describeApplyResult({
      applied: true,
      restart: { required: true, automatic: false, admin_url: null, fields: ["MODEL"] },
    });
    expect(msg.kind).toBe("ok");
    expect(msg.text).toContain("Restart fcc-server");
    expect(msg.text).toContain("MODEL");
    expect(msg.redirect).toBeUndefined();
  });

  it("reports a plain Applied when nothing is pending", () => {
    const msg = describeApplyResult({ applied: true });
    expect(msg.kind).toBe("ok");
    expect(msg.text).toBe("Applied");
    expect(msg.redirect).toBeUndefined();
  });

  it("falls back to pending_fields when no restart block is present", () => {
    const msg = describeApplyResult({
      applied: true,
      pending_fields: ["A", "B"],
    });
    expect(msg.kind).toBe("ok");
    expect(msg.text).toContain("A, B");
  });
});
