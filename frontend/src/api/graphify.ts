import { api } from "./client";

export interface GraphifyProject {
  path: string;
  name?: string;
  graphify_out?: string;
  status: string;
  last_indexed: string | null;
  error_message?: string;
}

export interface GraphifyProjectSummary {
  path: string;
  name: string;
  status: string;
  last_indexed: string | null;
}

export interface GraphifyStatus {
  enabled?: boolean;
  running: boolean;
  port?: number;
  base_url?: string;
  python?: string;
  last_error?: string;
  projects_count?: number;
  projects_summary?: GraphifyProjectSummary[];
  mcp_registered?: boolean;
  owns_process?: boolean;
  adopted?: boolean;
  llm_backend?: string;
  llm_model?: string;
  code_only?: boolean;
  index_queue_length?: number;
  index_queue?: { path: string; status: string }[];
}

export interface GraphifyGraph {
  present: boolean;
  node_count?: number;
  link_count?: number;
  hyperedge_count?: number;
  built_at_commit?: string;
  file_types?: Record<string, number>;
  communities?: number;
  reason?: string;
  error?: string;
}

export interface GraphifyIndexStatus {
  status: string;
  last_indexed?: string | null;
  error_message?: string;
  queue_position?: number;
  task?: { path: string; status: string; result?: unknown; error_message?: string };
  current_indexing?: string;
}

export function graphifyStatus(): Promise<GraphifyStatus> {
  return api("/admin/api/graphify/status");
}

export interface GraphifyHealth {
  status: string;
  http_status?: number;
  error?: string;
  server_info?: Record<string, unknown>;
  data?: Record<string, unknown>;
}

export function graphifyHealth(): Promise<GraphifyHealth> {
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

export function graphifyIndexStatus(pathB64: string): Promise<GraphifyIndexStatus> {
  return api(`/admin/api/graphify/projects/${pathB64}/index/status`);
}

export function graphifyGraph(pathB64: string): Promise<GraphifyGraph> {
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
