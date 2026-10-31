import { architectureAssets } from "./scripts/architecture-assets.mjs";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { localApiProxy } from "./server/proxy.ts";
import { readConfig } from "./src/config.ts";
import { staticBuildReceipt } from "./scripts/static-build-receipt.mjs";
export default defineConfig(({ mode, command }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  if (mode === "api") env.VITE_APP_MODE = "local";
  if (mode === "demo") env.VITE_APP_MODE = "demo";
  if (mode === "aws") env.VITE_APP_MODE = "aws";
  const config = readConfig(env);
  if (command === "build" && config.mode === "local")
    throw new Error(
      "LOCAL API is development-only. Build with demo or aws mode.",
    );
  return {
    define: {
      "import.meta.env.VITE_APP_MODE": JSON.stringify(config.mode),
      "import.meta.env.VITE_API_BASE": JSON.stringify(config.base),
    },
    plugins: [
      react(),
      architectureAssets(),
      staticBuildReceipt(config),
      ...(config.mode === "local" ? [localApiProxy()] : []),
    ],
    server: {
      host: "127.0.0.1",
      port: 5173,
      strictPort: true,
      fs: {
        strict: true,
        allow: [process.cwd()],
        deny: [
          ".env",
          ".env.*",
          "*.{crt,pem}",
          "**/.git/**",
          "**/.validation-results/**",
        ],
      },
    },
    preview: { host: "127.0.0.1", port: 4173, strictPort: true },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test-setup.ts"],
      include: ["src/**/*.test.{ts,tsx}", "server/**/*.test.ts"],
    },
  };
});
