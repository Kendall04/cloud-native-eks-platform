// Data-only receipt for the final Vite output; no environment dump or credentials.
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { resolve, relative } from "node:path";
import { createHash } from "node:crypto";
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
export function staticBuildReceipt(config) {
  return {
    name: "static-build-receipt",
    writeBundle(options) {
      const directory = resolve(options.dir);
      const names = readdirSync(directory, {
        recursive: true,
        withFileTypes: true,
      })
        .filter((entry) => entry.isFile())
        .map((entry) =>
          relative(directory, resolve(entry.parentPath, entry.name)).replaceAll(
            "\\",
            "/",
          ),
        )
        .sort();
      if (names.includes("frontend-build.json"))
        throw new Error(
          "Stale frontend build receipt; use a clean output directory",
        );
      const receipt = {
        schemaVersion: 1,
        configuration: { mode: config.mode, apiBase: config.base },
        toolchain: { node: process.versions.node },
        files: Object.fromEntries(
          names.map((name) => {
            const bytes = readFileSync(resolve(directory, name));
            return [name, { sha256: sha(bytes), bytes: bytes.length }];
          }),
        ),
      };
      writeFileSync(
        resolve(directory, "frontend-build.json"),
        JSON.stringify(receipt, null, 2) + "\n",
      );
    },
  };
}
