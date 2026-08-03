import { useCallback, useEffect, useState } from "react";
import {
  freebuffHealth,
  freebuffModels,
  freebuffRestart,
  freebuffSetup,
  freebuffStart,
  freebuffStop,
  getFreebuffStatus,
  type FreebuffContainer,
  type FreebuffHealth,
  type FreebuffStatus,
  type FreebuffTokenState,
} from "../api/freebuff";
import { useAdminStore } from "../store/useAdminStore";
import { Badge, Button } from "../components/ui";
import { FormSections } from "../components/FormSections";

export function FreebuffView() {
  const { config, showMessage, registerViewActivation } = useAdminStore();
  const [status, setStatus] = useState<FreebuffStatus | null>(null);
  const [health, setHealth] = useState<FreebuffHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadFreebuffView = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [st, hd] = await Promise.all([
        getFreebuffStatus(),
        freebuffHealth().catch(() => ({ status: "unreachable" }) as FreebuffHealth),
      ]);
      setStatus(st);
      setHealth(hd);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load Freebuff status");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    return registerViewActivation((viewId) => {
      if (viewId === "freebuff") void loadFreebuffView();
    });
  }, [registerViewActivation, loadFreebuffView]);

  const runAction = useCallback(
    async (
      label: string,
      fn: () => Promise<{ success?: boolean; error?: string; status?: string }>,
      successMsg: (r: { success?: boolean; error?: string; status?: string }) => string,
    ) => {
      setBusy(true);
      try {
        const result = await fn();
        if (result.success === false) {
          showMessage(`${label} failed: ${result.error || "unknown error"}`, "error");
        } else {
          showMessage(successMsg(result), "ok");
        }
        await loadFreebuffView();
      } catch (err) {
        showMessage(err instanceof Error ? `${label} failed: ${err.message}` : `${label} failed`, "error");
      } finally {
        setBusy(false);
      }
    },
    [loadFreebuffView, showMessage],
  );

  if (loading && !status) {
    return <div className="grid gap-3">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} />)}</div>;
  }
  if (error) {
    return <div className="alert alert-error py-3 px-4 rounded-lg text-sm">{error}</div>;
  }
  if (!status) return null;

  const runStart = () => runAction(
    "Start",
    () => freebuffStart(),
    (r) => r.success ? "Freebuff started successfully" : (r.error || "Start failed - check Docker logs"),
  );
  const runStop = () => runAction("Stop", () => freebuffStop(), () => "Freebuff stopped");
  const runRestart = () => runAction("Restart", () => freebuffRestart(), (r) => r.success ? "Freebuff restarted" : "Restart failed");
  const runSetup = async () => {
    setBusy(true);
    try {
      const result = await freebuffSetup();
      if (result.status === "ready") {
        showMessage(`Freebuff ready -- ${result.token_count ?? 0} token(s), port ${result.port ?? "?"}`, "ok");
      } else {
        showMessage(result.error || "Setup failed", "error");
      }
      await loadFreebuffView();
    } catch (err) {
      showMessage(err instanceof Error ? err.message : "Setup failed", "error");
    } finally {
      setBusy(false);
    }
  };

  const handleDiscoverModels = async () => {
    setBusy(true);
    try {
      const result = await freebuffModels();
      if (status) {
        setStatus({ ...status, models: result.models, model_count: result.models.length });
        showMessage(`Discovered ${result.models.length} model(s)`, "ok");
      }
    } catch (err) {
      showMessage(err instanceof Error ? err.message : "Discovery failed", "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-5">
      <div className="alert alert-warning py-3 px-4 rounded-lg text-sm">
        <Badge kind="warn">Suspension Risk</Badge>
        <span className="ml-1">
          Freebuff2API uses free-tier session credentials which may be suspended by the upstream provider. Use a
          throwaway account.
        </span>
      </div>

      {status.requires_sudo && (
        <div className="alert alert-warning py-3 px-4 rounded-lg text-sm">
          <Badge kind="warn">Sudo Required</Badge>
          <span className="ml-1">
            Docker is not accessible without sudo. Add your user to the docker group:{" "}
            <code className="px-1 py-0.5 rounded bg-base-300 text-xs">sudo usermod -aG docker $USER</code>
          </span>
        </div>
      )}

      <div className="rounded-lg border border-base-300 bg-base-200 p-4 flex items-center gap-3 flex-wrap">
        <Badge kind={status.running ? "ok" : "neutral"}>{status.running ? "Active" : "Stopped"}</Badge>
        <span className="text-sm">
          Freebuff2API{status.method ? ` (${status.method})` : ""}{status.port ? ` on port ${status.port}` : ""}
          {status.health && status.health !== "unknown" ? ` - ${status.health}` : ""}
        </span>
      </div>

      <div className="flex gap-2 flex-wrap">
        <Button variant="secondary" disabled={busy} onClick={runSetup} title="Ensure binary/image, read credentials, generate config">Setup</Button>
        <Button variant="primary" disabled={busy || status.running} onClick={runStart}>Start</Button>
        <Button variant="secondary" disabled={busy || !status.running} onClick={runStop}>Stop</Button>
        <Button variant="secondary" disabled={busy} onClick={runRestart}>Restart</Button>
        <Button variant="secondary" disabled={busy} onClick={loadFreebuffView}>Refresh</Button>
      </div>

      <Section title="Credentials" description="Auth tokens read from the Freebuff CLI credentials file.">
        <StatusGrid>
          <StatusCard
            title="Freebuff CLI Tokens"
            pillKind={status.credentials?.found ? "ok" : "warn"}
            pillText={status.credentials?.found ? `${status.credentials.token_count} token(s)` : "Not found"}
            meta={[
              ...(status.credentials?.profiles?.length ? [status.credentials.profiles.join(", ")] : []),
              ...(status.credentials?.path ? [status.credentials.path] : []),
            ]}
          />
        </StatusGrid>
      </Section>

      <Section title="Deployment" description="Binary or Docker image availability.">
        <StatusGrid>
          <BinaryCard label="Docker" available={!!status.binary?.docker_available} active={status.binary?.method === "docker"} />
          <BinaryCard label="Go Build" available={!!status.binary?.go_available} active={status.binary?.method === "source"} />
          {status.binary?.binary_exists && (
            <StatusCard title="Built Binary" pillKind="ok" pillText="Exists" meta={status.binary.binary_path ? [status.binary.binary_path] : []} />
          )}
          {status.binary?.version && (
            <StatusCard title="Version" pillKind="neutral" pillText={status.binary.version} meta={[]} />
          )}
        </StatusGrid>
      </Section>

      <Section title="Health & Status" description="Live health probe and container status.">
        <StatusGrid>
          <ContainerCard container={status.container} />
          <HealthCard health={health} />
          {health?.token_state && health.token_state.length > 0 && (
            health.token_state.map((tok, i) => <TokenCard key={i} token={tok} />)
          )}
        </StatusGrid>
      </Section>

      <Section title="Models" description={`${status.model_count ?? 0} model(s) available. Discover to refresh the list.`}>
        <div className="mb-3">
          <Button variant="secondary" disabled={busy} onClick={handleDiscoverModels}>Discover Models</Button>
        </div>
        <StatusGrid>
          {(status.models ?? []).map((m, i) => (
            <StatusCard
              key={m.id ?? i}
              title={m.id || m.model || "Model"}
              pillKind="ok"
              pillText="available"
              meta={["Proxied via Freebuff2API"]}
            />
          ))}
        </StatusGrid>
      </Section>

      {config && <FormSections sectionIds={["freebuff"]} sections={config.sections} fields={config.fields} />}
    </div>
  );
}

function Skeleton() {
  return <div className="skeleton h-8 w-full rounded-lg" aria-hidden />;
}

function Section({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-base-300 bg-base-200 p-5 scroll-mt-5">
      <div className="mb-4">
        <h3 className="text-base font-bold">{title}</h3>
        <p className="text-xs text-base-content/60 mt-0.5">{description}</p>
      </div>
      {children}
    </section>
  );
}

function StatusGrid({ children }: { children: React.ReactNode }) {
  return <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(220px,1fr))]">{children}</div>;
}

