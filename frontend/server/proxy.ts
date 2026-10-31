import type { Plugin } from "vite";
import { readFileSync } from "node:fs";
import { profileSchema } from "../src/contracts.ts";
import { localConfigPath } from "../scripts/local-config.mjs";
const publicRoutes = new Set([
  "/auth/login",
  "/auth/register",
  "/auth/refresh",
]);
export function localApiProxy(
  readConfig = () =>
    JSON.parse(readFileSync(localConfigPath(), "utf8")) as {
      proxySecret: string;
    },
): Plugin {
  return {
    name: "localhost-authenticated-api",
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const path = req.url ?? "";
        if (!path.startsWith("/api/")) return next();
        const origin = req.headers.origin;
        if (
          origin &&
          origin !== "http://localhost:5173" &&
          origin !== "http://127.0.0.1:5173"
        ) {
          res.statusCode = 403;
          res.end();
          return;
        }
        if (
          req.headers.host !== "localhost:5173" &&
          req.headers.host !== "127.0.0.1:5173"
        ) {
          res.statusCode = 403;
          res.end();
          return;
        }
        res.setHeader("Cache-Control", "no-store");
        const reply = (status: number, message: string) => {
          res.statusCode = status;
          res.setHeader("Content-Type", "application/json");
          res.end(JSON.stringify({ message }));
        };
        try {
          const config = readConfig();
          if (!config.proxySecret || config.proxySecret.length < 32)
            throw new Error("Invalid local configuration");
          const route = path.slice(4);
          const bare = route.split("?")[0];
          const method = req.method ?? "GET";
          const allowed =
            (method === "POST" && publicRoutes.has(bare)) ||
            (method === "GET" && bare === "/auth/me") ||
            (method === "GET" &&
              (/^\/shipments(?:\/by-id\/[a-fA-F0-9-]+|\/by-tracking\/[^/]+)?$/.test(
                bare,
              ) ||
                /^\/tracking\/by-(?:shipment|tracking-number)\/[^/]+$/.test(
                  bare,
                ))) ||
            (method === "POST" && bare === "/shipments");
          if (!allowed) {
            reply(404, "Route not exposed by local UI proxy.");
            return;
          }
          const service = bare.startsWith("/auth/")
            ? 0
            : bare.startsWith("/shipments")
              ? 1
              : 2;
          const headers: Record<string, string> = {
            Accept: "application/json",
            "Content-Type": "application/json",
          };
          const authorization = req.headers.authorization;
          if (!publicRoutes.has(bare)) {
            if (!authorization?.startsWith("Bearer ")) {
              reply(401, "Sign in required.");
              return;
            }
            const identity = await fetch("http://127.0.0.1:8080/auth/me", {
              headers: { Authorization: authorization },
              signal: AbortSignal.timeout(8000),
              redirect: "error",
            });
            if (!identity.ok) {
              reply(
                identity.status === 401 || identity.status === 403
                  ? identity.status
                  : 502,
                "Identity validation failed.",
              );
              return;
            }
            const profile = profileSchema.parse(await identity.json());
            if (!profile.isActive) {
              reply(403, "Account disabled.");
              return;
            }
            headers.Authorization = authorization;
            if (service !== 0)
              Object.assign(headers, {
                "X-Platform-User-Id": profile.userId,
                "X-Platform-Email": profile.email,
                "X-Platform-Roles": profile.roles.join(","),
                "X-Platform-Proxy-Secret": config.proxySecret,
              });
          }
          let body: Buffer | undefined;
          if (method === "POST") {
            const chunks: Buffer[] = [];
            let length = 0;
            for await (const chunk of req) {
              const part = Buffer.from(chunk);
              length += part.length;
              if (length > 16384) {
                reply(413, "Request too large.");
                return;
              }
              chunks.push(part);
            }
            body = Buffer.concat(chunks);
          }
          const response = await fetch(
            `http://127.0.0.1:${8080 + service}${route}`,
            {
              method,
              headers,
              body: body?.toString("utf8"),
              signal: AbortSignal.timeout(10000),
              redirect: "error",
            },
          );
          res.statusCode = response.status;
          res.setHeader("Content-Type", "application/json");
          res.end(await response.text());
        } catch {
          reply(
            502,
            "Local backend unavailable. Run npm run backend and verify service health.",
          );
        }
      });
    },
  };
}
