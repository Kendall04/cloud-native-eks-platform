// Offline checks for built presentation exports; compiles inline JS without executing it.
import assert from "node:assert/strict";
import {
  readFileSync,
  existsSync,
  readdirSync,
  mkdirSync,
  writeFileSync,
} from "node:fs";
import { Script } from "node:vm";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import {
  diagramNames,
  presentationExport,
  sha256,
  publicEvidence,
  architectureAssetPaths,
} from "./architecture-assets.mjs";
const assetPaths = architectureAssetPaths();
const dir = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../dist/architecture-assets",
);
assert.ok(existsSync(dir), "Run npm run build first");
for (const name of diagramNames) {
  const expected = presentationExport(name);
  const built = JSON.parse(
    readFileSync(
      resolve(dir, "..", assetPaths[name + ".json"].slice(1)),
      "utf8",
    ),
  );
  assert.deepEqual(built, expected);
  let scripts = 0;
  for (const match of built.html.matchAll(
    /<script([^>]*)>([\s\S]*?)<\/script>/g,
  )) {
    scripts++;
    if (match[1].includes("application/json")) JSON.parse(match[2]);
    else
      new Script(match[2], { filename: name + "-inline-" + scripts + ".js" });
  }
  assert.equal(scripts, 5);
  assert.equal(sha256(built.html), built.presentationSha256);
  assert.ok(built.html.includes("connect-src 'none'"));
  assert.ok(!/<a[^>]+href=|<script[^>]+src=|<link[^>]+href=/.test(built.html));
  console.log(
    "PASS: " +
      name +
      " original/export integrity, inline JS syntax, inert links and offline CSP",
  );
}
assert.deepEqual(
  JSON.parse(
    readFileSync(
      resolve(dir, "..", assetPaths["evidence.json"].slice(1)),
      "utf8",
    ),
  ),
  publicEvidence(),
);
assert.ok(
  existsSync(resolve(dir, "..", assetPaths["ARCHIFY-LICENSE.txt"].slice(1))),
);
assert.ok(!readdirSync(dir).some((file) => file.endsWith(".html")));
console.log("PASS: curated evidence, license and JSON-only publication assets");
const dist = resolve(dir, "..");
const files = readdirSync(dist, { recursive: true, withFileTypes: true })
  .filter((f) => f.isFile())
  .map((f) => resolve(f.parentPath, f.name));
const secret =
  /\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{30,}\b|github_pat_[A-Za-z0-9_]{30,}|\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\b/;
for (const file of files) {
  assert.ok(
    /\.(?:html|css|js|json|txt)$/.test(file),
    "Unexpected build artifact",
  );
  assert.ok(
    !secret.test(readFileSync(file, "utf8")),
    "Credential pattern in build: " + file,
  );
}
const index = readFileSync(resolve(dist, "index.html"), "utf8");
const sourceIcon = readFileSync(resolve(dist, "../index.html"), "utf8").match(
  /href="([^"]+)"/,
)?.[1];
for (const [, url] of index.matchAll(/(?:src|href)="([^"]+)"/g)) {
  if (url.startsWith("data:")) {
    assert.equal(url, sourceIcon);
    assert.ok(
      !/<script|\bon\w+=|href=|foreignObject|<image/i.test(
        decodeURIComponent(url),
      ),
    );
  } else assert.match(url, /^\/assets\/[a-zA-Z0-9_.-]+$/);
}
const output = resolve(dist, "../../.validation-results/frontend");
mkdirSync(output, { recursive: true });
writeFileSync(
  resolve(output, "architecture.json"),
  JSON.stringify(
    {
      result: "PASS",
      diagrams: diagramNames.map((name) => ({
        name,
        originalSha256: presentationExport(name).originalSha256,
        presentationSha256: presentationExport(name).presentationSha256,
      })),
      scriptSyntax: "PASS",
      inertJsonAssets: "PASS",
      offlineCsp: "PASS",
      buildSecretPatterns: "PASS",
      files: files.length,
      bytes: files.reduce((n, f) => n + readFileSync(f).length, 0),
    },
    null,
    2,
  ),
);
console.log(
  "PASS: compiled build credential patterns and local entrypoint assets",
);
