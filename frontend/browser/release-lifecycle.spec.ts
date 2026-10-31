// LOCAL_SIMULATED: loopback immutable static releases and intercepted synthetic APIs.
import { test, expect, type Page, type BrowserContext } from "@playwright/test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createServer, type Server } from "node:http";
import { resolve, sep } from "node:path";

type Release = {
  version: string;
  mode: string;
  sourceAppSha256: string;
  isolatedSourceOverlay: boolean;
  artifactSha256: string;
  buildReceiptSha256: string;
  files: Record<string, { sha256: string; bytes: number }>;
};
const root = resolve(
  process.cwd(),
  "../.validation-results/frontend-release-lifecycle",
);
const index = JSON.parse(readFileSync(resolve(root, "releases.json"), "utf8"));
const attempt = process.env.UI_RELEASE_ATTEMPT ?? "attempt1";
assert.match(attempt, /^attempt[1-9][0-9]*$/);
const evidence = resolve(root, attempt);
assert.equal(index.classification, "LOCAL_SIMULATED");
const releases: Record<string, Release> = index.releases;
const sha = (value: Buffer) => createHash("sha256").update(value).digest("hex");
let active = "a";
let origin = "";
let server: Server;
const served: { release: string; path: string; sha256: string }[] = [];
const records: Record<string, unknown>[] = [];
let apiReachedServer = 0;
test.setTimeout(60000);

test.beforeAll(async () => {
  assert.ok(
    !existsSync(resolve(evidence, "browser-receipt.json")),
    "Preserve previous attempt evidence",
  );
  mkdirSync(evidence, { recursive: true });
  assert.notEqual(releases.a.sourceAppSha256, releases.b.sourceAppSha256);
  assert.notEqual(releases.a.artifactSha256, releases.b.artifactSha256);
  for (const [id, release] of Object.entries(releases)) {
    const receipt = readFileSync(resolve(root, id, "frontend-build.json"));
    assert.equal(sha(receipt), release.buildReceiptSha256);
    assert.equal(
      sha(readFileSync(resolve(root, `${id}.tgz`))),
      release.artifactSha256,
    );
    for (const [path, expected] of Object.entries(release.files)) {
      const bytes = readFileSync(resolve(root, id, path));
      assert.equal(bytes.length, expected.bytes);
      assert.equal(sha(bytes), expected.sha256);
    }
  }
  server = createServer((request, response) => {
    try {
      const url = new URL(request.url!, "http://127.0.0.1");
      if (url.pathname.startsWith("/api/")) {
        apiReachedServer++;
        response.writeHead(503, { "Cache-Control": "no-store" }).end();
        return;
      }
      const path =
        url.pathname.startsWith("/assets/") ||
        url.pathname.startsWith("/architecture-assets/")
          ? decodeURIComponent(url.pathname.slice(1))
          : "index.html";
      const directory = resolve(root, active);
      const file = resolve(directory, path);
      assert.ok(file.startsWith(directory + sep));
      const release = releases[active];
      const expected = release.files[path];
      assert.ok(expected, "Unknown fixture asset");
      const bytes = readFileSync(file);
      assert.equal(sha(bytes), expected.sha256, "Changed fixture file");
      served.push({ release: active, path, sha256: sha(bytes) });
      response
        .writeHead(200, {
          "Content-Type": path.endsWith(".html")
            ? "text/html"
            : path.endsWith(".js")
              ? "application/javascript"
              : path.endsWith(".css")
                ? "text/css"
                : "application/json",
          "Cache-Control": "no-store",
          "X-Content-Type-Options": "nosniff",
          "X-Local-Simulated-Release": release.version,
        })
        .end(bytes);
    } catch {
      response.writeHead(404, { "Cache-Control": "no-store" }).end();
    }
  });
  await new Promise<void>((done) => server.listen(0, "127.0.0.1", done));
  const address = server.address();
  assert.ok(address && typeof address === "object");
  origin = `http://127.0.0.1:${address.port}`;
});

test.afterAll(async () => {
  if (server?.listening) {
    await new Promise<void>((done, reject) => {
      server.close((error) => (error ? reject(error) : done()));
      server.closeIdleConnections();
    });
  }
  writeFileSync(
    resolve(evidence, "browser-receipt.json"),
    JSON.stringify(
      {
        classification: "LOCAL_SIMULATED",
        finishedUtc: new Date().toISOString(),
        realCloudFrontOrBackendAuthentication: false,
        personalChromeSessionsUsed: false,
        forcedPidCleanup: false,
        serverClosed: !server?.listening,
        apiReachedServer,
        records,
        releaseIdentities: Object.fromEntries(
          Object.entries(releases).map(([id, r]) => [
            id,
            {
              version: r.version,
              sourceAppSha256: r.sourceAppSha256,
              isolatedSourceOverlay: r.isolatedSourceOverlay,
              artifactSha256: r.artifactSha256,
            },
          ]),
        ),
        served,
        limitations: [
          index.sourceVariantLimit,
          "Old loaded AWS page keeps its mode until explicit full navigation; no hot-switch or heap-forensics claim.",
          "No CDN propagation, real credentials, production data or remote promotion was exercised.",
        ],
      },
      null,
      2,
    ) + "\n",
  );
  expect(apiReachedServer).toBe(0);
});

