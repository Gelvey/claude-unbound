import { api } from "./client";

export interface OpenRouterProvider {
  slug: string;
  name: string;
}

export interface OpenRouterForcedSnapshot {
  forced_provider: string | null;
  allow_fallbacks: boolean;
  configured: boolean;
}

export function getForcedProvider(): Promise<OpenRouterForcedSnapshot> {
  return api("/admin/api/openrouter/forced-provider");
}

export function setForcedProvider(
  provider: string | null,
  allow_fallbacks = false,
): Promise<OpenRouterForcedSnapshot> {
  return api("/admin/api/openrouter/forced-provider", {
    method: "POST",
    body: JSON.stringify({ provider, allow_fallbacks }),
  });
}

export function listProviders(): Promise<{ providers: OpenRouterProvider[] }> {
  return api("/admin/api/openrouter/providers");
}
