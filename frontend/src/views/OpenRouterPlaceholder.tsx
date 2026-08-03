import { useAdminStore } from "../store/useAdminStore";
import { FormSections } from "../components/FormSections";

// Phase 1: OpenRouter policy config fields + placeholder for the
// forced-provider search/apply widget (Phase 2).
export function OpenRouterPlaceholder() {
  const { config } = useAdminStore();
  if (!config) return null;
  return (
    <div className="grid gap-5">
      <div className="alert alert-warning py-3 px-4 rounded-lg text-sm">
        The OpenRouter forced-provider search widget is part of Phase 2 (not
        yet implemented). Policy fields below apply via the global Apply
        button.
      </div>
      <FormSections
        sectionIds={["openrouter_policy"]}
        sections={config.sections}
        fields={config.fields}
      />
    </div>
  );
}
