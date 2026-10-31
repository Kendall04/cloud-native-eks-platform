// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import viteConfig from "../vite.config";

afterEach(() => vi.unstubAllEnvs());

describe("static API build boundary", () => {
  it.each(["demo", "aws"])(
    "builds %s without the LOCAL server proxy",
    (mode) => {
      vi.stubEnv("VITE_API_BASE", "/api");
      const config = viteConfig({ mode, command: "build" });
      expect(config.define?.["import.meta.env.VITE_APP_MODE"]).toBe(
        JSON.stringify(mode),
      );
      expect(config.define?.["import.meta.env.VITE_API_BASE"]).toBe('"/api"');
      expect(JSON.stringify(config.plugins)).not.toContain(
        "localhost-authenticated-api",
      );
    },
  );
  it("retains the proxy for explicit LOCAL development", () => {
    vi.stubEnv("VITE_API_BASE", "/api");
    const config = viteConfig({ mode: "api", command: "serve" });
    expect(JSON.stringify(config.plugins)).toContain(
      "localhost-authenticated-api",
    );
  });
  it("rejects LOCAL static builds before packaging", () => {
    vi.stubEnv("VITE_API_BASE", "/api");
    expect(() => viteConfig({ mode: "api", command: "build" })).toThrow(
      "development-only",
    );
  });
  it("rejects unknown environment modes at build time", () => {
    vi.stubEnv("VITE_APP_MODE", "fallback");
    expect(() => viteConfig({ mode: "production", command: "build" })).toThrow(
      "VITE_APP_MODE",
    );
  });
  it("rejects an external AWS API prefix at build time", () => {
    vi.stubEnv("VITE_API_BASE", "https://example.invalid/api");
    expect(() => viteConfig({ mode: "aws", command: "build" })).toThrow(
      "same-origin",
    );
  });
});
