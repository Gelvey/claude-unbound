// Thin fetch wrapper used by every API client module. Mirrors the original
// admin.js `api()` helper: JSON in, JSON out, throw on non-2xx.

export async function api<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) || {}),
  };
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}
