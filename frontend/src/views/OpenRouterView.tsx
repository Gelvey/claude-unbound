import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getForcedProvider,
  listProviders,
  setForcedProvider,
  type OpenRouterProvider,
} from "../api/openrouter";
import { useAdminStore } from "../store/useAdminStore";
import { Badge, Button } from "../components/ui";
import { FormSections } from "../components/FormSections";

export function OpenRouterView() {
  const { config, showMessage, registerViewActivation } = useAdminStore();
  const [providers, setProviders] = useState<OpenRouterProvider[]>([]);
  const [forced, setForced] = useState<string | null>(null);
  const [configured, setConfigured] = useState(false);
  const [allowFallbacks, setAllowFallbacks] = useState(false);
  const [search, setSearch] = useState("");
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [showDropdown, setShowDropdown] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const blurTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadOpenRouterView = useCallback(async () => {
    setLoading(true);
    try {
      const [snap, list] = await Promise.all([
        getForcedProvider(),
        listProviders().catch(() => ({ providers: [] as OpenRouterProvider[] })),
      ]);
      setForced(snap.forced_provider);
      setConfigured(snap.configured);
      setAllowFallbacks(snap.allow_fallbacks);
      setProviders(list.providers);
    } catch {
      // Non-fatal; the policy fields below still work via global Apply.
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadOpenRouterView();
    return registerViewActivation((viewId) => {
      if (viewId === "openrouter_policy") void loadOpenRouterView();
    });
  }, [registerViewActivation, loadOpenRouterView]);

  useEffect(() => () => {
    if (blurTimer.current) clearTimeout(blurTimer.current);
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return providers.slice(0, 50);
    return providers
      .filter((p) => p.name.toLowerCase().includes(q) || p.slug.toLowerCase().includes(q))
      .slice(0, 50);
  }, [providers, search]);

  const handleApply = async () => {
    const slug = selectedSlug || search.trim();
    if (!slug) {
      showMessage("Enter a provider slug first", "error");
      return;
    }
    setBusy(true);
    try {
      const result = await setForcedProvider(slug, allowFallbacks);
      setForced(result.forced_provider);
      setAllowFallbacks(result.allow_fallbacks);
      showMessage(`OpenRouter provider pinned to "${result.forced_provider}"`, "ok");
    } catch (err) {
      showMessage(err instanceof Error ? err.message : "Apply failed", "error");
    } finally {
      setBusy(false);
    }
  };

  const handleClear = async () => {
    setBusy(true);
    try {
      const result = await setForcedProvider(null, false);
      setForced(result.forced_provider);
      setAllowFallbacks(result.allow_fallbacks);
      setSelectedSlug(null);
      setSearch("");
      setAllowFallbacks(false);
      showMessage("OpenRouter forced provider cleared", "ok");
    } catch (err) {
      showMessage(err instanceof Error ? err.message : "Clear failed", "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-5">
      <section className="rounded-xl border border-base-300 bg-base-200 p-5 scroll-mt-5">
        <div className="mb-4">
          <h3 className="text-base font-bold">Forced Provider (session only)</h3>
          <p className="text-xs text-base-content/60 mt-0.5">
            Pin all OpenRouter requests to a single provider for this session. This override lives in server memory
            only and is lost on restart.
          </p>
        </div>

        <div className="mb-3">
          {!configured ? (
            <div className="flex items-center gap-2">
              <Badge kind="warn">OpenRouter API key not configured</Badge>
            </div>
          ) : forced ? (
            <div className="flex items-center gap-2 flex-wrap">
              <Badge kind="ok">Pinned: {forced}</Badge>
              {allowFallbacks && (
                <span className="text-xs text-base-content/60">
                  Fallback allowed — other providers may serve the request.
                </span>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Badge kind="neutral">No provider pinned (OpenRouter default routing)</Badge>
            </div>
          )}
        </div>

        <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(260px,1fr))]">
          <label className="grid gap-1.5">
            <span className="text-xs font-semibold text-base-content/70">Provider</span>
            <input
              type="text"
              className="input input-sm w-full"
              placeholder="Type to search providers (e.g. anthropic, deepinfra/turbo)"
              autoComplete="off"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setSelectedSlug(null);
                setShowDropdown(true);
              }}
              onFocus={() => setShowDropdown(true)}
              onBlur={() => {
                blurTimer.current = setTimeout(() => setShowDropdown(false), 150);
              }}
            />
            {showDropdown && filtered.length > 0 && (
              <div className="relative">
                <ul className="absolute z-[100] left-0 right-0 max-h-60 overflow-y-auto rounded-lg border border-base-300 bg-base-100 shadow-lg">
                  {filtered.map((p) => (
                    <li
                      key={p.slug}
                      className="px-3 py-2 text-sm cursor-pointer hover:bg-base-200 flex items-center justify-between gap-2"
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => {
                        setSelectedSlug(p.slug);
                        setSearch(`${p.name} (${p.slug})`);
                        setShowDropdown(false);
                      }}
                    >
                      <strong className="text-xs">{p.name}</strong>
                      <span className="text-xs text-base-content/60">{p.slug}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </label>

          <label className="grid gap-1.5">
            <span className="text-xs font-semibold text-base-content/70">Allow Fallbacks</span>
            <div className="flex items-center gap-2 h-[34px]">
              <input
                type="checkbox"
                className="checkbox checkbox-sm"
                checked={allowFallbacks}
                onChange={(e) => setAllowFallbacks(e.target.checked)}
              />
              <span className="text-xs text-base-content/60">
                Off = pin strictly. On = let OpenRouter fall through to other providers.
              </span>
            </div>
          </label>
        </div>

        <div className="flex gap-2 mt-4">
          <Button variant="primary" disabled={busy || (!selectedSlug && !search.trim())} onClick={handleApply}>
            {busy ? "Working..." : "Apply Forced Provider"}
          </Button>
          <Button variant="secondary" disabled={busy} onClick={handleClear}>Clear</Button>
        </div>
        {loading && <div className="text-xs text-base-content/50 mt-2">Loading provider catalog...</div>}
      </section>

      {config && <FormSections sectionIds={["openrouter_policy"]} sections={config.sections} fields={config.fields} />}
    </div>
  );
}
