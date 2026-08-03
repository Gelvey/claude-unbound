import { useState } from "react";
import type { ConfigField, ConfigSection } from "../types";
import { Field } from "./Field";

// sectionHeading + settings-section rendering. Advanced fields are hidden
// behind a "Show advanced" toggle, exactly like renderSections in admin.js.
export function FormSections({
  sectionIds,
  sections,
  fields,
}: {
  sectionIds: string[];
  sections: ConfigSection[];
  fields: ConfigField[];
}) {
  const sectionById = new Map(sections.map((s) => [s.id, s]));
  const bySection = new Map<string, ConfigField[]>();
  for (const field of fields) {
    if (!bySection.has(field.section)) bySection.set(field.section, []);
    bySection.get(field.section)!.push(field);
  }

  return (
    <div className="grid gap-5">
      {sectionIds.map((sectionId) => {
        const section = sectionById.get(sectionId);
        const sectionFields = bySection.get(sectionId) || [];
        if (!section || sectionFields.length === 0) return null;
        const hasAdvanced = sectionFields.some((f) => f.advanced);
        return (
          <Section
            key={sectionId}
            section={section}
            fields={sectionFields}
            hasAdvanced={hasAdvanced}
          />
        );
      })}
    </div>
  );
}

function Section({
  section,
  fields,
  hasAdvanced,
}: {
  section: ConfigSection;
  fields: ConfigField[];
  hasAdvanced: boolean;
}) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  return (
    <section className="rounded-xl border border-base-300 bg-base-200 p-5 scroll-mt-5">
      <div className="flex items-center justify-between gap-3 mb-4">
        <div>
          <h3 className="text-base font-bold">{section.label}</h3>
          {section.description && (
            <p className="text-xs text-base-content/60 mt-0.5">{section.description}</p>
          )}
        </div>
      </div>
      <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(260px,1fr))]">
        {fields.map((field) =>
          field.advanced && !showAdvanced ? null : <Field key={field.key} field={field} />,
        )}
      </div>
      {hasAdvanced && (
        <button
          type="button"
          className="btn btn-sm btn-ghost rounded-lg mt-3"
          onClick={() => setShowAdvanced((v) => !v)}
        >
          {showAdvanced ? "Hide advanced" : "Show advanced"}
        </button>
      )}
    </section>
  );
}
