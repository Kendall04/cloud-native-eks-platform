import { defineConfig } from "@playwright/test";
const releaseAttempt = process.env.UI_RELEASE_ATTEMPT ?? "attempt1";
if (
  process.env.UI_TEST_MODE === "release-lifecycle" &&
  !/^attempt[1-9][0-9]*$/.test(releaseAttempt)
)
  throw new Error("Use a fresh bounded release-lifecycle attempt label");
export default defineConfig({
  testDir: "./browser",
  testMatch:
    process.env.UI_TEST_MODE === "release-lifecycle"
      ? "**/release-lifecycle.spec.ts"
      : process.env.UI_TEST_MODE === "aws"
        ? "**/aws.spec.ts"
        : process.env.UI_TEST_MODE === "portfolio"
          ? [
              "**/architecture.spec.ts",
              "**/architecture-reading.spec.ts",
              "**/accessibility.spec.ts",
              "**/immersive.spec.ts",
              "**/demo.spec.ts",
            ]
          : process.env.UI_TEST_MODE === "v2"
            ? [
                "**/architecture.spec.ts",
                "**/architecture-reading.spec.ts",
                "**/accessibility.spec.ts",
                "**/immersive.spec.ts",
              ]
            : process.env.UI_TEST_MODE === "demo"
              ? "**/demo.spec.ts"
              : "**/workspace.spec.ts",
  fullyParallel: false,
  workers: 1,
  reporter:
    process.env.CI === "true"
      ? [
          ["list"],
          [
            "junit",
            {
              outputFile:
                process.env.UI_TEST_MODE === "release-lifecycle"
                  ? `../.validation-results/frontend-release-lifecycle/${releaseAttempt}/results.xml`
                  : process.env.UI_TEST_MODE === "local"
                    ? "../.validation-results/frontend-api/browser.xml"
                    : "../.validation-results/frontend/browser.xml",
            },
          ],
        ]
      : "list",
  webServer:
    process.env.CI === "true" &&
    process.env.UI_TEST_MODE !== "local" &&
    process.env.UI_TEST_MODE !== "release-lifecycle"
      ? {
          command: "node node_modules/vite/bin/vite.js preview --port 4175",
          url: "http://127.0.0.1:4175",
          reuseExistingServer: false,
          timeout: 30000,
        }
      : undefined,
  use: {
    baseURL:
      process.env.UI_TEST_URL ??
      (process.env.UI_TEST_MODE === "demo"
        ? "http://127.0.0.1:5174"
        : "http://127.0.0.1:5173"),
    channel: "chrome",
    headless: true,
    viewport: { width: 1440, height: 900 },
    // Only synthetic DEMO requests may appear in diagnostic network traces.
    trace:
      process.env.CI === "true" &&
      process.env.UI_TEST_MODE !== "local" &&
      process.env.UI_TEST_MODE !== "release-lifecycle"
        ? "retain-on-failure"
        : "off",
    screenshot: process.env.CI === "true" ? "only-on-failure" : "off",
  },
  outputDir:
    process.env.CI === "true"
      ? process.env.UI_TEST_MODE === "release-lifecycle"
        ? `../.validation-results/frontend-release-lifecycle/${releaseAttempt}/browser`
        : process.env.UI_TEST_MODE === "local"
          ? "../.validation-results/frontend-api/browser"
          : "../.validation-results/frontend/browser"
      : "../.validation-results/local-ui/browser",
});
