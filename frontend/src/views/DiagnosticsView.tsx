import { useAdminStore } from "../store/useAdminStore";
import { FormSections } from "../components/FormSections";

export function DiagnosticsView() {
  const { config } = useAdminStore();
  if (!config) return null;
  return (
    <FormSections
      sectionIds={["diagnostics", "smoke"]}
      sections={config.sections}
      fields={config.fields}
    />
  );
}
