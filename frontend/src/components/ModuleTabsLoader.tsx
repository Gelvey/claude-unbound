import { useEffect, useRef } from "react";
import type { ModuleTab } from "../types";

// Renders an active module tab: injects tab.html into a container ref and
// runs tab.mount_js(container) after mount. Mirrors injectModuleTab in admin.js.
export function ModuleTabView({ tab }: { tab: ModuleTab }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !tab.mount_js) return;
    try {
      // eslint-disable-next-line no-new-func
      const mount = new Function("container", tab.mount_js) as (c: HTMLDivElement) => void;
      mount(container);
    } catch (err) {
      console.error(`Module tab '${tab.id}' mount_js failed:`, err);
    }
  }, [tab.id, tab.mount_js]);

  return (
    <div
      ref={containerRef}
      dangerouslySetInnerHTML={{ __html: tab.html || "" }}
    />
  );
}
