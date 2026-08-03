import { api } from "./client";
import type {
  ApplyResult,
  ConfigResponse,
  ValidationResult,
} from "../types";

export function getConfig(): Promise<ConfigResponse> {
  return api<ConfigResponse>("/admin/api/config");
}

export function validateValues(values: Record<string, string>): Promise<ValidationResult> {
  return api<ValidationResult>("/admin/api/config/validate", {
    method: "POST",
    body: JSON.stringify({ values }),
  });
}

export function applyConfig(
  values: Record<string, string>,
): Promise<ApplyResult> {
  return api<ApplyResult>("/admin/api/config/apply", {
    method: "POST",
    body: JSON.stringify({ values }),
  });
}
