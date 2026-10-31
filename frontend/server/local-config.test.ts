// @vitest-environment node
import { describe, it, expect } from "vitest";
import { localConfigDirectory } from "../scripts/local-config.mjs";
describe("isolated disposable API configuration", () => {
  it("keeps the ordinary developer location", () =>
    expect(localConfigDirectory({})).toMatch(/local-ui$/));
  it("gives CI a separate ignored configuration", () =>
    expect(localConfigDirectory({ CI: "true", CNP_LOCAL_UI_CI: "1" })).toMatch(
      /local-ui-ci$/,
    ));
  it("rejects CI mode without explicit disposable-runner intent", () =>
    expect(() => localConfigDirectory({ CNP_LOCAL_UI_CI: "1" })).toThrow(
      /CI=true/,
    ));
  it("does not change normal development simply because CI is set", () =>
    expect(localConfigDirectory({ CI: "true" })).toMatch(/local-ui$/));
});
