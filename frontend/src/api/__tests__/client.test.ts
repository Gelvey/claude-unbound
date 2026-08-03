import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { api } from "../client";

describe("api client", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    globalThis.fetch = fetchMock as unknown as typeof fetch;
  });
  afterEach(() => {
    fetchMock.mockReset();
  });

  it("sends a JSON request and returns the parsed body", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ hello: "world" }),
    });

    const result = await api<{ hello: string }>("/admin/api/config");

    expect(fetchMock).toHaveBeenCalledWith(
      "/admin/api/config",
      expect.objectContaining({ headers: expect.objectContaining({ "Content-Type": "application/json" }) }),
    );
    expect(result).toEqual({ hello: "world" });
  });

  it("preserves caller headers and adds Content-Type when missing", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({}),
    });

    await api("/x", { headers: { Authorization: "Bearer t" } });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer t");
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });

  it("throws on a non-2xx response with status + statusText", async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 403, statusText: "Forbidden" });

    await expect(api("/admin/api/secret")).rejects.toThrow("403 Forbidden");
  });
});
