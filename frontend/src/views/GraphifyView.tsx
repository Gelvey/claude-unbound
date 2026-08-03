import { useCallback, useEffect, useRef, useState } from "react";
import {
  graphifyAddProject,
  graphifyGraph,
  graphifyHealth,
  graphifyIndex,
  graphifyIndexStatus,
  graphifyPathB64,
  graphifyProjects,
  graphifyRemoveProject,
  graphifyRestart,
  graphifySetup,
  graphifyStart,
  graphifyStatus,
  graphifyStop,
  type GraphifyHealth,
  type GraphifyProject,
  type GraphifyStatus,
} from "../api/graphify";
import { useAdminStore } from "../store/useAdminStore";
import { Badge, Button } from "../components/ui";
import { FormSections } from "../components/FormSections";
import { TwoStepConfirm } from "../components/TwoStepConfirm";

type PillKind = "ok" | "warn" | "error" | "neutral";

function graphifyStatusPill(status: string): PillKind {
  if (status === "ready") return "ok";
  if (status === "indexing" || status === "queued") return "warn";
  if (status === "error") return "error";
  if (status === "stale") return "warn";
  return "neutral";
}

function graphifyHealthPill(health: GraphifyHealth | null, running: boolean): { kind: PillKind; label: string } {
  if (!running) return { kind: "neutral", label: "Stopped" };
  if (!health) return { kind: "neutral", label: "Stopped" };
  if (health.status === "healthy") return { kind: "ok", label: "Healthy" };
  if (health.status === "unhealthy") return { kind: "error", label: "Unhealthy" };
  if (health.status === "not_configured" || health.status === "not_running") return { kind: "neutral", label: "Not configured" };
  return { kind: "warn", label: "Unreachable" };
}

const fmtNum = (n: number | undefined): string => (n ?? 0).toLocaleString();

