import { useAdminStore } from "../store/useAdminStore";
import { FormSections } from "../components/FormSections";

export function MessagingView() {
  const { config } = useAdminStore();
  if (!config) return null;
  return (
    <FormSections
      sectionIds={["messaging", "voice"]}
      sections={config.sections}
      fields={config.fields}
    />
  );
}
