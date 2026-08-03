import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import {
  applyMcpConfig,
  composioSetup,
  composioTest,
  getMcpConfig,
  getMcpStatus,
  sftpFetch,
  sftpImport,
  validateSftpConfig,
  applySftpConfig,
  type McpBackendEntry,
  type McpBackendType,
  type McpConfig,
  type McpStatus,
  type McpStatusBackend,
  type SftpConfig,
} from "../api/mcp";
import { readFieldValue, useAdminStore } from "../store/useAdminStore";
import { MASKED_SECRET } from "../types";
import { Badge, Button } from "../components/ui";
import { TwoStepConfirm } from "../components/TwoStepConfirm";

// SFTP config-field keys (managed by the global store / global Apply).
const SFTP_KEYS = {
  host: "FCC_SFTP_HOST",
  port: "FCC_SFTP_PORT",
  username: "FCC_SFTP_USERNAME",
  auth_method: "FCC_SFTP_AUTH_METHOD",
  password: "FCC_SFTP_PASSWORD",
  private_key: "FCC_SFTP_PRIVATE_KEY",
  remote_file_path: "FCC_SFTP_REMOTE_FILE_PATH",
  enabled: "FCC_SFTP_ENABLED",
} as const;

type EnvRow = { key: string; value: string; masked: boolean };

interface BackendForm {
  name: string;
  type: McpBackendType;
  port: string;
  command: string;
  args: string;
  env: EnvRow[];
  url: string;
  headers: EnvRow[];
}

interface EditState {
  isShared: boolean;
  originalName: string | null;
  form: BackendForm;
}

function rowsFromMap(map: Record<string, string> | undefined): EnvRow[] {
  if (!map) return [];
  return Object.entries(map).map(([k, v]) => ({
    key: k,
    value: v === MASKED_SECRET ? "" : v,
    masked: v === MASKED_SECRET,
  }));
}

function entryToForm(name: string, entry: McpBackendEntry): BackendForm {
  return {
    name,
    type: entry.type,
    port: String(entry.port ?? 7101),
    command: entry.command ?? "",
    args: (entry.args ?? []).join(", "),
    env: rowsFromMap(entry.env),
    url: entry.url ?? "",
    headers: rowsFromMap(entry.headers),
  };
}

function emptyForm(): BackendForm {
  return {
    name: "",
    type: "stdio",
    port: "7101",
    command: "",
    args: "",
    env: [],
    url: "",
    headers: [],
  };
}

function formToEntry(form: BackendForm): McpBackendEntry {
  const entry: McpBackendEntry = { type: form.type, port: parseInt(form.port, 10) || 7101 };
  if (form.type === "stdio") {
    entry.command = form.command;
    entry.args = form.args.split(",").map((s) => s.trim()).filter(Boolean);
    entry.env = {};
    for (const row of form.env) {
      if (!row.key) continue;
      entry.env[row.key] = row.masked && !row.value ? MASKED_SECRET : row.value;
    }
  } else {
    entry.url = form.url;
    if (form.type === "http") {
      entry.headers = {};
      for (const row of form.headers) {
        if (!row.key) continue;
        entry.headers[row.key] = row.masked && !row.value ? MASKED_SECRET : row.value;
      }
    }
  }
  return entry;
}

function backendMeta(srv: McpBackendEntry): string {
  if (srv.type === "stdio") {
    return `${srv.command || ""} ${(srv.args ?? []).join(" ")} (port ${srv.port})`.trim();
  }
  return `${srv.url || ""} (port ${srv.port})`;
}

