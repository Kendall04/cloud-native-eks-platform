// Disposable runner-only integration. Never touches the developer database or volume.
import { spawn } from "node:child_process";
import { openSync, mkdirSync, writeFileSync, closeSync } from "node:fs";
import { resolve } from "node:path";
import { createServer } from "node:net";
import { localConfigDirectory } from "./local-config.mjs";
if (process.env.CI !== "true")
  throw new Error(
    "Use this command only with CI=true and disposable PostgreSQL",
  );
const env = { ...process.env, CI: "true", CNP_LOCAL_UI_CI: "1" };
const root = resolve(import.meta.dirname, "..");
const output = resolve(root, "../.validation-results/frontend-api");
const privateDir = localConfigDirectory(env);
mkdirSync(output, { recursive: true });
mkdirSync(privateDir, { recursive: true });
const log = openSync(resolve(privateDir, "processes.private.log"), "w", 0o600);
const children = [];
function start(args) {
  const child = spawn(process.execPath, args, {
    cwd: root,
    env,
    stdio: ["ignore", log, log],
  });
  children.push(child);
  return child;
}
async function command(args, extra = {}) {
  const child = spawn(process.execPath, args, {
    cwd: root,
    env: { ...env, ...extra },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "",
    stderr = "";
  child.stdout.on("data", (chunk) => (stdout += chunk));
  child.stderr.on("data", (chunk) => (stderr += chunk));
  const code = await new Promise((accept, reject) => {
    child.on("error", reject);
    child.on("exit", accept);
  });
  if (code !== 0)
    throw new Error(
      `Integration command failed (${args[0]}). ${stderr || stdout}`,
    );
  return stdout;
}
async function wait(url) {
  for (let i = 0; i < 240; i++) {
    if (children.some((child) => child.exitCode !== null))
      throw new Error("A local service stopped; inspect private runner logs");
    try {
      if ((await fetch(url, { signal: AbortSignal.timeout(1000) })).ok) return;
    } catch {
      /* bounded polling */
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error("Local service readiness timed out");
}
try {
  for (const port of [5173, 8080, 8081, 8082])
    await new Promise((accept, reject) => {
      const server = createServer();
      server.on("error", reject);
      server.listen(port, "127.0.0.1", () => server.close(accept));
    });
  start(["scripts/local-backend.mjs"]);
  for (const port of [8080, 8081, 8082])
    await wait(`http://127.0.0.1:${port}/health/ready`);
  start(["node_modules/vite/bin/vite.js", "--mode", "api"]);
  await wait("http://127.0.0.1:5173");
  const text = await command(["scripts/api-integration.mjs"]);
  const http = JSON.parse(
    text.split("\n").find((line) => line.startsWith("{")),
  );
  if (http.httpAssertions !== 22 || http.result !== "PASS")
    throw new Error("Incomplete HTTP integration");
  console.log(text.trim());
  const browser = await command(
    ["node_modules/@playwright/test/cli.js", "test"],
    { UI_TEST_MODE: "local", UI_TEST_URL: "http://127.0.0.1:5173" },
  );
  console.log(browser.trim());
  writeFileSync(
    resolve(output, "http.json"),
    JSON.stringify(
      {
        ...http,
        privateFileDenied: true,
        browserTests: 2,
        mode: "LOCAL_API",
        postgresql: "15.18",
        awsEventsTested: false,
      },
      null,
      2,
    ),
  );
} finally {
  await Promise.all(
    children.map(
      (child) =>
        new Promise((accept) => {
          if (child.exitCode !== null) return accept();
          child.once("exit", accept);
          child.kill("SIGTERM");
        }),
    ),
  );
  closeSync(log);
}
