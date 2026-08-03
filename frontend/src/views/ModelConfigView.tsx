import { useAdminStore } from "../store/useAdminStore";
import { FormSections } from "../components/FormSections";

export function ModelConfigView() {
  const { config } = useAdminStore();
  if (!config) return null;
  return (
    <FormSections
      sectionIds={["models", "thinking", "permissions", "web_tools"]}
      sections={config.sections}
      fields={config.fields}
    />
  );
}
