import { useAdminStore } from "../store/useAdminStore";
import { FormSections } from "../components/FormSections";

// Phase 1: MCP config sections (mcp_shared) + placeholder for the bespoke
// backend-grid/edit-form/SFTP/Composio widgets (Phase 2).
export function McpPlaceholder() {
  const { config } = useAdminStore();
  if (!config) return null;
  return (
    <div className="grid gap-5">
      <div className="alert alert-warning py-3 px-4 rounded-lg text-sm">
        The MCP Router backend grid, edit form, SFTP, and Composio widgets are
        part of Phase 2 (not yet implemented). SFTP fields below are still
        editable and apply via the global Apply button.
      </div>
      <FormSections
        sectionIds={["mcp_shared"]}
        sections={config.sections}
        fields={config.fields}
      />
    </div>
  );
}