async function session(context: BrowserContext) {
  let unavailable = false;
  let token = "";
  let issued = 0;
  const calls: { path: string; status: number; bearerPresent: boolean }[] = [];
  await context.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    assert.equal(url.origin, origin, "External browser request prohibited");
    if (!url.pathname.startsWith("/api/")) return route.continue();
    const authorization = request.headers().authorization;
    const status = unavailable ? 503 : 200;
    calls.push({
      path: url.pathname,
      status,
      bearerPresent: authorization !== undefined,
    });
    if (unavailable)
      return route.fulfill({
        status,
        headers: { "Cache-Control": "no-store" },
        json: {},
      });
    let json;
    if (url.pathname === "/api/auth/login") {
      expect(authorization).toBeUndefined();
      token = `local-simulated-memory-${++issued}`;
      json = {
        accessToken: token,
        accessTokenExpiresAt: new Date(Date.now() + 300000).toISOString(),
        refreshToken: "local-simulated-discarded-refresh",
        refreshTokenExpiresAt: new Date(Date.now() + 600000).toISOString(),
      };
    } else {
      expect(authorization).toBe(`Bearer ${token}`);
      if (url.pathname === "/api/auth/me")
        json = {
          userId: "10000000-0000-4000-8000-000000000001",
          email: "browser@example.invalid",
          userName: "local-fixture",
          firstName: "Local",
          lastName: "Fixture",
          roles: ["USER"],
          isActive: true,
          createdAt: "2026-10-01T08:00:00Z",
        };
      else if (url.pathname === "/api/shipments")
        json = { items: [], pageNumber: 1, pageSize: 20, totalCount: 0 };
      else throw new Error("Unexpected synthetic API route");
    }
    await route.fulfill({ json, headers: { "Cache-Control": "no-store" } });
  });
  await context.addInitScript(() => {
    Object.defineProperty(window, "__localDocumentNonce", {
      value: crypto.randomUUID(),
    });
  });
  return {
    calls,
    withdraw: () => {
      unavailable = true;
    },
  };
}

async function storageEmpty(page: Page, context: BrowserContext) {
  expect(
    await page.evaluate(() => ({ ...localStorage, ...sessionStorage })),
  ).toEqual({});
  expect(await context.cookies()).toEqual([]);
}

async function login(page: Page, heading = "Shipment overview") {
  await expect(page.getByText("AWS API", { exact: true })).toBeVisible();
  await page
    .getByLabel("Email", { exact: true })
    .fill("browser@example.invalid");
  await page
    .getByLabel("Password", { exact: true })
    .fill("local-synthetic-input");
  await page.getByRole("button", { name: /^Sign in/ }).click();
  await expect(
    page.getByRole("heading", { name: heading, exact: true }),
  ).toBeVisible();
}

