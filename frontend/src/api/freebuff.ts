import { api } from "./client";

export interface FreebuffStatus {
  running: boolean;
  method?: string;
  port?: number;
  health?: string;
  requires_sudo?: boolean;
  credentials?: {
    found: boolean;
    token_count: number;
    profiles?: string[];
    path?: string;
  };
  binary?: {
    docker_available: boolean;
    go_available: boolean;
    method?: string;
    binary_exists?: boolean;
    binary_path?: string;
    version?: string;
  };
  container?: {
    running: boolean;
    status?: string;
    container_id?: string;
    error?: string;
  };
  models?: { id?: string; model?: string }[];
  model_count?: number;
}

export function getFreebuffStatus(): Promise<FreebuffStatus> {
  return api("/admin/api/freebuff/status");
}

export function freebuffSetup(): Promise<{ status: string; token_count?: number; port?: number; error?: string }> {
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

export function freebuffHealth(): Promise<{ status: string; uptime_sec?: number; error?: string; token_state?: unknown[] }> {
  return api("/admin/api/freebuff/health");
}

export function freebuffModels(): Promise<{ models: { id?: string; model?: string }[] }> {
  return api("/admin/api/freebuff/models");
}