export function McpView() {
  const { showMessage, registerViewActivation } = useAdminStore();
  const [config, setConfig] = useState<McpConfig | null>(null);
  const [status, setStatus] = useState<McpStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [edit, setEdit] = useState<EditState | null>(null);

  const loadMcpView = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [cfg, st] = await Promise.all([
        getMcpConfig(),
        getMcpStatus().catch(() => ({ running: false })),
      ]);
      setConfig(cfg);
      setStatus(st);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load MCP config");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadMcpView();
    return registerViewActivation((viewId) => {
      if (viewId === "mcp") void loadMcpView();
    });
  }, [registerViewActivation, loadMcpView]);

  const liveMap = new Map<string, McpStatusBackend>();
  if (status?.backends) {
    for (const b of status.backends) liveMap.set(b.name, b);
  }

  const saveMcpConfig = useCallback(
    async (next: McpConfig) => {
      setBusy(true);
      try {
        const result = await applyMcpConfig(next);
        if (result.applied) {
          showMessage(result.restart_hint || "Saved", "ok");
          setConfig(next);
          await loadMcpView();
        } else {
          showMessage(result.errors.join("; ") || "Validation failed", "error");
        }
      } catch (err) {
        showMessage(err instanceof Error ? `Save failed: ${err.message}` : "Save failed", "error");
      } finally {
        setBusy(false);
      }
    },
    [loadMcpView, showMessage],
  );

  const handleSaveBackend = (form: BackendForm, originalName: string | null, isShared: boolean) => {
    if (!config) return;
    const entry = formToEntry(form);
    const next: McpConfig = { ...config };
    const target = isShared ? { ...config.shared_servers } : { ...config.servers };
    if (originalName && originalName !== form.name) delete target[originalName];
    target[form.name] = entry;
    if (isShared) next.shared_servers = target;
    else next.servers = target;
    setEdit(null);
    void saveMcpConfig(next);
  };

  const handleDeleteBackend = (name: string, isShared: boolean) => {
    if (!config) return;
    const next: McpConfig = { ...config };
    if (isShared) {
      next.shared_servers = { ...config.shared_servers };
      delete next.shared_servers[name];
    } else {
      next.servers = { ...config.servers };
      delete next.servers[name];
    }
    void saveMcpConfig(next);
  };

  const handleRouterFieldChange = (key: keyof McpConfig, value: string) => {
    if (!config) return;
    setConfig({ ...config, [key]: key === "health_timeout_s" ? parseInt(value, 10) || 30 : value });
  };

  if (loading && !config) {
    return <div className="grid gap-3">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} />)}</div>;
  }
  if (error) {
    return <div className="alert alert-error py-3 px-4 rounded-lg text-sm">{error}</div>;
  }
  if (!config) return null;

  return (
    <div className="grid gap-5">
      <McpStatusBanner config={config} status={status} busy={busy} onRefresh={loadMcpView} />

      <ComposioSection config={config} liveMap={liveMap} onReload={loadMcpView} />

      <McpBackendGrid
        label="Local Backends"
        description="Configure MCP server backends managed locally."
        servers={config.servers}
        isShared={false}
        liveMap={liveMap}
        busy={busy}
        onEdit={(name, entry) =>
          setEdit({ isShared: false, originalName: name, form: entryToForm(name, entry) })
        }
        onAdd={() => setEdit({ isShared: false, originalName: null, form: emptyForm() })}
        onDelete={(name) => handleDeleteBackend(name, false)}
      />

      <McpBackendGrid
        label="Shared Backends"
        description="Backends shared across teammates (imported via SFTP or added manually)."
        servers={config.shared_servers}
        isShared
        liveMap={liveMap}
        busy={busy}
        onEdit={(name, entry) =>
          setEdit({ isShared: true, originalName: name, form: entryToForm(name, entry) })
        }
        onAdd={() => setEdit({ isShared: true, originalName: null, form: emptyForm() })}
        onDelete={(name) => handleDeleteBackend(name, true)}
      />

      <RouterSettings config={config} onChange={handleRouterFieldChange} onSave={() => void saveMcpConfig(config)} busy={busy} />

      <SftpSection />

      {edit && (
        <McpEditModal
          state={edit}
          onClose={() => setEdit(null)}
          onSave={(form, originalName, isShared) => handleSaveBackend(form, originalName, isShared)}
        />
      )}
    </div>
  );
}

function Skeleton() {
  return <div className="skeleton h-8 w-full rounded-lg" aria-hidden />;
}

function McpStatusBanner({
  config,
  status,
  busy,
  onRefresh,
}: {
  config: McpConfig;
  status: McpStatus | null;
  busy: boolean;
  onRefresh: () => void;
}) {
  const running = status?.running ?? false;
  return (
    <div className="rounded-lg border border-base-300 bg-base-200 p-4 flex items-center gap-3 flex-wrap">
      <Badge kind={running ? "ok" : "warn"}>{running ? "Running" : "Not running"}</Badge>
      <span className="text-sm">
        {running
          ? `MCP Router is active (${config.router_socket})`
          : "MCP Router is not running. Start it from the launcher or run "}
        {!running && <code className="px-1 py-0.5 rounded bg-base-300 text-xs">bash scripts/mcp/start_mcp.sh</code>}
      </span>
      <Button variant="secondary" disabled={busy} onClick={onRefresh} title="Refresh status">
        {busy ? "Refreshing..." : "Refresh Status"}
      </Button>
    </div>
  );
}