export function GraphifyView() {
  const { config, showMessage, registerViewActivation, activeView } = useAdminStore();
  const [status, setStatus] = useState<GraphifyStatus | null>(null);
  const [projects, setProjects] = useState<GraphifyProject[]>([]);
  const [health, setHealth] = useState<GraphifyHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [newPath, setNewPath] = useState("");
  const refreshTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadGraphifyView = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [st, hd, pr] = await Promise.all([
        graphifyStatus(),
        graphifyHealth().catch(() => ({ status: "unreachable" }) as GraphifyHealth),
        graphifyProjects(),
      ]);
      setStatus(st);
      setHealth(hd);
      setProjects(pr.projects || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load Graphify");
    } finally {
      setLoading(false);
    }
  }, []);

  const stopAutoRefresh = useCallback(() => {
    if (refreshTimerRef.current) {
      clearInterval(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
  }, []);

  const startAutoRefreshIfBusy = useCallback(() => {
    const isBusy = projects.some((p) => p.status === "indexing" || p.status === "queued");
    if (!isBusy) {
      stopAutoRefresh();
      return;
    }
    if (refreshTimerRef.current) return;
    refreshTimerRef.current = setInterval(async () => {
      if (activeView !== "graphify") {
        stopAutoRefresh();
        return;
      }
      try {
        const [st, pr] = await Promise.all([graphifyStatus(), graphifyProjects()]);
        setStatus(st);
        setProjects(pr.projects || []);
      } catch {
        // Transient polling errors are swallowed.
      }
    }, 10000);
  }, [projects, activeView, stopAutoRefresh]);

  useEffect(() => {
    void loadGraphifyView();
    return registerViewActivation((viewId) => {
      if (viewId === "graphify") {
        void loadGraphifyView();
      } else {
        stopAutoRefresh();
      }
    });
  }, [registerViewActivation, loadGraphifyView, stopAutoRefresh]);

  useEffect(() => {
    startAutoRefreshIfBusy();
    return () => stopAutoRefresh();
  }, [startAutoRefreshIfBusy, stopAutoRefresh]);

  const runAction = useCallback(
    async (label: string, fn: () => Promise<{ success?: boolean; error?: string; ready?: boolean; method?: string; python?: string }>, successMsg: string) => {
      setBusy(true);
      try {
        const result = await fn();
        if (result.success === false || result.ready === false) {
          showMessage(`${label} failed: ${result.error || "unknown error"}`, "error");
        } else if (label === "Setup") {
          showMessage(`Graphify ready -- ${result.method} (${result.python})`, "ok");
        } else {
          showMessage(successMsg, "ok");
        }
        await loadGraphifyView();
      } catch (err) {
        showMessage(err instanceof Error ? `${label} failed: ${err.message}` : `${label} failed`, "error");
      } finally {
        setBusy(false);
      }
    },
    [loadGraphifyView, showMessage],
  );

  const handleAddProject = async () => {
    const path = newPath.trim();
    if (!path) return;
    setBusy(true);
    try {
      await graphifyAddProject(path);
      setNewPath("");
      await loadGraphifyView();
    } catch (err) {
      showMessage(err instanceof Error ? `Add failed: ${err.message}` : "Add failed", "error");
    } finally {
      setBusy(false);
    }
  };

  const handleRemoveProject = async (projectPath: string) => {
    setBusy(true);
    try {
      await graphifyRemoveProject(graphifyPathB64(projectPath));
      await loadGraphifyView();
    } catch (err) {
      showMessage(err instanceof Error ? err.message : "Remove failed", "error");
    } finally {
      setBusy(false);
    }
  };

  if (loading && !status) {
    return <div className="grid gap-3">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} />)}</div>;
  }
  if (error) {
    return <div className="alert alert-error py-3 px-4 rounded-lg text-sm">{error}</div>;
  }
  if (!status) return null;

  const hp = graphifyHealthPill(health, status.running);
  const runPill: { kind: PillKind; label: string } = status.running
    ? { kind: "ok", label: "Running" }
    : status.last_error
      ? { kind: "error", label: "Error" }
      : { kind: "neutral", label: "Stopped" };
  const projectCount = status.projects_count ?? projects.length;
  const backendInfo = status.code_only
    ? " . code-only"
    : ` . backend ${status.llm_backend ?? "?"} (${status.llm_model ?? "?"})`;

  return (
    <div className="grid gap-5">
      <div className="rounded-lg border border-base-300 bg-base-200 p-4 flex items-center gap-3 flex-wrap">
        <Badge kind={runPill.kind}>{runPill.label}</Badge>
        <Badge kind={hp.kind}>{hp.label}</Badge>
        <Badge kind={status.mcp_registered ? "ok" : "neutral"}>
          {status.mcp_registered ? "MCP registered" : "MCP unregistered"}
        </Badge>
        <span className="text-sm">
          Graphify . local MCP server (isolated venv, no Docker)
          {status.port ? ` . port ${status.port}` : ""}
          {status.python ? ` . ${status.python}` : ""}
          {` . ${projectCount} project(s)`}
          {backendInfo}
        </span>
      </div>

      <p className="text-sm text-base-content/70 px-1">
        Graphify is a self-hosted knowledge-graph MCP server. It runs an isolated Python venv (no Docker) as a local
        HTTP MCP process on 127.0.0.1, sibling to the MCP Router. Add project repos to index their code into a
        queryable graph.
      </p>

      {status.last_error && (
        <div className="alert alert-warning py-3 px-4 rounded-lg text-sm">
          <Badge kind="error">Error</Badge>
          <span className="ml-1">{status.last_error}</span>
        </div>
      )}

      <div className="flex gap-2 flex-wrap">
        <Button variant="secondary" disabled={busy} onClick={() => runAction("Setup", graphifySetup, "")}>Setup</Button>
        <Button variant="primary" disabled={busy} onClick={() => runAction("Start", graphifyStart, "Graphify started")}>Start</Button>
        <Button variant="secondary" disabled={busy} onClick={() => runAction("Stop", graphifyStop, "Graphify stopped")}>Stop</Button>
        <Button variant="secondary" disabled={busy} onClick={() => runAction("Restart", graphifyRestart, "Graphify restarted")}>Restart</Button>
        <Button variant="secondary" disabled={busy} onClick={loadGraphifyView}>Refresh</Button>
      </div>

      <section className="rounded-xl border border-base-300 bg-base-200 p-5 scroll-mt-5">
        <div className="mb-4">
          <h3 className="text-base font-bold">Projects</h3>
          <p className="text-xs text-base-content/60 mt-0.5">Knowledge-graph projects tracked by Graphify.</p>
        </div>
        <div className="flex gap-2 mb-4">
          <input
            type="text"
            className="input input-sm flex-1"
            placeholder="Absolute repo path"
            value={newPath}
            onChange={(e) => setNewPath(e.target.value)}
          />
          <Button variant="primary" disabled={busy || !newPath.trim()} onClick={handleAddProject}>Add Project</Button>
        </div>

        {status.index_queue_length && status.index_queue_length > 0 && status.index_queue ? (
          <div className="alert alert-warning py-2 px-3 rounded-lg text-sm mb-4 flex items-center gap-2">
            <Badge kind="warn">Indexing</Badge>
            <span>
              {status.index_queue.find((q) => q.status === "indexing")?.path
                ? `${status.index_queue.find((q) => q.status === "indexing")?.path} is indexing`
                : ""}
              {status.index_queue.filter((q) => q.status === "queued").length > 0
                ? ` . ${status.index_queue.filter((q) => q.status === "queued").length} project(s) queued`
                : ""}
            </span>
          </div>
        ) : null}

        <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(300px,1fr))]">
          {projects.length === 0 && (
            <div className="text-sm text-base-content/50 italic">No projects added yet.</div>
          )}
          {projects.map((project) => (
            <GraphifyProjectCard
              key={project.path}
              project={project}
              busy={busy}
              onReload={loadGraphifyView}
              onRemove={() => handleRemoveProject(project.path)}
            />
          ))}
        </div>
      </section>

      {config && <FormSections sectionIds={["graphify"]} sections={config.sections} fields={config.fields} />}
    </div>
  );
}