test("LOCAL_SIMULATED continuous tab withdraws API, then explicitly loads DEMO without carrying auth", async ({
  browser,
}) => {
  active = "a";
  const context = await browser.newContext();
  const record: Record<string, unknown> = {
    scenario: "CONTINUOUS_AWS_TO_DEMO",
    startedUtc: new Date().toISOString(),
    chromeVersion: browser.version(),
    passed: false,
    contextClosed: false,
  };
  records.push(record);
  context.on("close", () => {
    record.contextClosed = true;
    record.finishedUtc = new Date().toISOString();
  });
  try {
    const synthetic = await session(context);
    const page = await context.newPage();
    await page.goto(origin + "/demo");
    await login(page);
    await storageEmpty(page, context);
    const nonce = await page.evaluate(
      () =>
        (window as unknown as { __localDocumentNonce: string })
          .__localDocumentNonce,
    );
    active = "demo";
    synthetic.withdraw();
    await page
      .getByRole("navigation", { name: "Main navigation" })
      .getByRole("link", { name: /Shipments/ })
      .click();
    await expect(page.getByRole("alert")).toContainText(
      "A required service is unavailable.",
    );
    await expect(page.getByText("AWS API", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: /Enter demo/ })).toHaveCount(
      0,
    );
    expect(
      await page.evaluate(
        () =>
          (window as unknown as { __localDocumentNonce: string })
            .__localDocumentNonce,
      ),
    ).toBe(nonce);
    expect(synthetic.calls.at(-1)).toMatchObject({
      status: 503,
      bearerPresent: true,
    });
    await page.screenshot({ path: resolve(evidence, "old-aws-tab-error.png") });
    const count = synthetic.calls.length;
    await page.reload();
    await expect(
      page.getByRole("button", { name: /Enter demo workspace/ }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () =>
          (window as unknown as { __localDocumentNonce: string })
            .__localDocumentNonce,
      ),
    ).not.toBe(nonce);
    await storageEmpty(page, context);
    await page.getByRole("button", { name: /Enter demo workspace/ }).click();
    await expect(
      page.getByText("DEMO-2026-001", { exact: true }),
    ).toBeVisible();
    await page.getByRole("link", { name: /Create shipment$/ }).click();
    await page.getByLabel("Origin *").fill("Local synthetic origin");
    await page.getByLabel("Destination *").fill("Local synthetic destination");
    await page.getByLabel("Weight (kg) *").fill("3");
    await page.getByRole("button", { name: /^Create shipment/ }).click();
    await expect(
      page.getByRole("heading", { name: "Awaiting first tracking update" }),
    ).toBeVisible();
    await page.reload();
    await page.getByRole("button", { name: /Enter demo workspace/ }).click();
    await page
      .getByRole("navigation", { name: "Main navigation" })
      .getByRole("link", { name: /Overview/ })
      .click();
    await expect(
      page.getByText("DEMO-2026-001", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("Local synthetic origin", { exact: true }),
    ).toHaveCount(0);
    expect(synthetic.calls).toHaveLength(count);
    await storageEmpty(page, context);
    await page.screenshot({
      path: resolve(evidence, "explicit-demo-synthetic.png"),
    });
    // New AWS navigation must not resurrect the old bearer, even for login.
    active = "a";
    await page.reload();
    await expect(page.getByRole("button", { name: /^Sign in/ })).toBeVisible();
    await page
      .getByLabel("Email", { exact: true })
      .fill("browser@example.invalid");
    await page
      .getByLabel("Password", { exact: true })
      .fill("local-synthetic-input");
    await page.getByRole("button", { name: /^Sign in/ }).click();
    await expect(page.getByRole("alert")).toContainText(
      "A required service is unavailable.",
    );
    expect(synthetic.calls.at(-1)).toMatchObject({
      path: "/api/auth/login",
      bearerPresent: false,
    });
    Object.assign(record, {
      passed: true,
      sameOldDocumentObserved: true,
      explicitReloadRequired: true,
      oldPageErrorNotSilentFallback: true,
      demoApiCalls: synthetic.calls.length - count - 1,
      memoryClearingEvidence:
        "Document replaced; empty stores/cookies; subsequent login carries no bearer",
      syntheticMutationResetOnReload: true,
      calls: synthetic.calls,
    });
  } finally {
    await context.close();
    record.contextClosed = true;
  }
});

test("LOCAL_SIMULATED promotes two distinct authenticated source bundles and rolls back A-B-A", async ({
  browser,
}) => {
  const context = await browser.newContext();
  const record: Record<string, unknown> = {
    scenario: "DISTINCT_SOURCE_A_B_A",
    startedUtc: new Date().toISOString(),
    chromeVersion: browser.version(),
    passed: false,
    contextClosed: false,
  };
  records.push(record);
  context.on("close", () => {
    record.contextClosed = true;
    record.finishedUtc = new Date().toISOString();
  });
  try {
    const synthetic = await session(context);
    const page = await context.newPage();
    const selected = [];
    for (const id of ["a", "b", "a"]) {
      active = id;
      const start = served.length;
      await page.goto(origin + "/demo");
      await login(
        page,
        id === "b"
          ? "Shipment overview - local source release B"
          : "Shipment overview",
      );
      await expect(
        page.getByText("No shipments yet", { exact: true }),
      ).toBeVisible();
      await storageEmpty(page, context);
      const scripts = served.slice(start).filter((s) => s.path.endsWith(".js"));
      expect(scripts.length).toBeGreaterThan(0);
      expect(
        scripts.every(
          (s) =>
            s.release === id && s.sha256 === releases[id].files[s.path].sha256,
        ),
      ).toBe(true);
      selected.push({
        release: id,
        version: releases[id].version,
        artifactSha256: releases[id].artifactSha256,
        scripts,
      });
      await page.screenshot({
        path: resolve(evidence, `source-${selected.length}-${id}.png`),
      });
    }
    expect(selected[0].scripts).toEqual(selected[2].scripts);
    expect(selected[0].scripts).not.toEqual(selected[1].scripts);
    expect(
      synthetic.calls.filter((c) => c.path === "/api/auth/login"),
    ).toHaveLength(3);
    expect(
      synthetic.calls
        .filter((c) => c.path === "/api/auth/login")
        .every((c) => !c.bearerPresent),
    ).toBe(true);
    Object.assign(record, {
      passed: true,
      selected,
      authenticatedBusinessReadsSimulated: true,
      oldBearerAbsentAfterEveryNavigation: true,
      calls: synthetic.calls,
    });
  } finally {
    await context.close();
    record.contextClosed = true;
    record.finishedUtc = new Date().toISOString();
  }
});
