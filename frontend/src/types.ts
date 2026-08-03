// Shared types mirroring the backend admin API contract.

export type FieldType =
  | "text"
  | "secret"
  | "number"
  | "boolean"
  | "tri_boolean"
  | "select"
  | "textarea";

export type SourceType =
  | "default"
  | "template"
  | "repo_env"
  | "managed_env"
  | "explicit_env_file"
  | "process"
  | "settings_json";

export interface ConfigField {
  key: string;
  label: string;
  section: string;
  type: FieldType;
  value: string;
  configured: boolean;
  source: SourceType;
  locked: boolean;
  secret: boolean;
  advanced: boolean;
  restart_required: boolean;
  session_sensitive: boolean;
  options: string[];
  model_options: boolean;
  description: string;
}

export interface ConfigSection {
  id: string;
  label: string;
  description: string;
  advanced: boolean;
}

export interface ConfigPaths {
  managed: string;
  repo: string;
  explicit: string | null;
}

export interface ProviderStatusEntry {
  provider_id: string;
  kind: "local" | "remote";
  status: string;
  label: string;
  base_url?: string;
  credential_env?: string;
  missing_envs?: string[];
}

export interface ConfigResponse {
  sections: ConfigSection[];
  fields: ConfigField[];
  paths: ConfigPaths;
  provider_status: ProviderStatusEntry[];
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
}

export interface ApplyResult {
  applied: boolean;
  errors?: string[];
  pending_fields?: string[];
  restart?: {
    required: boolean;
    automatic: boolean;
    admin_url: string | null;
    fields: string[];
  };
}

export interface LocalProviderCheck {
  provider_id: string;
  status: string;
  label: string;
  base_url: string;
  status_code?: number;
  error_type?: string;
}

export interface ProviderTestResult {
  provider_id: string;
  ok: boolean;
  models?: string[];
  error_type?: string;
  status_code?: number;
  error_message?: string;
  request_url?: string;
}

export interface ModuleTab {
  id: string;
  label: string;
  title: string;
  html: string;
  mount_js: string | null;
}

export const MASKED_SECRET = "********";

export const RESTART_MODAL_KEYS = new Set([
  "CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS",
  "CODEX_DANGEROUSLY_BYPASS_APPROVALS",
]);
