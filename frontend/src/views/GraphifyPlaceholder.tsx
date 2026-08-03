import { useAdminStore } from "../store/useAdminStore";
import { FormSections } from "../components/FormSections";

// Phase 1: Graphify config fields + placeholder for the project/index/poll
// widgets (Phase 2).
export function GraphifyPlaceholder() {
  const { config } = useAdminStore();
  if (!config) return null;
  return (
    <div className="grid gap-5">
      <div className="alert alert-warning py-3 px-4 rounded-lg text-sm">
        The Graphify project CRUD, index, and auto-refresh widgets are part of
        Phase 2 (not yet implemented).
      </div>
      <FormSections
        sectionIds={["graphify"]}
        sections={config.sections}
        fields={config.fields}
      />
    </div>
  );
}
