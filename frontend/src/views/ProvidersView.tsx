import { useAdminStore } from "../store/useAdminStore";
import { FormSections } from "../components/FormSections";
import { Badge, statusBadgeClass } from "../components/ui";

const PROVIDER_NAMES: Record<string, string> = {
  nvidia_nim: "NVIDIA NIM",
  open_router: "OpenRouter",
  mistral_codestral: "Mistral Codestral",
  deepseek: "DeepSeek",
  lmstudio: "LM Studio",
  llamacpp: "llama.cpp",
  ollama: "Ollama",
  kimi: "Kimi",
  wafer: "Wafer",
  opencode: "OpenCode Zen",
  opencode_go: "OpenCode Go",
  zai: "Z.ai",
  freebuff: "Freebuff",
};

function providerName(id: string): string {
  if (PROVIDER_NAMES[id]) return PROVIDER_NAMES[id];
  return id
    .split("_")
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(" ");
}

export function ProvidersView() {
  const { config, providerStatus, localStatus, testProvider, lastChecked } =
    useAdminStore();
  if (!config) return null;

  return (
    <div className="grid gap-5">
      <section
        className="rounded-xl border border-base-300 bg-base-200 p-5"
        aria-label="Provider status"
      >
        <div className="mb-4">
          <h3 className="text-base font-bold">Providers</h3>
        </div>
        <div className="grid [grid-template-columns:repeat(auto-fit,minmax(220px,1fr))] gap-3">
          {providerStatus.length === 0 && (
            <div className="flex flex-col items-center justify-center min-h-[80px] p-6 border border-dashed border-base-300 rounded-lg text-base-content/60 text-sm text-center">
              No providers configured. Configure API keys below to see provider
              status.
            </div>
          )}
          {providerStatus.map((provider) => {
            const local = localStatus.get(provider.provider_id);
            const status = local?.status || provider.status;
            const label = local?.label || provider.label;
            const meta = local
              ? local.status_code
                ? `${local.base_url} returned HTTP ${local.status_code}`
                : local.base_url
              : provider.kind === "local"
                ? provider.base_url || "No local URL configured"
                : provider.credential_env;
            return (
              <article
                key={provider.provider_id}
                className="grid gap-2 min-h-[108px] border border-base-300 rounded-lg p-3.5 bg-base-100 hover:border-base-content/30 transition"
              >
                <div className="flex items-center justify-between gap-2">
                  <strong className="text-sm">{providerName(provider.provider_id)}</strong>
                  <Badge kind={statusBadgeClass(status)}>{label}</Badge>
                </div>
                <div className="text-xs text-base-content/60 break-words">{meta}</div>
                {lastChecked && local && (
                  <div className="text-[11px] text-base-content/50 opacity-70">
                    Checked: {lastChecked.toLocaleTimeString()}
                  </div>
                )}
                <button
                  type="button"
                  className="btn btn-xs btn-neutral rounded-lg self-start"
                  onClick={() => void testProvider(provider.provider_id)}
                >
                  {provider.kind === "local" ? "Test" : "Refresh models"}
                </button>
              </article>
            );
          })}
        </div>
      </section>
      <FormSections
        sectionIds={["providers", "runtime"]}
        sections={config.sections}
        fields={config.fields}
      />
    </div>
  );
}
