import { api } from "./client";
import type { LocalProviderCheck, ProviderTestResult } from "../types";

export function getLocalStatus(): Promise<{ providers: LocalProviderCheck[] }> {
  return api("/admin/api/providers/local-status");
}

export function testProvider(
  providerId: string,
): Promise<ProviderTestResult> {
  return api<ProviderTestResult>(
    `/admin/api/providers/${providerId}/test`,
    { method: "POST", body: "{}" },
  );
}
