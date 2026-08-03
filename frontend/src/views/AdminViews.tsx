import { useAdminStore } from "../store/useAdminStore";
import { Skeleton } from "../components/ui";
import { ViewErrorBoundary } from "../components/ViewErrorBoundary";
import { ProvidersView } from "./ProvidersView";
import { ModelConfigView } from "./ModelConfigView";
import { MessagingView } from "./MessagingView";
import { CloudflareView } from "./CloudflareView";
import { DiagnosticsView } from "./DiagnosticsView";
import { McpView } from "./McpView";
import { FreebuffView } from "./FreebuffView";
import { GraphifyView } from "./GraphifyView";
import { OpenRouterView } from "./OpenRouterView";

function ViewSkeleton() {
  return (
    <div className="grid gap-5">
      {[0, 1].map((i) => (
        <section
          key={i}
          className="rounded-xl border border-base-300 bg-base-200 p-5"
        >
          <Skeleton className="h-5 w-40 mb-4" />
          <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(260px,1fr))]">
            {Array.from({ length: 4 }).map((_, j) => (
              <Skeleton key={j} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function ViewEmpty({ viewId }: { viewId: string }) {
  return (
    <div className="alert rounded-lg">
      <span className="text-sm text-base-content/70">
        Nothing to configure for this view ({viewId}).
      </span>
    </div>
  );
}

function renderView(viewId: string): React.ReactNode {
  switch (viewId) {
    case "providers":
      return <ProvidersView />;
    case "model_config":
      return <ModelConfigView />;
    case "messaging":
      return <MessagingView />;
    case "cloudflare":
      return <CloudflareView />;
    case "diagnostics":
      return <DiagnosticsView />;
    case "mcp":
      return <McpView />;
    case "freebuff":
      return <FreebuffView />;
    case "graphify":
      return <GraphifyView />;
    case "openrouter_policy":
      return <OpenRouterView />;
    default:
      // Module tabs are rendered by the shell, not here.
      return null;
  }
}

export function AdminViews() {
  const { activeView, config, loading } = useAdminStore();
  if (loading && !config) return <ViewSkeleton />;
  if (!config) return <ViewEmpty viewId={activeView} />;
  const rendered = renderView(activeView);
  if (rendered === null) return null;
  return (
    <ViewErrorBoundary key={activeView} viewId={activeView}>
      {rendered}
    </ViewErrorBoundary>
  );
}
