import { architectureAssetPaths } from "../scripts/architecture-assets.mjs";
import { test, expect } from "@playwright/test";
const assetPaths = architectureAssetPaths();
const diagrams = [
  ["platform", "Platform architecture"],
  ["networking", "Private networking"],
  ["event-processing", "Reliable event processing"],
  ["private-cd", "Private delivery"],
  ["security", "Security & Trust Boundaries"],
] as const;
test("public navigation, direct URLs, history, session preservation and screenshots", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/architecture");
  await expect(
    page.getByRole("heading", { name: "Architecture Explorer" }),
  ).toBeVisible();
  await page.screenshot({
    path: "../.validation-results/local-ui/v2-explorer-overview.png",
    fullPage: true,
  });
  await expect(page).toHaveURL(/\/architecture$/);
  await page
    .getByRole("navigation", { name: "Choose workspace" })
    .getByRole("link", { name: "Logistics Demo", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Enter demo workspace →" }),
  ).toBeVisible();
  await page.screenshot({
    path: "../.validation-results/local-ui/v2-welcome.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Enter demo workspace →" }).click();
  await expect(
    page.getByRole("heading", { name: "Shipment overview" }),
  ).toBeVisible();
  await page.screenshot({
    path: "../.validation-results/local-ui/v2-dashboard.png",
    fullPage: true,
  });
  await page
    .getByRole("link", { name: "Architecture Explorer", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Architecture Explorer" }),
  ).toBeVisible();
  await page
    .getByRole("navigation", { name: "Architecture navigation" })
    .getByRole("link", { name: "Event-driven flow" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Reliable event processing" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByTitle("Reliable event processing interactive diagram"),
  ).toBeVisible();
  await page.goBack();
  await expect(
    page.getByRole("heading", { name: "Architecture Explorer" }),
  ).toBeVisible();
  await page.goForward();
  await expect(
    page.getByRole("heading", { name: "Reliable event processing" }),
  ).toBeVisible();
  await page.goto("/architecture/missing");
  await expect(
    page.getByRole("heading", { name: "Architecture page not found" }),
  ).toBeVisible();
  await page.goto("/demo/missing");
  await expect(
    page.getByRole("button", { name: "Enter demo workspace →" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Enter demo workspace →" }).click();
  await expect(
    page.getByRole("heading", { name: "Page not found" }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Architecture Explorer", exact: true })
    .click();
  await expect(page).toHaveURL(/\/architecture$/);
  await page
    .getByRole("navigation", { name: "Choose workspace" })
    .getByRole("link", { name: "Logistics Demo", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Shipment overview" }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
for (const [id, title] of diagrams)
  test(`${id}: original interactive controls, isolated origin and offline assets`, async ({
    page,
  }) => {
    const external: string[] = [];
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("request", (r) => {
      if (
        !r
          .url()
          .startsWith(
            new URL(process.env.UI_TEST_URL ?? "http://127.0.0.1:5173").origin,
          ) &&
        !r.url().startsWith("data:") &&
        !r.url().startsWith("blob:")
      )
        external.push(r.url());
    });
    await page.goto("/architecture/" + id);
    await expect(
      page.getByRole("heading", { name: title, exact: true }),
    ).toBeVisible();
    const frame = page.frameLocator("iframe");
    const node = frame.locator("svg [data-node-id]").first();
    await expect(node).toBeVisible();
    await frame
      .getByRole("button", { name: "Find a node", exact: true })
      .click();
    await frame
      .getByRole("searchbox", { name: "Search diagram nodes" })
      .fill((await node.getAttribute("data-node-label")) ?? "");
    await frame.locator(".node-finder-result").first().click();
    await expect(node).toHaveAttribute("aria-pressed", "true");
    await expect(frame.locator("#btn-reach-downstream")).toBeVisible();
    const reach = (await frame.locator("#btn-reach-downstream").isEnabled())
      ? frame.locator("#btn-reach-downstream")
      : frame.locator("#btn-reach-upstream");
    await reach.click();
    await expect(reach).toHaveAttribute("aria-pressed", "true");
    const initial = await frame.locator("html").getAttribute("data-theme");
    await frame.getByRole("button", { name: "Toggle color theme" }).click();
    expect(await frame.locator("html").getAttribute("data-theme")).not.toBe(
      initial,
    );
    if (await frame.locator("#btn-focus-clear").isVisible())
      await frame.locator("#btn-focus-clear").click();
    await frame
      .getByRole("button", { name: "Find a node", exact: true })
      .click();
    await expect(
      frame.getByRole("searchbox", { name: "Search diagram nodes" }),
    ).toBeVisible();
    await frame
      .getByRole("searchbox", { name: "Search diagram nodes" })
      .fill((await node.getAttribute("data-node-label")) ?? "");
    await expect(frame.locator(".node-finder-result").first()).toBeVisible();
    await frame.locator("#node-finder-close").click();
    const f = page.frames().find((f) => f.url() === "about:srcdoc")!;
    expect(
      await f.evaluate(() => {
        try {
          void window.parent.document.body;
          return false;
        } catch {
          return true;
        }
      }),
    ).toBe(true);
    expect(
      await f.evaluate(() => {
        try {
          void localStorage.length;
          return false;
        } catch {
          return true;
        }
      }),
    ).toBe(true);
    await expect(page.locator("iframe")).toHaveAttribute(
      "sandbox",
      "allow-scripts allow-downloads",
    );
    expect(await frame.locator("a[href]").count()).toBe(0);
    const asset = await page.request.get(assetPaths[id + ".json"]);
    expect(asset.headers()["content-type"]).toContain("application/json");
    expect((await asset.json()).html).not.toContain("Kendall04");
    await page
      .getByRole("button", { name: "Expand view", exact: true })
      .click();
    await expect(page.locator(".diagram-viewer")).toHaveClass(/is-expanded/);
    await page.screenshot({
      path: "../.validation-results/local-ui/v2-" + id + "-expanded.png",
      fullPage: true,
    });
    await frame.locator("body").press("Escape");
    await expect(page.locator(".diagram-viewer")).not.toHaveClass(
      /is-expanded/,
    );
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    expect(external).toEqual([]);
    expect(errors).toEqual([]);
  });
test("fullscreen and diagram error/retry", async ({ page }) => {
  await page.goto("/architecture/platform");
  await expect(
    page.frameLocator("iframe").locator("svg [data-node-id]").first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Fullscreen", exact: true }).click();
  await expect
    .poll(() => page.evaluate(() => !!document.fullscreenElement))
    .toBe(true);
  await page.evaluate(() => document.exitFullscreen());
  await page.route("**" + assetPaths["networking.json"], (route) =>
    route.fulfill({ status: 404, body: "missing" }),
  );
  await page.goto("/architecture/networking");
  await expect(page.getByRole("alert")).toContainText("could not be loaded");
  await page.unroute("**" + assetPaths["networking.json"]);
  await page.getByRole("button", { name: "Retry diagram" }).click();
  await expect(
    page.frameLocator("iframe").locator("svg [data-node-id]").first(),
  ).toBeVisible();
});
test("mobile/tablet layouts, keyboard focus and synthetic examples", async ({
  page,
}) => {
  await page.goto("/demo/tracking");
  await page.getByRole("button", { name: "Enter demo workspace →" }).click();
  await expect(
    page.getByRole("button", { name: "DEMO-2026-001", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "../.validation-results/local-ui/v2-tracking-empty.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "DEMO-2026-002", exact: true })
    .click();
  await expect(page.getByText("Regional hub")).toBeVisible();
  await page.screenshot({
    path: "../.validation-results/local-ui/v2-tracking-delivered.png",
    fullPage: true,
  });
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name: "▱ Shipments", exact: true })
    .click();
  await page.screenshot({
    path: "../.validation-results/local-ui/v2-shipments.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "＋ Create shipment" }).click();
  await page.screenshot({
    path: "../.validation-results/local-ui/v2-create.png",
    fullPage: true,
  });
  for (const width of [390, 768]) {
    await page.setViewportSize({ width, height: 900 });
    await page
      .getByRole("link", { name: "Architecture Explorer", exact: true })
      .click();
    await expect(page).toHaveURL(/\/architecture$/);
    await expect(
      page
        .getByRole("navigation", { name: "Choose workspace" })
        .getByRole("link", { name: "Logistics Demo", exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: "../.validation-results/local-ui/v2-explorer-" + width + ".png",
      fullPage: true,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page
      .getByRole("navigation", { name: "Architecture navigation" })
      .getByRole("link", { name: "Platform & services" })
      .click();
    await expect(
      page.frameLocator("iframe").locator("svg [data-node-id]").first(),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  await page.goto("/architecture");
  await page.getByRole("heading", { name: "Architecture Explorer" }).waitFor();
  await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).toBeVisible();
  expect(
    await page
      .locator(":focus")
      .evaluate((e) => getComputedStyle(e).outlineStyle),
  ).not.toBe("none");
});

test("native zoom, authored route and SVG export remain usable", async ({
  page,
}) => {
  await page.goto("/architecture/platform");
  const frame = page.frameLocator("iframe");
  await frame.locator("#btn-node-finder").waitFor();
  const reset = frame.getByRole("button", { name: /Reset diagram view/ });
  const before = await reset.innerText();
  await frame.getByRole("button", { name: "Zoom in", exact: true }).click();
  expect(await reset.innerText()).not.toBe(before);
  await frame
    .getByRole("button", { name: "Export diagram", exact: true })
    .click();
  const download = page.waitForEvent("download");
  await frame.getByRole("menuitem", { name: /SVG · Dark/ }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/\.svg$/);
  await file.saveAs("../.validation-results/local-ui/v2-platform-export.svg");
});

test("secret delivery follows the real authored route", async ({ page }) => {
  await page.goto("/architecture/platform");
  const frame = page.frameLocator("iframe");
  await frame.locator("#btn-node-finder").waitFor();
  await frame
    .getByRole("button", { name: "Trace a directed route", exact: true })
    .click();
  await frame.locator("#route-probe-find").click();
  await frame.locator("#node-finder-input").fill("External Secrets");
  await frame.locator(".node-finder-result").first().click();
  await expect(frame.locator("#route-probe")).toHaveAttribute(
    "data-state",
    "target",
  );
  await frame.locator("#route-probe-find").click();
  await frame.locator("#node-finder-input").fill("auth");
  await frame.locator('.node-finder-result[data-node-id="auth"]').click();
  await expect(frame.locator("#route-probe")).toHaveAttribute(
    "data-state",
    "result",
  );
  await expect(frame.locator("#route-probe-path")).toContainText(
    "Kubernetes Secrets",
  );
  await expect(frame.locator("#route-probe-path")).toContainText(
    "External Secrets",
  );
});

test("CSP blocks network access and direct data assets do not execute HTML", async ({
  page,
  context,
}) => {
  const requests: string[] = [];
  page.on("request", (r) => {
    if (r.url().startsWith("https://example.invalid")) requests.push(r.url());
  });
  await page.goto("/architecture/platform");
  const frame = page.frameLocator("iframe");
  await frame.locator("#btn-node-finder").waitFor();
  const actual = page.frames().find((f) => f.url() === "about:srcdoc")!;
  expect(
    await actual.evaluate(async () => {
      try {
        await fetch("https://example.invalid/forbidden");
        return false;
      } catch {
        return true;
      }
    }),
  ).toBe(true);
  expect(requests).toEqual([]);
  const asset = await context.newPage();
  await asset.goto(assetPaths["platform.json"]);
  expect(await asset.evaluate(() => document.contentType)).toBe(
    "application/json",
  );
  expect(await asset.locator("svg,iframe").count()).toBe(0);
  await asset.close();
});
