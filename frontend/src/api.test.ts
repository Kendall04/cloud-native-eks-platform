import { describe, it, expect, vi } from "vitest";
import { createHttpApi, ApiError, readConfig } from "./api";
import { createDemoApi, demoProfile } from "./demo";
import { createSchema } from "./contracts";
const response = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
describe("HTTP client", () => {
  it.each([400, 401, 403, 404, 409, 429, 500, 502, 503])(
    "rejects HTTP %i without reporting success",
    async (status) => {
      const unauthorized = vi.fn();
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({}, status)));
      const api = createHttpApi("/api", unauthorized);
      await expect(api.me()).rejects.toBeInstanceOf(ApiError);
      expect(unauthorized).toHaveBeenCalledTimes(status === 401 ? 1 : 0);
    },
  );
  it("rejects invalid JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>")));
    await expect(createHttpApi().me()).rejects.toThrow("invalid response");
  });
  it("rejects a valid JSON with an invalid contract", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ items: [] })));
    await expect(createHttpApi().list()).rejects.toThrow("invalid response");
  });
  it("reports a disconnected backend", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await expect(createHttpApi().me()).rejects.toThrow("Cannot reach");
  });
  it("times out a hung request", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url, init) =>
          new Promise((_resolve, reject) =>
            init.signal.addEventListener("abort", () =>
              reject(new Error("aborted")),
            ),
          ),
      ),
    );
    await expect(createHttpApi("/api", () => {}, 10).me()).rejects.toThrow(
      "timed out",
    );
  });
  it("sends bearer identity only in headers, with no cookies", async () => {
    const fetcher = vi
      .fn()
      .mockImplementation(async () => response(demoProfile));
    vi.stubGlobal("fetch", fetcher);
    const api = createHttpApi();
    api.setToken("memory-only");
    await api.me();
    expect(fetcher.mock.calls[0][1].headers.Authorization).toBe(
      "Bearer memory-only",
    );
    expect(fetcher.mock.calls[0][1].credentials).toBe("omit");
    expect(fetcher.mock.calls[0][1].cache).toBe("no-store");
    expect(fetcher.mock.calls[0][1].redirect).toBe("error");
    api.setToken(null);
    await api.me();
    expect(fetcher.mock.calls[1][1].headers.Authorization).toBeUndefined();
  });
  it("encodes query values and paths", async () => {
    const fetcher = vi.fn().mockResolvedValue(response([]));
    vi.stubGlobal("fetch", fetcher);
    await createHttpApi().timeline("a/b?c");
    expect(fetcher.mock.calls[0][0]).toBe(
      "/api/tracking/by-tracking-number/a%2Fb%3Fc",
    );
  });
  it("never silently falls back to DEMO", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    await expect(createHttpApi().list()).rejects.toThrow();
  });
});
describe("explicit modes and isolated DEMO", () => {
  it("accepts an explicit AWS mode only with the fixed same-origin API path", () => {
    expect(readConfig({ VITE_APP_MODE: "aws" })).toEqual({
      mode: "aws",
      base: "/api",
    });
    expect(() =>
      readConfig({ VITE_APP_MODE: "aws", VITE_API_BASE: "/other" }),
    ).toThrow();
    expect(
      readConfig({ VITE_APP_MODE: "local", VITE_API_BASE: "/local/api" }).base,
    ).toBe("/local/api");
  });
  it.each([
    "/",
    "//host/api",
    "/\\host/api",
    "/api/../other",
    "/api/",
    "/api?x=1",
    "/api#fragment",
    "/%2fhost",
    "/api\n",
    123,
  ])("rejects ambiguous API prefix %s before a request can be sent", (base) =>
    expect(() => readConfig({ VITE_API_BASE: base })).toThrow(),
  );
  it("defaults to demo and rejects unknown modes or cross-origin prefixes", () => {
    expect(readConfig({}).mode).toBe("demo");
    expect(() => readConfig({ VITE_APP_MODE: "fallback" })).toThrow();
    expect(() =>
      readConfig({ VITE_API_BASE: "https://example.invalid" }),
    ).toThrow();
    expect(() => readConfig({ VITE_API_BASE: "//example.invalid" })).toThrow();
  });
  it("demo never fetches, has a real contract shape and resets per instance", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    const a = createDemoApi();
    await a.login("", "");
    a.setToken("demo");
    const before = await a.list();
    const created = await a.create({
      customerId: demoProfile.userId,
      origin: "A",
      destination: "B",
      weight: 1,
    });
    expect((await a.get(created.id)).status).toBe("CREATED");
    expect(await a.timeline(created.trackingNumber)).toEqual([]);
    expect((await a.list()).totalCount).toBe(before.totalCount + 1);
    const b = createDemoApi();
    await b.login("", "");
    expect((await b.list()).totalCount).toBe(before.totalCount);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("demo logout rejects further access", async () => {
    const api = createDemoApi();
    await api.login("", "");
    api.setToken(null);
    await expect(api.list()).rejects.toMatchObject({ status: 401 });
  });
  it.each([0, -1, 100001, NaN])(
    "rejects invalid shipment weight %s",
    (weight) => {
      expect(
        createSchema.safeParse({
          customerId: "id",
          origin: "A",
          destination: "B",
          weight,
        }).success,
      ).toBe(false);
    },
  );
});
