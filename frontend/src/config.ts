export type AppMode = "demo" | "local" | "aws";

// Shared by Vite and the browser so an invalid release fails before packaging.
export function readConfig(env: Record<string, unknown>) {
  const mode = env.VITE_APP_MODE ?? "demo";
  if (mode !== "demo" && mode !== "local" && mode !== "aws")
    throw new Error("VITE_APP_MODE must be demo, local or aws.");
  const base = env.VITE_API_BASE ?? "/api";
  if (
    typeof base !== "string" ||
    !/^\/[a-zA-Z0-9_-]+(?:\/[a-zA-Z0-9_-]+)*$/.test(base)
  )
    throw new Error("This UI requires a normalized same-origin API prefix.");
  if (mode === "aws" && base !== "/api")
    throw new Error("AWS API mode requires the same-origin /api prefix.");
  return { mode, base } as const;
}