function Skeleton() {
  return <div className="skeleton h-8 w-full rounded-lg" aria-hidden />;
}

function GraphifyProjectCard({
  project,
  busy,
  onReload,
  onRemove,
}: {
  project: GraphifyProject;
  busy: boolean;
  onReload: () => Promise<void>;
  onRemove: () => void;
}) {
  const { showMessage } = useAdminStore();
  const [indexing, setIndexing] = useState(false);
  const [indexLabel, setIndexLabel] = useState("Index");
  const [graphSummary, setGraphSummary] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Lazy-fetch graph summary when the project is ready.
  useEffect(() => {
    if (project.status !== "ready") return;
    let cancelled = false;
    void (async () => {
      try {
        const summary = await graphifyGraph(graphifyPathB64(project.path));
        if (cancelled) return;
        if (summary.present) {
          const commit = summary.built_at_commit ? summary.built_at_commit.slice(0, 7) : "unknown";
          setGraphSummary(
            `${fmtNum(summary.node_count)} nodes . ${fmtNum(summary.link_count)} links . ${fmtNum(summary.hyperedge_count)} hyperedges . commit ${commit}`,
          );
        } else {
          setGraphSummary("Graph not built yet");
        }
      } catch {
        // Swallow — leaves the summary slot empty.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [project.status, project.path]);

  useEffect(() => () => {
    if (pollRef.current) clearInterval(pollRef.current);
  }, []);

  const handleIndex = async () => {
    const pathB64 = graphifyPathB64(project.path);
    setIndexing(true);
    setIndexLabel("Indexing...");
    try {
      await graphifyIndex(pathB64);
      const started = Date.now();
      pollRef.current = setInterval(async () => {
        try {
          const st = await graphifyIndexStatus(pathB64);
          if (st.status === "indexing") {
            const elapsed = Math.round((Date.now() - started) / 1000);
            setIndexLabel(`Indexing (${elapsed}s)`);
          } else if (st.status === "queued") {
            setIndexLabel(st.queue_position != null ? `Queued (#${st.queue_position})` : "Queued");
          } else if (st.status === "ready") {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setIndexing(false);
            setIndexLabel("Index");
            showMessage("Index complete", "ok");
            await onReload();
          } else {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setIndexing(false);
            setIndexLabel("Index");
            showMessage(st.error_message || "Index failed", "error");
            await onReload();
          }
        } catch {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setIndexing(false);
          setIndexLabel("Index");
        }
      }, 1000);
    } catch (err) {
      setIndexing(false);
      setIndexLabel("Index");
      showMessage(err instanceof Error ? err.message : "Index failed", "error");
    }
  };

  const pillKind = graphifyStatusPill(project.status);
  const pillText = `${project.status || "missing"}${project.status === "indexing" ? " ⟳" : ""}${project.status === "queued" ? " ⏳" : ""}`;

  return (
    <article className="grid gap-2 border border-base-300 rounded-lg p-3.5 bg-base-100 hover:border-base-content/30 transition">
      <div className="flex items-center justify-between gap-2">
        <strong className="text-sm break-all">{project.name || project.path}</strong>
        <Badge kind={pillKind}>{pillText}</Badge>
      </div>
      <div className="text-xs text-base-content/60 break-words">{project.path}</div>
      <div className="text-xs text-base-content/60">
        {project.last_indexed ? `Last indexed: ${new Date(project.last_indexed).toLocaleString()}` : "Not indexed yet"}
      </div>
      {graphSummary && <div className="text-xs text-base-content/70">{graphSummary}</div>}
      {project.status === "error" && project.error_message && (
        <div className="text-xs text-error">{project.error_message}</div>
      )}
      <div className="flex gap-2 mt-auto">
        <Button variant="secondary" disabled={busy || indexing} onClick={handleIndex}>{indexLabel}</Button>
        <TwoStepConfirm
          label="Remove"
          confirmLabel="Confirm Remove?"
          variant="ghost"
          disabled={busy}
          onConfirm={onRemove}
        />
      </div>
    </article>
  );
}
