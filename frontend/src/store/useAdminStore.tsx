import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import * as configApi from "../api/config";
import * as providersApi from "../api/providers";
import * as modulesApi from "../api/modules";
import type {
  ApplyResult,
  ConfigField,
  ConfigResponse,
  LocalProviderCheck,
  ModuleTab,
  ProviderStatusEntry,
  ValidationResult,
} from "../types";
import { MASKED_SECRET } from "../types";

// View groups mirror VIEW_GROUPS in the old admin.js. Complex views (mcp,
// freebuff, graphify, openrouter_policy) render placeholders in Phase 1 and
// get bespoke widgets in Phase 2.
export interface ViewGroup {
  id: string;
  label: string;
  title: string;
  sections: string[];
  moduleTab?: boolean;
}

export const VIEW_GROUPS: ViewGroup[] = [
  { id: "providers", label: "Providers", title: "Providers", sections: ["providers", "runtime"] },
  { id: "model_config", label: "Model Config", title: "Model Config", sections: ["models", "thinking", "permissions", "web_tools"] },
  { id: "messaging", label: "Messaging", title: "Messaging", sections: ["messaging", "voice"] },
  { id: "openrouter_policy", label: "OpenRouter", title: "OpenRouter Policy", sections: ["openrouter_policy"] },
  { id: "cloudflare", label: "CloudFlare AI", title: "Cloudflare Workers AI", sections: ["cloudflare"] },
  { id: "mcp", label: "MCP Router", title: "MCP Router", sections: [] },
  { id: "freebuff", label: "Freebuff", title: "Freebuff2API", sections: ["freebuff"] },
  { id: "graphify", label: "Graphify", title: "Graphify", sections: ["graphify"] },
  { id: "diagnostics", label: "Diagnostics", title: "Diagnostics & Logging", sections: ["diagnostics", "smoke"] },
];

export interface AdminMessage {
  text: string;
  kind: "" | "ok" | "error";
}

interface AdminStoreValue {
  config: ConfigResponse | null;
  fields: Map<string, ConfigField>;
  fieldValues: Map<string, string>;
  originalValues: Map<string, string>;
  localStatus: Map<string, LocalProviderCheck>;
  providerStatus: ProviderStatusEntry[];
  modelOptions: string[];
  activeView: string;
  message: AdminMessage;
  configPath: string;
  dirtyCount: number;
  totalCount: number;
  applyDisabled: boolean;
  loading: boolean;
  lastChecked: Date | null;
  views: ViewGroup[];
  moduleTabs: ModuleTab[];
  setActiveView: (id: string) => void;
  setFieldValue: (key: string, value: string) => void;
  validate: (showResult?: boolean) => Promise<ValidationResult>;
  apply: () => Promise<void>;
  showMessage: (text: string, kind?: "" | "ok" | "error") => void;
  testProvider: (providerId: string) => Promise<void>;
  refreshLocalStatus: () => Promise<void>;
  reload: () => Promise<void>;
  viewActivationCallbacks: ((viewId: string) => void)[];
  registerViewActivation: (cb: (viewId: string) => void) => () => void;
}

const AdminStoreContext = createContext<AdminStoreValue | null>(null);

// The original value used for dirty comparison (mirrors renderField's
// dataset.original, with boolean special-cased per inputForField).
function computeOriginal(field: ConfigField): string {
  if (field.type === "boolean") {
    return String(field.value).toLowerCase() === "true" ? "true" : "false";
  }
  return field.value || "";
}

// The value the input is initialized with (what the user sees on load).
function computeInitialValue(field: ConfigField): string {
  if (field.type === "boolean") {
    return String(field.value).toLowerCase() === "true" ? "true" : "false";
  }
  if (field.type === "secret") {
    return "";
  }
  if (field.type === "select") {
    return field.value || field.options[0] || "";
  }
  return field.value || "";
}

// readFieldValue mirrors admin.js: secret+configured+empty -> MASKED_SECRET.
function readFieldValue(field: ConfigField, currentValue: string): string {
  if (field.type === "boolean") {
    return currentValue === "true" ? "true" : "false";
  }
  if (field.secret && field.configured && currentValue === "") {
    return MASKED_SECRET;
  }
  return currentValue;
}

