import { describe, expect, it, vi } from "vitest";
import { apiJson } from "@/lib/api";

describe("apiJson", () => {
  it("sends credentials and returns JSON payloads", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(apiJson<{ ok: boolean }>("/api/v1/health/live")).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/health/live", expect.objectContaining({ credentials: "include" }));
  });
});
