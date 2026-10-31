import { test, expect } from "@playwright/test";
import { randomBytes } from "node:crypto";
test("local API: registration, login, create, persist, tracking, logout and reload", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page
    .getByRole("button", { name: "New here? Create an account" })
    .click();
  await page.getByLabel("First name").fill("Jordan");
  await page.getByLabel("Last name").fill("Morgan");
  const email =
    "browser-" + randomBytes(8).toString("hex") + "@example.invalid";
  const password = randomBytes(16).toString("hex") + "Aa1!";
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Create account →", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Shipment overview" }),
  ).toBeVisible();
  await expect(page.getByText("No shipments yet")).toBeVisible();
  await page.screenshot({
    path: "../.validation-results/local-ui/local-empty.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "＋ Create shipment" }).click();
  await page.getByLabel("Origin *").fill("San José, CR");
  await page.getByLabel("Destination *").fill("Cartago, CR");
  await page.getByLabel("Weight (kg) *").fill("2.75");
  await page.getByLabel("Reference number").fill("BROWSER-LOCAL");
  await page.getByRole("button", { name: "Create shipment →" }).click();
  await expect(
    page.getByRole("heading", { name: "Awaiting first tracking update" }),
  ).toBeVisible();
  await page.screenshot({
    path: "../.validation-results/local-ui/local-detail.png",
    fullPage: true,
  });
  const number = await page.getByRole("heading", { level: 1 }).innerText();
  await page.getByRole("link", { name: "⌁ Tracking", exact: true }).click();
  await page.getByLabel("Tracking number").fill(number);
  await page.getByRole("button", { name: "Find shipment →" }).click();
  await expect(
    page.getByRole("heading", { name: "Awaiting first tracking update" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "▱ Shipments", exact: true }).click();
  await expect(page.getByText(number, { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "Sign in →" })).toBeVisible();
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in →" }).click();
  await expect(page.getByText(number, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Sign out ↗" }).click();
  await expect(page.getByText("You have signed out.")).toBeVisible();
  expect(errors).toEqual([]);
});
test("local API: invalid credentials and disconnected service are visible", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByLabel("Email", { exact: true })
    .fill("missing@example.invalid");
  await page.getByLabel("Password", { exact: true }).fill("incorrect");
  await page.getByRole("button", { name: "Sign in →" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Email or password is incorrect.",
  );
  await page.route("**/api/auth/login", (route) => route.abort());
  await page.getByRole("button", { name: "Sign in →" }).click();
  await expect(page.getByRole("alert")).toContainText("Cannot reach");
});
