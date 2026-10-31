import { test, expect } from "@playwright/test";
test("DEMO is isolated, navigable and responsive with no API traffic", async ({
  page,
}) => {
  const apiRequests: string[] = [];
  const errors: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/")) apiRequests.push(r.url());
  });
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(page.getByText("DEMO · SYNTHETIC DATA")).toBeVisible();
  await page.getByRole("button", { name: "Enter demo workspace →" }).click();
  await expect(page.getByText("DEMO-2026-001", { exact: true })).toBeVisible();
  await expect(page.getByText("DEMO · SYNTHETIC DATA")).toBeVisible();
  await page.screenshot({
    path: "../.validation-results/local-ui/demo-overview.png",
    fullPage: true,
  });
  await page.getByText("DEMO-2026-001", { exact: true }).click();
  await expect(page.getByText("Regional hub")).toBeVisible();
  await page.screenshot({
    path: "../.validation-results/local-ui/demo-timeline.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "▱ Shipments", exact: true }).click();
  await page.getByLabel("Filter status").selectOption("DELIVERED");
  await expect(page.getByText("DEMO-2026-002", { exact: true })).toBeVisible();
  await expect(
    page.getByText("DEMO-2026-001", { exact: true }),
  ).not.toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("link", { name: "▦ Overview", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Shipment overview" }),
  ).toBeVisible();
  await page.screenshot({
    path: "../.validation-results/local-ui/demo-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("link", { name: "＋ Create shipment" }).click();
  await page.getByLabel("Origin *").fill("Demo origin");
  await page.getByLabel("Destination *").fill("Demo destination");
  await page.getByLabel("Weight (kg) *").fill("3");
  await page.getByRole("button", { name: "Create shipment →" }).click();
  await expect(
    page.getByRole("heading", { name: "Awaiting first tracking update" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Enter demo workspace →" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Enter demo workspace →" }).click();
  await expect(
    page.getByText("Demo origin", { exact: true }),
  ).not.toBeVisible();
  expect(apiRequests).toEqual([]);
  expect(errors).toEqual([]);
});