function StatusCard({
  title,
  pillKind,
  pillText,
  meta,
}: {
  title: string;
  pillKind: "ok" | "warn" | "error" | "neutral";
  pillText: string;
  meta: string[];
}) {
  return (
    <article className="grid gap-2 min-h-[108px] border border-base-300 rounded-lg p-3.5 bg-base-100 hover:border-base-content/30 transition">
      <div className="flex items-center justify-between gap-2">
        <strong className="text-sm">{title}</strong>
        <Badge kind={pillKind}>{pillText}</Badge>
      </div>
      {meta.map((m, i) => (
        <div key={i} className="text-xs text-base-content/60 break-words">{m}</div>
      ))}
    </article>
  );
}

function BinaryCard({ label, available, active }: { label: string; available: boolean; active: boolean }) {
  return (
    <StatusCard
      title={label}
      pillKind={available ? "ok" : "neutral"}
      pillText={available ? "Available" : "Not installed"}
      meta={[active ? "Active method" : "Not the active method"]}
    />
  );
}

function ContainerCard({ container }: { container?: FreebuffContainer }) {
  if (!container) return null;
  const pillKind: "ok" | "warn" | "neutral" = container.running
    ? "ok"
    : container.status === "exited"
      ? "warn"
      : "neutral";
  const pillText = container.running
    ? "Active"
    : container.status === "exited"
      ? "Stopped"
      : container.status === "not_found"
        ? "Not Found"
        : "Unknown";
  const meta: string[] = [];
  if (container.container_id) meta.push(`id: ${container.container_id.slice(0, 12)}`);
  if (container.error) meta.push(container.error);
  return <StatusCard title="Docker Container" pillKind={pillKind} pillText={pillText} meta={meta} />;
}

function HealthCard({ health }: { health: FreebuffHealth | null }) {
  if (!health) return null;
  const pillKind: "ok" | "error" | "neutral" = health.status === "healthy" ? "ok" : health.status === "not_configured" ? "neutral" : "error";
  const meta: string[] = [];
  if (health.uptime_sec != null) meta.push(`uptime: ${health.uptime_sec}s`);
  if (health.error) meta.push(health.error);
  return <StatusCard title="Health Endpoint" pillKind={pillKind} pillText={health.status} meta={meta} />;
}

function TokenCard({ token }: { token: FreebuffTokenState }) {
  const st = (token.status || "").toLowerCase();
  const pillKind: "ok" | "warn" | "neutral" = ["active", "ok", "healthy"].includes(st) ? "ok" : ["rate_limited", "cooldown", "draining"].includes(st) ? "warn" : "neutral";
  const meta: string[] = [];
  if (token.run_count != null) meta.push(`${token.run_count} active run(s)`);
  if (token.inflight_count != null) meta.push(`${token.inflight_count} in-flight`);
  if (token.session_expires_at && token.session_expires_at !== "0001-01-01T00:00:00Z") {
    meta.push(`session expires: ${token.session_expires_at}`);
  }
  return <StatusCard title={token.name || "Token"} pillKind={pillKind} pillText={token.status || "unknown"} meta={meta} />;
}
