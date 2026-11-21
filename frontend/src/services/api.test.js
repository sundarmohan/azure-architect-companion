import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createArchitecture,
  getCurrentUser,
  listArchitectures,
  login,
  onUnauthorized,
  setApiSession,
} from "./api";

function ok(data) {
  return { ok: true, status: 200, json: async () => data };
}

afterEach(() => {
  setApiSession();
  onUnauthorized(undefined);
  vi.unstubAllGlobals();
});

describe("session-aware requests", () => {
  it("sends cookies, adds the write header, and scopes only client requests", async () => {
    const fetch = vi.fn().mockResolvedValue(ok({}));
    vi.stubGlobal("fetch", fetch);
    setApiSession("client-a");
    await login("operator", "sample-password");
    await getCurrentUser();
    await createArchitecture({ name: "Design" });

    const [[loginUrl, loginOptions], [meUrl, meOptions], [designUrl, designOptions]] = fetch.mock.calls;
    expect(loginUrl).toMatch(/\/auth\/login$/);
    expect(loginOptions.credentials).toBe("include");
    expect(loginOptions.headers.get("X-MonitorAI-Request")).toBe("1");
    expect(loginOptions.headers.has("X-Client-ID")).toBe(false);
    expect(meUrl).toMatch(/\/auth\/me$/);
    expect(meOptions.cache).toBe("no-store");
    expect(designUrl).toMatch(/\/architectures$/);
    expect(designOptions.credentials).toBe("include");
    expect(designOptions.headers.get("X-Client-ID")).toBe("client-a");
    expect(designOptions.headers.get("X-MonitorAI-Request")).toBe("1");
  });

  it("rejects an old client's in-flight response after switching clients", async () => {
    let finishOld;
    const oldResponse = new Promise((resolve) => { finishOld = resolve; });
    vi.stubGlobal("fetch", vi.fn()
      .mockReturnValueOnce(oldResponse)
      .mockResolvedValueOnce(ok([{ id: "design-b" }])));

    setApiSession("client-a");
    const oldRequest = listArchitectures();
    setApiSession("client-b");
    await expect(listArchitectures()).resolves.toEqual([{ id: "design-b" }]);
    finishOld(ok([{ id: "design-a" }]));
    await expect(oldRequest).rejects.toMatchObject({ name: "AbortError" });
  });

  it("reports an expired session on a scoped request but keeps login errors on the form", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      text: async () => JSON.stringify({ detail: "Sign in required" }),
    }));
    const expired = vi.fn();
    onUnauthorized(expired);
    await expect(login("operator", "wrong-password")).rejects.toMatchObject({ status: 401 });
    expect(expired).not.toHaveBeenCalled();

    setApiSession("client-a");
    await expect(listArchitectures()).rejects.toMatchObject({ status: 401 });
    expect(expired).toHaveBeenCalledTimes(1);
  });
});
