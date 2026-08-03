import { useAdminStore } from "../store/useAdminStore";
import { FormSections } from "../components/FormSections";

// Phase 1: Freebuff config fields + placeholder for the lifecycle/health
// widgets (Phase 2).
export function FreebuffPlaceholder() {
  const { config } = useAdminStore();
  if (!config) return null;
  return (
    <div className="grid gap-5">
      <div className="alert alert-warning py-3 px-4 rounded-lg text-sm">
        The Freebuff2API lifecycle, health, and model-discovery widgets are
        part of Phase 2 (not yet implemented).
      </div>
      <FormSections
        sectionIds={["freebuff"]}
        sections={config.sections}
        fields={config.fields}
      />
    </div>
  );
}
