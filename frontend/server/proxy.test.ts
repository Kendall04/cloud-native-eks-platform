// @vitest-environment node
import { describe, it, expect, vi } from "vitest";
import { Readable } from "node:stream";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { ViteDevServer } from "vite";
import { localApiProxy } from "./proxy";
import { demoProfile } from "../src/demo";
type Middleware = (
  req: IncomingMessage,
  res: ServerResponse,
  next: () => void,
) => Promise<void>;
async function invoke(
  path: string,
  options: {
    method?: string;
    body?: string;
    headers?: Record<string, string>;
    missingConfig?: boolean;
  } = {},
) {
  let middleware: Middleware = async () => {};
  const plugin = localApiProxy(() => {
    if (options.missingConfig) throw new Error("Missing");
    return { proxySecret: "test-only-".repeat(5) };
  });
  const configure = plugin.configureServer as (s: ViteDevServer) => void;
  configure({
    middlewares: {
      use: (m: Middleware) => {
        middleware = m;
      },
    },
  } as unknown as ViteDevServer);
  const req = Readable.from(
    options.body ? [options.body] : [],
  ) as IncomingMessage;
  req.url = path;
  req.method = options.method ?? "GET";
  req.headers = {
    host: "127.0.0.1:5173",
    authorization: "Bearer fixture",
    ...options.headers,
  };
  let body = "";
  const headers: Record<string, string> = {};
  const res = {
    statusCode: 200,
    setHeader: (k: string, v: string) => {
      headers[k] = v;
    },
    end: (value = "") => {
      body = value;
    },
  };
  const next = vi.fn();
  await middleware(req, res as unknown as ServerResponse, next);
  return { ...res, body, headers, next };
}
describe("loopback authenticated development proxy", () => {
  it("passes non-API requests through", async () => {
    expect((await invoke("/")).next).toHaveBeenCalled();
  });
  it("fails closed when configuration is missing", async () => {
    expect(
      (await invoke("/api/shipments", { missingConfig: true })).statusCode,
    ).toBe(502);
  });
  it.each([
    "/api/admin/tracking-events",
    "/api/internal/shipments/x",
    "/api/../../internal/shipments",
    "/api/auth/validate",
  ])("does not expose %s", async (path) => {
    expect((await invoke(path)).statusCode).toBe(404);
  });
  it("rejects non-local origins", async () => {
    expect(
      (
        await invoke("/api/shipments", {
          headers: { origin: "https://host.invalid" },
        })
      ).statusCode,
    ).toBe(403);
  });
  it("rejects unexpected Host headers", async () => {
    expect(
      (await invoke("/api/shipments", { headers: { host: "evil.invalid" } }))
        .statusCode,
    ).toBe(403);
  });
  it("rejects missing tokens before contacting a service", async () => {
    const f = vi.fn();
    vi.stubGlobal("fetch", f);
    expect(
      (await invoke("/api/shipments", { headers: { authorization: "" } }))
        .statusCode,
    ).toBe(401);
    expect(f).not.toHaveBeenCalled();
  });
  it("rejects an expired/invalid token when Auth rejects it", async () => {
    const f = vi.fn().mockResolvedValue(new Response("", { status: 401 }));
    vi.stubGlobal("fetch", f);
    expect((await invoke("/api/shipments")).statusCode).toBe(401);
    expect(f).toHaveBeenCalledTimes(1);
  });
  it("fails closed on invalid identity responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(Response.json({ userId: "forged" })),
    );
    expect((await invoke("/api/shipments")).statusCode).toBe(502);
  });
  it("forwards only Auth-verified identity and drops forged browser privilege headers", async () => {
    const f = vi
      .fn()
      .mockResolvedValueOnce(Response.json(demoProfile))
      .mockResolvedValueOnce(Response.json({ items: [] }));
    vi.stubGlobal("fetch", f);
    const r = await invoke("/api/shipments", {
      headers: {
        "x-platform-user-id": "forged",
        "x-platform-roles": "ADMIN",
        "x-platform-internal-secret": "forged",
      },
    });
    expect(r.statusCode).toBe(200);
    expect(r.headers["Cache-Control"]).toBe("no-store");
    const headers = f.mock.calls[1][1].headers;
    expect(headers["X-Platform-User-Id"]).toBe(demoProfile.userId);
    expect(headers["X-Platform-Roles"]).toBe("USER");
    expect(headers["X-Platform-Internal-Secret"]).toBeUndefined();
    expect(headers.Authorization).toBe("Bearer fixture");
  });
  it("keeps invalid upstream payloads visible to the client instead of creating demo data", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(Response.json(demoProfile))
        .mockResolvedValueOnce(new Response("unavailable", { status: 500 })),
    );
    expect((await invoke("/api/shipments")).statusCode).toBe(500);
  });
  it("bounds request bodies", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(Response.json(demoProfile)),
    );
    expect(
      (
        await invoke("/api/shipments", {
          method: "POST",
          body: "a".repeat(16385),
        })
      ).statusCode,
    ).toBe(413);
  });
});
