import assert from "node:assert/strict";
import {
  mkdtempSync,
  readFileSync,
  writeFileSync,
  rmSync,
  mkdirSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import { spawnSync } from "node:child_process";
const root = resolve(import.meta.dirname, "..");
const manifest = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
const lock = JSON.parse(readFileSync(join(root, "package-lock.json"), "utf8"));
assert.equal(lock.lockfileVersion, 3);
assert.deepEqual(lock.packages[""].dependencies, manifest.dependencies);
assert.deepEqual(lock.packages[""].devDependencies, manifest.devDependencies);
// Add a local-only dependency without updating the real lock. No registry is needed.
const directory = mkdtempSync(join(tmpdir(), "cnp-npm-lock-"));
try {
  mkdirSync(join(directory, "fixture"));
  writeFileSync(
    join(directory, "fixture/package.json"),
    JSON.stringify({ name: "cnp-lock-negative", version: "1.0.0" }),
  );
  manifest.dependencies["cnp-lock-negative"] = "file:./fixture";
  writeFileSync(join(directory, "package.json"), JSON.stringify(manifest));
  writeFileSync(join(directory, "package-lock.json"), JSON.stringify(lock));
  const result = spawnSync(
    process.platform === "win32" ? "npm.cmd" : "npm",
    ["ci", "--offline", "--ignore-scripts", "--no-audit", "--no-fund"],
    {
      cwd: directory,
      encoding: "utf8",
      shell: process.platform === "win32",
    },
  );
  assert.notEqual(result.status, 0, "Inconsistent lockfile was accepted");
  assert.match(result.stdout + result.stderr, /EUSAGE/);
  assert.match(
    result.stdout + result.stderr,
    /Missing:.*cnp-lock-negative|lock file.*in sync/s,
  );
  console.log("PASS: npm ci rejects inconsistent dependency locks offline");
} finally {
  rmSync(directory, { recursive: true });
}
