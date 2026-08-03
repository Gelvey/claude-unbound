import { useAdminStore } from "../store/useAdminStore";
import { FormSections } from "../components/FormSections";

export function CloudflareView() {
  const { config } = useAdminStore();
  if (!config) return null;
  // Cloudflare section uses a single-column layout in the original admin.css
  // (long field labels); FormSections already wraps each section, so we just
  // reuse the default grid here. The cloudflare section id is rendered alone.
  return (
    <FormSections
      sectionIds={["cloudflare"]}
      sections={config.sections}
      fields={config.fields}
    />
  );
}
