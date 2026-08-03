import { useState } from "react";
import type { ConfigField } from "../types";
import { RESTART_MODAL_KEYS } from "../types";
import { useAdminStore } from "../store/useAdminStore";
import { Modal } from "./ui";

// sourceLabel/sourceText mirror admin.js exactly.
const SOURCE_LABELS: Record<string, string> = {
  default: "default",
  template: "template",
  repo_env: "repo .env",
  managed_env: "",
  explicit_env_file: "FCC_ENV_FILE",
  process: "process env",
  settings_json: "settings.json",
};

function sourceLabel(source: string): string {
  return Object.prototype.hasOwnProperty.call(SOURCE_LABELS, source)
    ? SOURCE_LABELS[source]
    : source;
}

function sourceText(field: ConfigField): string {
  const parts: string[] = [];
  const label = sourceLabel(field.source);
  if (label) parts.push(label);
  if (field.locked) parts.push("locked");
  return parts.join(" ");
}

export function Field({ field }: { field: ConfigField }) {
  const store = useAdminStore();
  const inputId = `field-${field.key}`;
  const currentValue = store.fieldValues.get(field.key) ?? "";
  const [showRestart, setShowRestart] = useState(false);
  const [revealed, setRevealed] = useState(false);

  const onChange = (raw: string) => {
    store.setFieldValue(field.key, raw);
    if (RESTART_MODAL_KEYS.has(field.key) && field.type === "boolean" && raw === "true") {
      setShowRestart(true);
    }
  };

  const source = sourceText(field);

  return (
    <div className="grid gap-1.5 content-start min-w-0">
      <label
        htmlFor={inputId}
        className="flex items-center justify-between gap-2 text-xs font-bold uppercase tracking-wide text-base-content/60"
      >
        <span>{field.label}</span>
        {source && <span className="text-[11px] font-semibold text-base-content/50">{source}</span>}
      </label>

      <FieldInput
        field={field}
        inputId={inputId}
        currentValue={currentValue}
        onChange={onChange}
        revealed={revealed}
        setRevealed={setRevealed}
      />

      {field.description && (
        <div className="text-xs text-base-content/60 leading-snug">{field.description}</div>
      )}

      {showRestart && (
        <Modal title="Restart Required" onDismiss={() => setShowRestart(false)}>
          <p>Claude Unbound will need to be restarted to take effect.</p>
          <div className="mt-4 flex justify-end">
            <button
              type="button"
              className="btn btn-sm btn-primary rounded-lg"
              onClick={() => setShowRestart(false)}
            >
              OK
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function FieldInput({
  field,
  inputId,
  currentValue,
  onChange,
  revealed,
  setRevealed,
}: {
  field: ConfigField;
  inputId: string;
  currentValue: string;
  onChange: (raw: string) => void;
  revealed: boolean;
  setRevealed: (v: boolean) => void;
}) {
  if (field.type === "boolean") {
    const checked = currentValue === "true";
    return (
      <input
        id={inputId}
        type="checkbox"
        checked={checked}
        disabled={field.locked}
        onChange={(e) => onChange(e.target.checked ? "true" : "false")}
        className="checkbox checkbox-sm"
      />
    );
  }

  if (field.type === "tri_boolean") {
    return (
      <select
        id={inputId}
        value={currentValue}
        disabled={field.locked}
        onChange={(e) => onChange(e.target.value)}
        className="select select-sm w-full"
      >
        <option value="">Inherit</option>
        <option value="true">Enabled</option>
        <option value="false">Disabled</option>
      </select>
    );
  }

  if (field.type === "select") {
    return (
      <select
        id={inputId}
        value={currentValue}
        disabled={field.locked}
        onChange={(e) => onChange(e.target.value)}
        className="select select-sm w-full"
      >
        {field.options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    );
  }

  if (field.type === "textarea") {
    return (
      <textarea
        id={inputId}
        value={currentValue}
        disabled={field.locked}
        onChange={(e) => onChange(e.target.value)}
        className="textarea textarea-sm w-full min-h-[90px] resize-y"
      />
    );
  }

  if (field.type === "secret") {
    return (
      <div className="flex gap-1.5 items-center">
        <input
          id={inputId}
          type={revealed ? "text" : "password"}
          value={currentValue}
          disabled={field.locked}
          autoComplete="off"
          placeholder={
            field.configured
              ? "Configured - enter a new value to replace"
              : "Not configured"
          }
          onChange={(e) => onChange(e.target.value)}
          className="input input-sm w-full flex-1"
        />
        <button
          type="button"
          className="btn btn-sm btn-ghost rounded-lg min-w-[36px]"
          title="Show/hide"
          onClick={() => setRevealed(!revealed)}
        >
          {revealed ? "🔒" : "👁"}
        </button>
      </div>
    );
  }

  // text | number
  const listAttr = field.model_options ? "model-options" : undefined;
  return (
    <input
      id={inputId}
      type={field.type === "number" ? "number" : "text"}
      value={currentValue}
      disabled={field.locked}
      list={listAttr}
      onChange={(e) => onChange(e.target.value)}
      className="input input-sm w-full"
    />
  );
}

// Config path copy button (ports attachCopyButton).
export function CopyButton({
  target,
  label = "Copy",
}: {
  target: string;
  label?: string;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className={`btn btn-xs rounded-md ${copied ? "btn-success" : "btn-ghost"}`}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(target);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          /* clipboard unavailable */
        }
      }}
    >
      {copied ? "Copied" : label}
    </button>
  );
}

// Shared <datalist> for model_options autocomplete (ports syncModelDatalist).
export function ModelOptionsDatalist() {
  const store = useAdminStore();
  return (
    <datalist id="model-options">
      {store.modelOptions.map((m) => (
        <option key={m} value={m} />
      ))}
    </datalist>
  );
}
