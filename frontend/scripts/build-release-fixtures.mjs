// LOCAL_SIMULATED source variants only. Never publishes or changes tracked App.tsx.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";
import { build } from "vite";

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repo = resolve(frontend, "..");
const output = resolve(repo, ".validation-results/frontend-release-lifecycle");
assert.ok(!existsSync(output), "Preserve existing fixture builds and receipts");
const sha = (value) => createHash("sha256").update(value).digest("hex");
const appPath = resolve(frontend, "src/App.tsx");
const original = readFileSync(appPath, "utf8");
const anchor = 'title="Shipment overview"';
assert.equal(original.split(anchor).length, 2, "Fixture source anchor drift");
const candidate = original.replace(
  anchor,
  'title="Shipment overview - local source release B"',
);
assert.notEqual(sha(original), sha(candidate));
const baseCommit = execFileSync("git", ["rev-parse", "HEAD"], {
  cwd: repo,
  encoding: "utf8",
}).trim();
mkdirSync(output, { recursive: true });
writeFileSync(resolve(output, "App.release-b.tsx.txt"), candidate);
const releases = {};
for (const [id, mode, version] of [
  ["a", "aws", "0.0.0-local.a"],
  ["b", "aws", "0.0.0-local.b"],
  ["demo", "demo", "0.0.0-local.demo"],
]) {
  let transformed = false;
  await build({
    root: frontend,
    mode,
    build: { outDir: resolve(output, id), emptyOutDir: false },
    plugins:
      id === "b"
        ? [
            {
              name: "local-simulated-source-release-b",
              enforce: "pre",
              transform(source, moduleId) {
                if (
                  moduleId.split("?")[0].replaceAll("\\", "/") !==
                  appPath.replaceAll("\\", "/")
                )
                  return;
                assert.equal(
                  source,
                  original,
                  "Unexpected pre-transformed source",
                );
                transformed = true;
                return { code: candidate, map: null };
              },
            },
          ]
        : [],
  });
  assert.equal(transformed, id === "b");
  const receiptBytes = readFileSync(resolve(output, id, "frontend-build.json"));
  const receipt = JSON.parse(receiptBytes);
  assert.equal(receipt.configuration.mode, mode);
  const artifact = resolve(output, `${id}.tgz`);
  const packaged = JSON.parse(
    execFileSync(
      process.env.CNP_PYTHON ?? "python",
      [
        resolve(frontend, "scripts/package_static.py"),
        "build",
        "--dist",
        resolve(output, id),
        "--mode",
        mode,
        "--source-base",
        baseCommit,
        "--output",
        artifact,
      ],
      { encoding: "utf8", cwd: repo },
    ),
  );
  releases[id] = {
    version,
    mode,
    baseCommit,
    sourceAppSha256: sha(id === "b" ? candidate : original),
    isolatedSourceOverlay: id === "b",
    artifactSha256: packaged.sha256,
    buildReceiptSha256: sha(receiptBytes),
    files: receipt.files,
  };
}
assert.equal(sha(readFileSync(appPath)), sha(original));
assert.notEqual(releases.a.artifactSha256, releases.b.artifactSha256);
assert.notDeepEqual(releases.a.files, releases.b.files);
writeFileSync(
  resolve(output, "releases.json"),
  JSON.stringify(
    {
      classification: "LOCAL_SIMULATED",
      realAwsOrAuth: false,
      sourceVariantLimit:
        "B is a documented isolated App.tsx source overlay, not a committed/deployed product release; baseCommit is provenance base only.",
      releases,
    },
    null,
    2,
  ) + "\n",
);
console.log(
  "LOCAL_SIMULATED: three separate source/mode fixtures packaged; tracked App.tsx unchanged",
);
