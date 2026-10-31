import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
export function localConfigDirectory(env = process.env) {
  const ci = env.CNP_LOCAL_UI_CI === "1";
  if (ci && env.CI !== "true") throw new Error("CI API mode requires CI=true");
  return resolve(
    dirname(fileURLToPath(import.meta.url)),
    "../../.validation-results",
    ci ? "local-ui-ci" : "local-ui",
  );
}
export const localConfigPath = () =>
  resolve(localConfigDirectory(), "backend.json");
