import { test, expect, type Page } from "@playwright/test";
import type { Profile } from "../src/contracts";

// Synthetic HTTP responses on loopback. No gateway, AWS identity or backend needed.
const bearer = "synthetic-memory-access-token";
const refresh = "synthetic-unused-refresh-token";
const profile = {
  userId: "10000000-0000-4000-8000-000000000001",
  email: "browser@example.invalid",
  userName: "browser-fixture",
  firstName: "Browser",
  lastName: "Fixture",
  roles: ["USER"],
  isActive: true,
  createdAt: "2026-10-01T08:00:00Z",
} satisfies Profile;
const emptyPage = { items: [], pageNumber: 1, pageSize: 20, totalCount: 0 };

async function fixture(page: Page) {
  const preview = new URL(test.info().project.use.baseURL!);
  if (
    preview.protocol !== "http:" ||
    !["127.0.0.1", "localhost"].includes(preview.hostname)
  )
    throw new Error("The AWS-mode fixture requires an HTTP loopback preview");
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    // A misconfigured build must never turn this local gate into an external call.
    if (url.origin !== preview.origin)
      throw new Error("Unexpected external browser request");
    if (!url.pathname.startsWith("/api/")) return route.continue();
    if (url.pathname === "/api/auth/login")
      return route.fulfill({
        json: {
          accessToken: bearer,
          accessTokenExpiresAt: new Date(Date.now() + 60000).toISOString(),
          refreshToken: refresh,
          refreshTokenExpiresAt: new Date(Date.now() + 120000).toISOString(),
        },
      });
    expect(route.request().headers().authorization).toBe(`Bearer ${bearer}`);
    if (url.pathname === "/api/auth/me")
      return route.fulfill({ json: profile });
    if (url.pathname === "/api/shipments")
      return route.fulfill({ json: emptyPage });
    throw new Error("Unexpected API route in synthetic fixture");
  });
}

async function signIn(page: Page) {
  await page.getByLabel("Email", { exact: true }).fill(profile.email);
  await page.getByLabel("Password", { exact: true }).fill("synthetic-input");
  await page.getByRole("button", { name: /^Sign in/ }).click();
}

test.beforeEach(async ({ page }) => {
  await fixture(page);
  await page.goto("/demo");
  await expect(page.getByText("AWS API", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Enter demo/ })).toHaveCount(0);
});

test("AWS static build uses same-origin HTTP and loses its memory session on reload", async ({
  page,
}) => {
  const authCalls: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/auth/"))
      authCalls.push(new URL(request.url()).pathname);
  });
  await signIn(page);
  await expect(
    page.getByText("No shipments yet", { exact: true }),
  ).toBeVisible();
  expect(authCalls).toEqual(["/api/auth/login", "/api/auth/me"]);
  expect(
    await page.evaluate(() => ({ ...localStorage, ...sessionStorage })),
  ).toEqual({});
  expect(await page.context().cookies()).toEqual([]);
  await expect(page.getByText(/DEMO.*SYNTHETIC|LOCAL API/)).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("button", { name: /^Sign in/ })).toBeVisible();
  expect(authCalls).toHaveLength(2);
  await signIn(page);
  await page.getByRole("button", { name: /^Sign out/ }).click();
  await expect(page.getByText("You have signed out.")).toBeVisible();
  await expect(page.getByText("AWS API", { exact: true })).toBeVisible();
});

test("AWS 401 clears the session; the next login carries no old bearer", async ({
  page,
}) => {
  await signIn(page);
  await expect(
    page.getByText("No shipments yet", { exact: true }),
  ).toBeVisible();
  await page.route("**/api/shipments?**", (route) =>
    route.fulfill({ status: 401, json: {} }),
  );
  await page.getByRole("link", { name: /Shipments/ }).click();
  await expect(
    page.getByText("Your session expired. Please sign in again."),
  ).toBeVisible();
  const loginRequest = page.waitForRequest("**/api/auth/login");
  await signIn(page);
  expect((await loginRequest).headers().authorization).toBeUndefined();
});

test("unavailable AWS API stays visibly AWS and never creates demo shipments", async ({
  page,
}) => {
  await page.route("**/api/shipments?**", (route) =>
    route.fulfill({ status: 503, json: { privateDetail: "not displayed" } }),
  );
  await signIn(page);
  await expect(page.getByRole("alert")).toContainText(
    "A required service is unavailable.",
  );
  await expect(page.getByText("AWS API", { exact: true })).toBeVisible();
  await expect(page.getByText(/DEMO-2026|not displayed|LOCAL API/)).toHaveCount(
    0,
  );
});

test("an unavailable current profile fails closed after login", async ({
  page,
}) => {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({ status: 503, json: {} }),
  );
  await signIn(page);
  await expect(page.getByRole("alert")).toContainText(
    "A required service is unavailable.",
  );
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toHaveCount(0);
  await expect(page.getByText("AWS API", { exact: true })).toBeVisible();
});

test("offline and malformed AWS login responses stay errors; Explorer remains public", async ({
  page,
}) => {
  await page.route("**/api/auth/login", (route) => route.abort());
  await signIn(page);
  await expect(page.getByRole("alert")).toContainText(
    "Cannot reach the backend.",
  );
  await page.route("**/api/auth/login", (route) =>
    route.fulfill({ contentType: "text/html", body: "<html>not JSON</html>" }),
  );
  await signIn(page);
  await expect(page.getByRole("alert")).toContainText("invalid response");
  await page.getByRole("link", { name: "Architecture Explorer" }).click();
  await expect(page).toHaveURL(/\/architecture$/);
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toHaveCount(0);
  await page.getByRole("link", { name: "Logistics Demo" }).click();
  await expect(page.getByRole("button", { name: /^Sign in/ })).toBeVisible();
  await expect(page.getByText("AWS API", { exact: true })).toBeVisible();
});