function McpBackendGrid({
  label,
  description,
  servers,
  isShared,
  liveMap,
  busy,
  onEdit,
  onAdd,
  onDelete,
}: {
  label: string;
  description: string;
  servers: Record<string, McpBackendEntry>;
  isShared: boolean;
  liveMap: Map<string, McpStatusBackend>;
  busy: boolean;
  onEdit: (name: string, entry: McpBackendEntry) => void;
  onAdd: () => void;
  onDelete: (name: string) => void;
}) {
  const names = Object.keys(servers);
  return (
    <section className="rounded-xl border border-base-300 bg-base-200 p-5 scroll-mt-5">
      <div className="mb-4 flex items-center justify-between gap-2">
        <div>
          <h3 className="text-base font-bold">{label}</h3>
          <p className="text-xs text-base-content/60 mt-0.5">{description}</p>
        </div>
        <Button variant="primary" disabled={busy} onClick={onAdd}>+ Add Backend</Button>
      </div>
      <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(280px,1fr))]">
        {names.length === 0 && (
          <div className="text-sm text-base-content/50 italic">No backends configured.</div>
        )}
        {names.map((name) => {
          const srv = servers[name];
          const live = liveMap.get(name);
          const displayName = isShared ? `[shared] ${name}` : name;
          const pillKind = live
            ? live.activated
              ? "ok"
              : "neutral"
            : "neutral";
          const pillText = live
            ? live.activated
              ? `${live.tool_count} tool(s)`
              : "configured"
            : srv.type || "stdio";
          return (
            <article
              key={name}
              className="grid gap-2 min-h-[108px] border border-base-300 rounded-lg p-3.5 bg-base-100 hover:border-base-content/30 transition"
            >
              <div className="flex items-center justify-between gap-2">
                <strong className="text-sm break-all">{displayName}</strong>
                <Badge kind={pillKind}>{pillText}</Badge>
              </div>
              <div className="text-xs text-base-content/60 break-words">{backendMeta(srv)}</div>
              {isShared && (
                <div className="text-xs font-semibold text-base-content/70">Imported via SFTP</div>
              )}
              <div className="flex gap-2 mt-auto">
                <Button variant="secondary" onClick={() => onEdit(name, srv)}>Edit</Button>
                <TwoStepConfirm
                  label="Delete"
                  confirmLabel="Confirm Delete?"
                  variant="ghost"
                  onConfirm={() => onDelete(name)}
                />
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function RouterSettings({
  config,
  onChange,
  onSave,
  busy,
}: {
  config: McpConfig;
  onChange: (key: keyof McpConfig, value: string) => void;
  onSave: () => void;
  busy: boolean;
}) {
  const fields: { key: keyof McpConfig; label: string; value: string }[] = [
    { key: "router_socket", label: "Socket Path", value: config.router_socket },
    { key: "router_log", label: "Log Path", value: config.router_log },
    { key: "router_pidfile", label: "PID File", value: config.router_pidfile },
    { key: "health_timeout_s", label: "Health Timeout (s)", value: String(config.health_timeout_s) },
  ];
  return (
    <section className="rounded-xl border border-base-300 bg-base-200 p-5 scroll-mt-5">
      <div className="mb-4">
        <h3 className="text-base font-bold">Router Settings</h3>
        <p className="text-xs text-base-content/60 mt-0.5">Socket path, log path, and health timeout.</p>
      </div>
      <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(260px,1fr))]">
        {fields.map((f) => (
          <label key={f.key} className="grid gap-1.5">
            <span className="text-xs font-semibold text-base-content/70">{f.label}</span>
            <input
              type="text"
              className="input input-sm w-full"
              value={f.value}
              onChange={(e) => onChange(f.key, e.target.value)}
            />
          </label>
        ))}
      </div>
      <div className="mt-4">
        <Button variant="primary" disabled={busy} onClick={onSave}>Save Router Settings</Button>
      </div>
    </section>
  );
}

function McpEditModal({
  state,
  onClose,
  onSave,
}: {
  state: EditState;
  onClose: () => void;
  onSave: (form: BackendForm, originalName: string | null, isShared: boolean) => void;
}) {
  const { form } = state;
  const [draft, setDraft] = useState<BackendForm>(form);

  const set = <K extends keyof BackendForm>(key: K, value: BackendForm[K]) =>
    setDraft((prev) => ({ ...prev, [key]: value }));

  const showStdio = draft.type === "stdio";
  const showUrl = draft.type === "sse" || draft.type === "http";
  const showHeaders = draft.type === "http";

  const addRow = (which: "env" | "headers") =>
    set(which, [...draft[which], { key: "", value: "", masked: false }]);

  const removeRow = (which: "env" | "headers", idx: number) =>
    set(which, draft[which].filter((_, i) => i !== idx));

  const handleSave = () => {
    if (!draft.name.trim()) return;
    onSave(draft, state.originalName, state.isShared);
  };

  // Portal to document.body so the overlay escapes the view's motion.div
  // wrapper: an ancestor with `transform` (even translateY(0)) becomes the
  // containing block for position:fixed descendants and traps them in a
  // sub-stacking-context below the fixed ActionBar/sidebar, hiding the modal.
  return createPortal(
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/60 p-4" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-box max-w-2xl max-h-[90vh] overflow-y-auto">
        <h3 className="text-lg font-bold mb-4">
          {state.originalName ? "Edit Backend" : "Add Backend"}
          {state.isShared && " (shared)"}
        </h3>
        <div className="grid gap-4">
          <label className="grid gap-1.5">
            <span className="text-xs font-semibold text-base-content/70">Name</span>
            <input
              type="text"
              className="input input-sm w-full"
              value={draft.name}
              disabled={state.originalName !== null}
              onChange={(e) => set("name", e.target.value)}
              placeholder="backend-name"
            />
          </label>
          <label className="grid gap-1.5">
            <span className="text-xs font-semibold text-base-content/70">Type</span>
            <select
              className="select select-sm w-full"
              value={draft.type}
              onChange={(e) => set("type", e.target.value as McpBackendType)}
            >
              <option value="stdio">stdio</option>
              <option value="sse">sse</option>
              <option value="http">http</option>
            </select>
          </label>
          <label className="grid gap-1.5">
            <span className="text-xs font-semibold text-base-content/70">Port</span>
            <input
              type="number"
              className="input input-sm w-full"
              value={draft.port}
              onChange={(e) => set("port", e.target.value)}
            />
          </label>

          {showStdio && (
            <>
              <label className="grid gap-1.5">
                <span className="text-xs font-semibold text-base-content/70">Command</span>
                <input
                  type="text"
                  className="input input-sm w-full"
                  value={draft.command}
                  onChange={(e) => set("command", e.target.value)}
                  placeholder="e.g. npx"
                />
              </label>
              <label className="grid gap-1.5">
                <span className="text-xs font-semibold text-base-content/70">Args (comma-separated)</span>
                <input
                  type="text"
                  className="input input-sm w-full"
                  value={draft.args}
                  onChange={(e) => set("args", e.target.value)}
                  placeholder="e.g. -y, @modelcontextprotocol/server-filesystem"
                />
              </label>
              <div className="grid gap-1.5">
                <span className="text-xs font-semibold text-base-content/70">Environment Variables</span>
                <EnvRows rows={draft.env} onChange={(r) => set("env", r)} onRemove={(i) => removeRow("env", i)} />
                <Button variant="ghost" onClick={() => addRow("env")}>+ Add env var</Button>
              </div>
            </>
          )}

          {showUrl && (
            <label className="grid gap-1.5">
              <span className="text-xs font-semibold text-base-content/70">URL</span>
              <input
                type="text"
                className="input input-sm w-full"
                value={draft.url}
                onChange={(e) => set("url", e.target.value)}
                placeholder="https://..."
              />
            </label>
          )}

          {showHeaders && (
            <>
              <p className="text-xs text-base-content/60">
                Authentication headers (e.g., <code>x-consumer-api-key</code> for Composio).
              </p>
              <div className="grid gap-1.5">
                <span className="text-xs font-semibold text-base-content/70">HTTP Headers</span>
                <EnvRows rows={draft.headers} onChange={(r) => set("headers", r)} onRemove={(i) => removeRow("headers", i)} />
                <Button variant="ghost" onClick={() => addRow("headers")}>+ Add header</Button>
              </div>
            </>
          )}
        </div>
        <div className="flex gap-2 justify-end mt-6">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={handleSave} disabled={!draft.name.trim()}>Save</Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

function EnvRows({
  rows,
  onChange,
  onRemove,
}: {
  rows: EnvRow[];
  onChange: (rows: EnvRow[]) => void;
  onRemove: (idx: number) => void;
}) {
  if (rows.length === 0) {
    return <div className="text-xs text-base-content/40 italic">No entries.</div>;
  }
  return (
    <div className="grid gap-2">
      {rows.map((row, idx) => (
        <div key={idx} className="flex gap-2 items-center">
          <input
            type="text"
            className="input input-sm flex-1"
            placeholder="KEY"
            value={row.key}
            onChange={(e) => onChange(rows.map((r, i) => (i === idx ? { ...r, key: e.target.value } : r)))}
          />
          <input
            type={row.masked ? "password" : "text"}
            className="input input-sm flex-1"
            placeholder={row.masked ? "Leave empty to keep unchanged" : "VALUE"}
            value={row.value}
            title={row.masked ? "Masked — leave empty to keep unchanged" : undefined}
            onChange={(e) => onChange(rows.map((r, i) => (i === idx ? { ...r, value: e.target.value } : r)))}
          />
          <Button variant="ghost" onClick={() => onRemove(idx)}>x</Button>
        </div>
      ))}
    </div>
  );
}

// ---- SFTP section (fields wired to the global store / global Apply) ----

function SftpSection() {
  const { fields, fieldValues, setFieldValue, showMessage, registerViewActivation, reload } = useAdminStore();
  const [preview, setPreview] = useState<{ name: string; entry: McpBackendEntry }[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [localMsg, setLocalMsg] = useState<{ text: string; kind: "ok" | "error" | "" } | null>(null);

  useEffect(() => {
    return registerViewActivation((viewId) => {
      if (viewId === "mcp") setPreview(null);
    });
  }, [registerViewActivation]);

  const field = (key: string) => fields.get(key);
  const val = (key: string) => fieldValues.get(key) ?? "";
  const sftpHost = val(SFTP_KEYS.host);
  const sftpPort = val(SFTP_KEYS.port) || "22";
  const sftpUsername = val(SFTP_KEYS.username);
  const sftpAuthMethod = val(SFTP_KEYS.auth_method) || "password";
  const sftpRemotePath = val(SFTP_KEYS.remote_file_path);
  const sftpEnabled = val(SFTP_KEYS.enabled) === "true";

  const passwordField = field(SFTP_KEYS.password);
  const keyField = field(SFTP_KEYS.private_key);
  const passwordConfigured = passwordField?.configured ?? false;
  const keyConfigured = keyField?.configured ?? false;

  const enabled = sftpEnabled && !!sftpHost;

  const readSftpValues = (): SftpConfig => {
    const f = (k: string) => fields.get(k);
    return {
      host: val(SFTP_KEYS.host),
      port: parseInt(val(SFTP_KEYS.port), 10) || 22,
      username: val(SFTP_KEYS.username),
      auth_method: val(SFTP_KEYS.auth_method) || "password",
      password: readFieldValue(f(SFTP_KEYS.password)!, val(SFTP_KEYS.password)),
      private_key: readFieldValue(f(SFTP_KEYS.private_key)!, val(SFTP_KEYS.private_key)),
      remote_file_path: val(SFTP_KEYS.remote_file_path),
      enabled: val(SFTP_KEYS.enabled) === "true",
    };
  };

  const handleTestConnection = async () => {
    setBusy(true);
    setLocalMsg(null);
    setPreview(null);
    try {
      const values = readSftpValues();
      const validateResult = await validateSftpConfig(values);
      if (!validateResult.valid) {
        setLocalMsg({ text: validateResult.errors.join("; "), kind: "error" });
        return;
      }
      await applySftpConfig(values);
      const fetchResult = await sftpFetch();
      if (fetchResult.ok && fetchResult.config) {
        const entries = Object.entries(fetchResult.config.servers || {});
        setPreview(entries.map(([name, entry]) => ({ name, entry })));
        setLocalMsg({ text: `Connection successful. Found ${entries.length} remote backend(s).`, kind: "ok" });
      } else {
        setLocalMsg({ text: fetchResult.error || "Fetch failed", kind: "error" });
      }
    } catch (err) {
      setLocalMsg({ text: err instanceof Error ? err.message : "Test failed", kind: "error" });
    } finally {
      setBusy(false);
    }
  };

  const handleFetch = async () => {
    setBusy(true);
    setLocalMsg(null);
    setPreview(null);
    try {
      const values = readSftpValues();
      await applySftpConfig(values);
      const result = await sftpFetch();
      if (result.ok && result.config) {
        const entries = Object.entries(result.config.servers || {});
        setPreview(entries.map(([name, entry]) => ({ name, entry })));
        setLocalMsg({ text: `Fetched ${entries.length} remote backend(s).`, kind: "ok" });
      } else {
        setLocalMsg({ text: result.error || "Fetch failed", kind: "error" });
      }
    } catch (err) {
      setLocalMsg({ text: err instanceof Error ? err.message : "Fetch failed", kind: "error" });
    } finally {
      setBusy(false);
    }
  };

  const handleImport = async (mode: "merge" | "replace") => {
    setBusy(true);
    try {
      const result = await sftpImport(mode);
      if (result.ok) {
        showMessage(`Imported ${result.imported_count ?? 0} backend(s) (${mode}). Reloading...`, "ok");
        setPreview(null);
        await reload();
      } else {
        setLocalMsg({ text: result.error || "Import failed", kind: "error" });
      }
    } catch (err) {
      setLocalMsg({ text: err instanceof Error ? err.message : "Import failed", kind: "error" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-xl border border-base-300 bg-base-200 p-5 scroll-mt-5">
      <div className="mb-4">
        <h3 className="text-base font-bold">SFTP Shared Config</h3>
        <p className="text-xs text-base-content/60 mt-0.5">
          Set up SFTP credentials to share MCP config across teammates. Fields apply via the global Apply button.
        </p>
      </div>
      <div className="rounded-lg border border-base-300 bg-base-100 p-3 mb-4 flex items-center gap-3 flex-wrap">
        <Badge kind={enabled ? "ok" : "neutral"}>{enabled ? "Enabled" : "Not configured"}</Badge>
        <span className="text-sm">
          {enabled
            ? `SFTP configured: ${sftpUsername}@${sftpHost}:${sftpPort} -> ${sftpRemotePath}`
            : "Set up SFTP credentials to share MCP config across teammates."}
        </span>
      </div>
      <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(260px,1fr))]">
        <SftpInput label="Host" value={sftpHost} placeholder="e.g. sftp.example.com" onChange={(v) => setFieldValue(SFTP_KEYS.host, v)} />
        <SftpInput label="Port" value={sftpPort} type="number" placeholder="22" onChange={(v) => setFieldValue(SFTP_KEYS.port, v)} />
        <SftpInput label="Username" value={sftpUsername} placeholder="e.g. teamuser" onChange={(v) => setFieldValue(SFTP_KEYS.username, v)} />
        <label className="grid gap-1.5">
          <span className="text-xs font-semibold text-base-content/70">Auth Method</span>
          <select
            className="select select-sm w-full"
            value={sftpAuthMethod}
            onChange={(e) => setFieldValue(SFTP_KEYS.auth_method, e.target.value)}
          >
            <option value="password">Password</option>
            <option value="key">Private Key</option>
          </select>
        </label>
        {sftpAuthMethod === "password" && (
          <SftpSecretInput
            label="Password"
            configured={passwordConfigured}
            value={val(SFTP_KEYS.password)}
            placeholder="Enter password"
            onChange={(v) => setFieldValue(SFTP_KEYS.password, v)}
          />
        )}
        {sftpAuthMethod === "key" && (
          <label className="grid gap-1.5">
            <span className="text-xs font-semibold text-base-content/70">Private Key</span>
            <textarea
              className="textarea textarea-sm w-full min-h-[90px] resize-y"
              placeholder={keyConfigured ? "Configured — enter a new value to replace" : "Paste private key"}
              value={val(SFTP_KEYS.private_key)}
              onChange={(e) => setFieldValue(SFTP_KEYS.private_key, e.target.value)}
            />
          </label>
        )}
        <SftpInput label="Remote File Path" value={sftpRemotePath} placeholder="/home/team/shared-mcp/mcp_config.json" onChange={(v) => setFieldValue(SFTP_KEYS.remote_file_path, v)} />
        <label className="grid gap-1.5">
          <span className="text-xs font-semibold text-base-content/70">Enabled</span>
          <input
            type="checkbox"
            className="checkbox checkbox-sm"
            checked={sftpEnabled}
            onChange={(e) => setFieldValue(SFTP_KEYS.enabled, e.target.checked ? "true" : "false")}
          />
        </label>
      </div>
      <div className="flex gap-2 flex-wrap mt-4">
        <Button variant="secondary" disabled={busy} onClick={handleTestConnection} title="Validate, save, and test SFTP connection">
          {busy ? "Working..." : "Test Connection"}
        </Button>
        <Button variant="primary" disabled={busy} onClick={handleFetch} title="Save and fetch remote config">
          {busy ? "Working..." : "Fetch Remote Config"}
        </Button>
      </div>
      {localMsg && (
        <div className={`mt-3 text-sm ${localMsg.kind === "ok" ? "text-success" : localMsg.kind === "error" ? "text-error" : ""}`}>
          {localMsg.text}
        </div>
      )}
      {preview && (
        <div className="mt-4 rounded-lg border border-base-300 bg-base-100 p-4">
          <div className="flex items-center justify-between mb-3">
            <strong className="text-sm">Remote Backends ({preview.length})</strong>
            <span className="text-xs text-base-content/60">Review before importing</span>
          </div>
          <div className="grid gap-2 mb-4">
            {preview.map(({ name, entry }) => (
              <article key={name} className="grid gap-1 border border-base-300 rounded-lg p-3 bg-base-200">
                <div className="flex items-center justify-between gap-2">
                  <strong className="text-sm break-all">{name}</strong>
                  <Badge kind="neutral">{entry.type || "stdio"}</Badge>
                </div>
                <div className="text-xs text-base-content/60 break-words">{backendMeta(entry)}</div>
              </article>
            ))}
          </div>
          <div className="flex gap-2 flex-wrap">
            <Button variant="primary" disabled={busy} onClick={() => void handleImport("merge")}>Merge into Local</Button>
            <TwoStepConfirm
              label="Replace All Local"
              confirmLabel="Confirm Replace All?"
              variant="secondary"
              disabled={busy}
              onConfirm={() => handleImport("replace")}
            />
          </div>
        </div>
      )}
    </section>
  );
}

function SftpInput({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <label className="grid gap-1.5">
      <span className="text-xs font-semibold text-base-content/70">{label}</span>
      <input
        type={type}
        className="input input-sm w-full"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

function SftpSecretInput({
  label,
  configured,
  value,
  placeholder,
  onChange,
}: {
  label: string;
  configured: boolean;
  value: string;
  placeholder: string;
  onChange: (v: string) => void;
}) {
  const [reveal, setReveal] = useState(false);
  return (
    <label className="grid gap-1.5">
      <span className="text-xs font-semibold text-base-content/70">{label}</span>
      <div className="flex gap-1">
        <input
          type={reveal ? "text" : "password"}
          className="input input-sm w-full"
          value={value}
          placeholder={configured ? "Configured — enter a new value to replace" : placeholder}
          onChange={(e) => onChange(e.target.value)}
        />
        <Button variant="ghost" onClick={() => setReveal((r) => !r)} title={reveal ? "Hide" : "Show"}>
          {reveal ? "🔒" : "👁"}
        </Button>
      </div>
    </label>
  );
}

// ---- Composio section ----

function ComposioSection({
  config,
  liveMap,
  onReload,
}: {
  config: McpConfig;
  liveMap: Map<string, McpStatusBackend>;
  onReload: () => Promise<void>;
}) {
  const { showMessage } = useAdminStore();
  const composio = config.servers.composio;
  const composioLive = liveMap.get("composio");
  const composioShared = findComposioShared(config);
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);

  const handleConnect = async () => {
    if (!apiKey.trim()) return;
    setBusy(true);
    try {
      const result = await composioSetup(apiKey);
      if (result.applied) {
        showMessage("Composio connected successfully", "ok");
        setApiKey("");
        await onReload();
      } else {
        showMessage(result.errors.join("; ") || "Setup failed", "error");
      }
    } catch (err) {
      showMessage(err instanceof Error ? err.message : "Setup failed", "error");
    } finally {
      setBusy(false);
    }
  };

  const handleUpdateKey = async () => {
    if (!apiKey.trim() || !composio) return;
    setBusy(true);
    try {
      const result = await composioSetup(apiKey, composio.port);
      if (result.applied) {
        showMessage("Composio API key updated", "ok");
        setApiKey("");
        await onReload();
      } else {
        showMessage(result.errors.join("; ") || "Update failed", "error");
      }
    } catch (err) {
      showMessage(err instanceof Error ? err.message : "Update failed", "error");
    } finally {
      setBusy(false);
    }
  };

  const handleTest = async () => {
    setBusy(true);
    try {
      const result = await composioTest(apiKey || undefined);
      if (result.ok) {
        showMessage(`Composio OK (${apiKey ? "new key" : "current key"}): ${result.tool_count} tools available`, "ok");
      } else {
        showMessage(`Composio test failed: ${result.error}`, "error");
      }
    } catch (err) {
      showMessage(err instanceof Error ? err.message : "Test failed", "error");
    } finally {
      setBusy(false);
    }
  };

  const handleRemove = async () => {
    if (!composio) return;
    const next: McpConfig = { ...config, servers: { ...config.servers } };
    delete next.servers.composio;
    setBusy(true);
    try {
      const result = await applyMcpConfig(next);
      if (result.applied) {
        showMessage("Composio removed", "ok");
        await onReload();
      } else {
        showMessage(result.errors.join("; ") || "Remove failed", "error");
      }
    } catch (err) {
      showMessage(err instanceof Error ? err.message : "Remove failed", "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-xl border border-base-300 bg-base-200 p-5 scroll-mt-5">
      <div className="mb-4">
        <h3 className="text-base font-bold">Composio</h3>
        <p className="text-xs text-base-content/60 mt-0.5">
          {composio
            ? "Connected to Composio MCP marketplace."
            : "Connect to Composio's MCP marketplace. Get an API key at composio.dev."}
        </p>
      </div>
      {composioShared && (
        <div className="text-xs text-base-content/60 mb-3">
          Also configured as a shared server: &lsquo;{composioShared}&rsquo;. Manage it from the Shared Backends section.
        </div>
      )}
      {!composio ? (
        <div className="grid gap-3 max-w-md">
          <label className="grid gap-1.5">
            <span className="text-xs font-semibold text-base-content/70">Composio API Key</span>
            <input
              type="password"
              className="input input-sm w-full"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="ak_..."
            />
          </label>
          <Button variant="primary" disabled={busy || !apiKey.trim()} onClick={handleConnect}>
            {busy ? "Connecting..." : "Connect Composio"}
          </Button>
        </div>
      ) : (
        <div className="grid gap-3">
          <div className="flex items-center gap-3 flex-wrap">
            <Badge kind={composioLive?.activated ? "ok" : "neutral"}>
              {composioLive?.activated
                ? `${composioLive.tool_count} tool(s) available`
                : composioLive
                  ? "Configured (not activated)"
                  : "Configured"}
            </Badge>
            {composioLive?.tool_names && composioLive.tool_names.length > 0 && (
              <span className="text-xs text-base-content/60">{composioLive.tool_names.join(", ")}</span>
            )}
          </div>
          <label className="grid gap-1.5 max-w-md">
            <span className="text-xs font-semibold text-base-content/70">Update API Key</span>
            <input
              type="password"
              className="input input-sm w-full"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="Enter new key to replace"
            />
            <span className="text-xs text-base-content/50">Leave empty and click Test Connection to verify the currently saved key.</span>
          </label>
          <div className="flex gap-2 flex-wrap">
            <Button variant="secondary" disabled={busy} onClick={handleTest}>Test Connection</Button>
            <Button variant="primary" disabled={busy || !apiKey.trim()} onClick={handleUpdateKey}>Update Key</Button>
            <TwoStepConfirm
              label="Remove"
              confirmLabel="Confirm Remove?"
              variant="ghost"
              disabled={busy}
              onConfirm={handleRemove}
            />
          </div>
        </div>
      )}
    </section>
  );
}

function findComposioShared(config: McpConfig): string | null {
  for (const [name, srv] of Object.entries(config.shared_servers)) {
    if (name === "composio-shared") return name;
    if (srv.url && srv.url.includes("composio.dev")) return name;
  }
  return null;
}
