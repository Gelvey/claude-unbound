import { api } from "./client";

export interface FreebuffContainer {
  running: boolean;
  status?: string;
  container_id?: string;
  host_port?: number | null;
  error?: string;
  requires_sudo?: boolean;
}

export interface FreebuffCredentials {
  found: boolean;
  token_count: number;
  profiles?: string[];
  path?: string;
}

export interface FreebuffBinary {
  method?: string;
  docker_available: boolean;
  go_available: boolean;
  binary_exists?: boolean;
  binary_path?: string;
  version?: string;
}

export interface FreebuffTokenState {
  name?: string;
  status?: string;
  run_count?: number;
  inflight_count?: number;
  session_expires_at?: string;
}

export interface FreebuffStatus {
  running: boolean;
  method?: string;
  port?: number;
  base_url?: string;
  health?: string;
  requires_sudo?: boolean;
  auth_token_count?: number;
  credentials?: FreebuffCredentials;
  binary?: FreebuffBinary;
  container?: FreebuffContainer;
  models?: { id?: string; model?: string }[];
  model_count?: number;
}

export interface FreebuffHealth {
  status: string;
  uptime_sec?: number;
  http_status?: number;
  error?: string;
  token_state?: FreebuffTokenState[];
}

export function getFreebuffStatus(): Promise<FreebuffStatus> {
  return api("/admin/api/freebuff/status");
}

export function freebuffSetup(): Promise<{ status: string; method?: string; token_count?: number; port?: number; base_url?: string; error?: string }> {
  return api("/admin/api/freebuff/setup", { method: "POST" });
}

export function freebuffStart(): Promise<{ success: boolean; error?: string }> {
  return api("/admin/api/freebuff/start", { method: "POST" });
}

export function freebuffStop(): Promise<{ success: boolean }> {
  return api("/admin/api/freebuff/stop", { method: "POST" });
}

export function freebuffRestart(): Promise<{ success: boolean }> {
  return api("/admin/api/freebuff/restart", { method: "POST" });
}

export function freebuffHealth(): Promise<FreebuffHealth> {
  return api("/admin/api/freebuff/health");
}

export function freebuffModels(): Promise<{ models: { id?: string; model?: string }[] }> {
  return api("/admin/api/freebuff/models");
}
