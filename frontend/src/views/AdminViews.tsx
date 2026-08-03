import { useAdminStore } from "../store/useAdminStore";
import { ProvidersView } from "./ProvidersView";
import { ModelConfigView } from "./ModelConfigView";
import { MessagingView } from "./MessagingView";
import { CloudflareView } from "./CloudflareView";
import { DiagnosticsView } from "./DiagnosticsView";
import { McpView } from "./McpView";
import { FreebuffView } from "./FreebuffView";
import { GraphifyView } from "./GraphifyView";
import { OpenRouterView } from "./OpenRouterView";

export function AdminViews() {
  const { activeView, config } = useAdminStore();
  if (!config) return null;

  switch (activeView) {
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
