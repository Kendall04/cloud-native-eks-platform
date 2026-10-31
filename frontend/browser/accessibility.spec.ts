import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
test("WCAG AA automated checks on product and editorial screens", async ({
  page,
}) => {
  for (const path of [
    "/demo",
    "/architecture",
    "/architecture/security",
    "/architecture/evidence",
  ]) {
    await page.goto(path);
    await page.locator("h1,h2").first().waitFor();
    expect(
      (
        await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze()
      ).violations,
    ).toEqual([]);
  }
  await page.goto("/demo");
  await page.getByRole("button", { name: "Enter demo workspace →" }).click();
  await page.getByRole("heading", { name: "Shipment overview" }).waitFor();
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name: "▱ Shipments", exact: true })
    .click();
  await page.getByRole("link", { name: "＋ Create shipment" }).click();
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
});
