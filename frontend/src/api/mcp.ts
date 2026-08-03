import { api } from "./client";

// MCP config shape (servers/shared_servers map). Kept loose here; the
// Phase 2 edit form narrows it with a discriminated union on `type`.
export type McpBackendType = "stdio" | "sse" | "http";

export interface McpBackendEntry {
  type: McpBackendType;
  port: number;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  url?: string;
  headers?: Record<string, string>;
}

export interface McpConfig {
  router_socket: string;
  router_pidfile: string;
  router_log: string;
  health_timeout_s: number;
  servers: Record<string, McpBackendEntry>;
  shared_servers: Record<string, McpBackendEntry>;
}

export interface McpStatusBackend {
  name: string;
  activated: boolean;
  tool_count: number;
  tool_names?: string[];
}

export interface McpStatus {
  running: boolean;
  backends?: McpStatusBackend[];
}

export interface SftpConfig {
  host: string;
  port: number;
  username: string;
  auth_method: string;
  password: string;
  private_key: string;
  remote_file_path: string;
  enabled: boolean;
}

export function getMcpConfig(): Promise<McpConfig> {
  return api("/admin/api/mcp/config");
}

export function applyMcpConfig(config: McpConfig): Promise<{ applied: boolean; errors?: string[]; restart_hint?: string }> {
  return api("/admin/api/mcp/config/apply", {
    method: "POST",
    body: JSON.stringify(config),
  });
}

export function getMcpStatus(): Promise<McpStatus> {
  return api("/admin/api/mcp/status");
}

export function getSftpConfig(): Promise<{ sftp: SftpConfig }> {
  return api("/admin/api/mcp/sftp-config");
}

export function validateSftpConfig(values: SftpConfig): Promise<{ valid: boolean; errors: string[] }> {
  return api("/admin/api/mcp/sftp-config/validate", {
    method: "POST",
    body: JSON.stringify(values),
  });
}

export function applySftpConfig(values: SftpConfig): Promise<{ applied: boolean; errors?: string[] }> {
  return api("/admin/api/mcp/sftp-config/apply", {
    method: "POST",
    body: JSON.stringify(values),
  });
}

export function sftpFetch(): Promise<{ ok: boolean; error?: string; config?: { servers: Record<string, McpBackendEntry> } }> {
  return api("/admin/api/mcp/sftp-fetch", { method: "POST" });
}

export function sftpImport(mode: "merge" | "replace"): Promise<{ ok: boolean; error?: string; imported_count?: number }> {
  return api("/admin/api/mcp/sftp-import", {
    method: "POST",
    body: JSON.stringify({ mode }),
  });
}

export function composioSetup(api_key: string, port?: number): Promise<{ applied: boolean; errors?: string[] }> {
  return api("/admin/api/mcp/composio/setup", {
    method: "POST",
    body: JSON.stringify({ api_key, ...(port ? { port } : {}) }),
  });
}

export function composioTest(api_key?: string): Promise<{ ok: boolean; error?: string; tool_count?: number; tool_names?: string[] }> {
  return api("/admin/api/mcp/composio/test", {
    method: "POST",
    body: JSON.stringify(api_key ? { api_key } : {}),
  });
}
