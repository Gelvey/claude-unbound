import { useAdminStore } from "../store/useAdminStore";
import { ProvidersView } from "./ProvidersView";
import { ModelConfigView } from "./ModelConfigView";
import { MessagingView } from "./MessagingView";
import { CloudflareView } from "./CloudflareView";
import { DiagnosticsView } from "./DiagnosticsView";
import { McpPlaceholder } from "./McpPlaceholder";
import { FreebuffPlaceholder } from "./FreebuffPlaceholder";
import { GraphifyPlaceholder } from "./GraphifyPlaceholder";
import { OpenRouterPlaceholder } from "./OpenRouterPlaceholder";

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
      return <McpPlaceholder />;
    case "freebuff":
      return <FreebuffPlaceholder />;
    case "graphify":
      return <GraphifyPlaceholder />;
    case "openrouter_policy":
      return <OpenRouterPlaceholder />;
    default:
      // Module tabs are rendered by the shell, not here.
      return null;
  }
}