export function AdminStoreProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [fieldValues, setFieldValues] = useState<Map<string, string>>(new Map());
  const [originalValues, setOriginalValues] = useState<Map<string, string>>(new Map());
  const [fields, setFields] = useState<Map<string, ConfigField>>(new Map());
  const [localStatus, setLocalStatus] = useState<Map<string, LocalProviderCheck>>(new Map());
  const [providerStatus, setProviderStatus] = useState<ProviderStatusEntry[]>([]);
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [activeView, setActiveViewState] = useState("providers");
  const [message, setMessage] = useState<AdminMessage>({ text: "", kind: "" });
  const [configPath, setConfigPath] = useState("");
  const [loading, setLoading] = useState(true);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const [moduleViews, setModuleViews] = useState<ViewGroup[]>([]);
  const [moduleTabs, setModuleTabs] = useState<ModuleTab[]>([]);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const activationCallbacksRef = useRef<((viewId: string) => void)[]>([]);

  const showMessage = useCallback((text: string, kind: "" | "ok" | "error" = "") => {
    setMessage({ text, kind });
  }, []);

  const views = useMemo(() => {
    const seen = new Set(VIEW_GROUPS.map((v) => v.id));
    const merged = [...VIEW_GROUPS];
    for (const mv of moduleViews) {
      if (!seen.has(mv.id)) {
        merged.push(mv);
        seen.add(mv.id);
      }
    }
    return merged;
  }, [moduleViews]);

  const loadModuleTabs = useCallback(async () => {
    try {
      const payload = await modulesApi.getModuleTabs();
      const tabs = payload.tabs || [];
      setModuleTabs(tabs);
      const newViews: ViewGroup[] = [];
      for (const tab of tabs) {
        if (!tab.id) continue;
        if (VIEW_GROUPS.some((v) => v.id === tab.id)) continue;
        newViews.push({
          id: tab.id,
          label: tab.label || tab.id,
          title: tab.title || tab.label || tab.id,
          sections: [tab.id],
          moduleTab: true,
        });
      }
      if (newViews.length) setModuleViews(newViews);
    } catch {
      // Endpoint may not exist on older builds; non-fatal.
    }
  }, []);

  const refreshLocalStatus = useCallback(async () => {
    try {
      const result = await providersApi.getLocalStatus();
      setLastChecked(new Date());
      const next = new Map(localStatus);
      for (const provider of result.providers) {
        next.set(provider.provider_id, provider);
      }
      setLocalStatus(next);
    } catch {
      // Swallow transient polling errors.
    }
  }, [localStatus]);

  const reload = useCallback(async () => {
    showMessage("Loading admin config");
    setLoading(true);
    try {
      const cfg = await configApi.getConfig();
      setConfig(cfg);
      const fieldMap = new Map(cfg.fields.map((f) => [f.key, f]));
      setFields(fieldMap);
      setOriginalValues(new Map(cfg.fields.map((f) => [f.key, computeOriginal(f)])));
      setFieldValues(new Map(cfg.fields.map((f) => [f.key, computeInitialValue(f)])));
      setProviderStatus(cfg.provider_status);
      setConfigPath(cfg.paths.managed);
      await loadModuleTabs();
      await refreshLocalStatus();
    } catch (err) {
      showMessage(err instanceof Error ? err.message : "Failed to load config", "error");
    } finally {
      setLoading(false);
    }
  }, [loadModuleTabs, refreshLocalStatus, showMessage]);

  // Initial load + status polling (60s, mirroring startStatusPolling).
  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    pollTimerRef.current = setInterval(() => {
      void refreshLocalStatus();
    }, 60000);
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, [refreshLocalStatus]);

  const setFieldValue = useCallback((key: string, value: string) => {
    setFieldValues((prev) => {
      const next = new Map(prev);
      next.set(key, value);
      return next;
    });
  }, []);

  const { dirtyCount, totalCount } = useMemo(() => {
    if (!config) return { dirtyCount: 0, totalCount: 0 };
    let changed = 0;
    let total = 0;
    for (const field of config.fields) {
      if (field.locked) continue;
      total++;
      const current = fieldValues.get(field.key) ?? computeInitialValue(field);
      const original = originalValues.get(field.key) ?? computeOriginal(field);
      if (readFieldValue(field, current) !== original) {
        changed++;
      }
    }
    return { dirtyCount: changed, totalCount: total };
  }, [config, fieldValues, originalValues]);

  const changedValues = useCallback((): Record<string, string> => {
    if (!config) return {};
    const values: Record<string, string> = {};
    for (const field of config.fields) {
      if (field.locked) continue;
      const current = fieldValues.get(field.key) ?? computeInitialValue(field);
      const original = originalValues.get(field.key) ?? computeOriginal(field);
      const value = readFieldValue(field, current);
      if (value !== original) {
        values[field.key] = value;
      }
    }
    return values;
  }, [config, fieldValues, originalValues]);

  const allCurrentValues = useCallback((): Record<string, string> => {
    if (!config) return {};
    const values: Record<string, string> = {};
    for (const field of config.fields) {
      if (field.locked) continue;
      const current = fieldValues.get(field.key) ?? computeInitialValue(field);
      values[field.key] = readFieldValue(field, current);
    }
    return values;
  }, [config, fieldValues]);

  const validate = useCallback(
    async (showResult = true): Promise<ValidationResult> => {
      const result = await configApi.validateValues(changedValues());
      if (showResult) {
        if (result.valid) {
          showMessage("Config shape is valid", "ok");
        } else {
          showMessage(result.errors.join("; "), "error");
        }
      }
      return result;
    },
    [changedValues, showMessage],
  );

  const apply = useCallback(async (): Promise<void> => {
    const values = allCurrentValues();
    // Don't send the masked sentinel for unchanged secrets; the server preserves
    // existing values. Mirrors admin.js apply().
    for (const key of Object.keys(values)) {
      if (values[key] === MASKED_SECRET) delete values[key];
    }
    try {
      const result: ApplyResult = await configApi.applyConfig(values);
      if (!result.applied) {
        if (result.errors) showMessage(result.errors.join("; "), "error");
        return;
      }
      const restart = result.restart ?? {
        required: false,
        automatic: false,
        admin_url: null as string | null,
        fields: [] as string[],
      };
      if (restart.required && restart.automatic) {
        showMessage("Applied. Restarting server...", "ok");
        setTimeout(() => {
          window.location.href = restart.admin_url || "/admin";
        }, 1600);
        return;
      }
      await reload();
      // Re-fire activation so the active complex view (mcp/freebuff/graphify/
      // openrouter_policy) reloads its view-specific state after a global apply,
      // mirroring the old admin.js apply() post-apply reload.
      for (const cb of activationCallbacksRef.current) {
        cb(activeView);
      }
      const pending = restart.required ? restart.fields || [] : result.pending_fields || [];
      showMessage(
        pending.length
          ? `Applied. Restart fcc-server to use: ${pending.join(", ")}`
          : "Applied",
        "ok",
      );
    } catch (err) {
      showMessage(err instanceof Error ? err.message : "Apply failed", "error");
    }
  }, [allCurrentValues, reload, showMessage, activeView]);

  const testProvider = useCallback(
    async (providerId: string): Promise<void> => {
      try {
        const result = await providersApi.testProvider(providerId);
        if (result.ok && result.models) {
          setModelOptions((prev) =>
            Array.from(
              new Set([
                ...prev,
                ...result.models!.map((m) => `${providerId}/${m}`),
              ]),
            ).sort(),
          );
        }
      } catch (err) {
        showMessage(
          err instanceof Error ? `Provider test failed: ${err.message}` : "Provider test failed",
          "error",
        );
      }
    },
    [showMessage],
  );

  const setActiveView = useCallback((id: string) => {
    setActiveViewState(id);
    for (const cb of activationCallbacksRef.current) {
      cb(id);
    }
  }, []);

  const registerViewActivation = useCallback((cb: (viewId: string) => void) => {
    activationCallbacksRef.current.push(cb);
    return () => {
      activationCallbacksRef.current = activationCallbacksRef.current.filter(
        (c) => c !== cb,
      );
    };
  }, []);

  const value: AdminStoreValue = {
    config,
    fields,
    fieldValues,
    originalValues,
    localStatus,
    providerStatus,
    modelOptions,
    activeView,
    message,
    configPath,
    dirtyCount,
    totalCount,
    applyDisabled: dirtyCount === 0,
    loading,
    lastChecked,
    views,
    moduleTabs,
    setActiveView,
    setFieldValue,
    validate,
    apply,
    showMessage,
    testProvider,
    refreshLocalStatus,
    reload,
    viewActivationCallbacks: activationCallbacksRef.current,
    registerViewActivation,
  };

  return (
    <AdminStoreContext.Provider value={value}>
      {children}
    </AdminStoreContext.Provider>
  );
}

export function useAdminStore(): AdminStoreValue {
  const ctx = useContext(AdminStoreContext);
  if (!ctx) throw new Error("useAdminStore must be used inside AdminStoreProvider");
  return ctx;
}

export { readFieldValue, computeInitialValue, computeOriginal };
