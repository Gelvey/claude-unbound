import { api } from "./client";

export interface GraphifyProject {
  path: string;
  name?: string;
  status: string;
  last_indexed: string | null;
  error_message?: string;
}

export interface GraphifyStatus {
  running: boolean;
  port?: number;
  python?: string;
  last_error?: string;
  projects_count?: number;
  mcp_registered?: boolean;
  llm_backend?: string;
  llm_model?: string;
  code_only?: boolean;
  index_queue_length?: number;
  index_queue?: { path: string; status: string }[];
}

export function graphifyStatus(): Promise<GraphifyStatus> {
  return api("/admin/api/graphify/status");
}

export function graphifyHealth(): Promise<{ status: string; error?: string }> {
  return api("/admin/api/graphify/health");
}

export function graphifyProjects(): Promise<{ active_project_path: string | null; projects: GraphifyProject[] }> {
  return api("/admin/api/graphify/projects");
}

export function graphifySetup(): Promise<{ ready: boolean; method?: string; python?: string; error?: string }> {
  return api("/admin/api/graphify/setup", { method: "POST" });
}

export function graphifyStart(): Promise<{ success: boolean; error?: string }> {
  return api("/admin/api/graphify/start", { method: "POST" });
}

export function graphifyStop(): Promise<{ success: boolean }> {
  return api("/admin/api/graphify/stop", { method: "POST" });
}

export function graphifyRestart(): Promise<{ success: boolean }> {
  return api("/admin/api/graphify/restart", { method: "POST" });
}

export function graphifyAddProject(path: string): Promise<{ success: boolean }> {
  return api("/admin/api/graphify/projects", {
    method: "POST",
    body: JSON.stringify({ path }),
  });
}

export function graphifyRemoveProject(pathB64: string): Promise<{ success: boolean }> {
  return api(`/admin/api/graphify/projects/${pathB64}`, { method: "DELETE" });
}

export function graphifyIndex(pathB64: string): Promise<{ success: boolean; status?: string; error?: string }> {
  return api(`/admin/api/graphify/projects/${pathB64}/index`, {
    method: "POST",
    body: "{}",
  });
}

export function graphifyIndexStatus(pathB64: string): Promise<{ status: string; queue_position?: number; error_message?: string }> {
  return api(`/admin/api/graphify/projects/${pathB64}/index/status`);
}

export function graphifyGraph(pathB64: string): Promise<{ present: boolean; node_count?: number; link_count?: number; hyperedge_count?: number; built_at_commit?: string; reason?: string }> {
  return api(`/admin/api/graphify/projects/${pathB64}/graph`);
}

// URL-safe base64 path encoding (mirrors graphifyPathB64 in admin.js).
export function graphifyPathB64(path: string): string {
  const bytes = new TextEncoder().encode(path);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
