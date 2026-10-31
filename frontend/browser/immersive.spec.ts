import { test, expect, type Frame } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { writeFile } from "node:fs/promises";

async function metrics(frame: Frame) {
  return frame.evaluate(() => {
    const svg = document.querySelector<SVGSVGElement>(
      ".diagram-container > svg",
    )!;
    const box = svg.getBBox(),
      matrix = svg.getScreenCTM()!;
    const bounds = {
      left: box.x * matrix.a + matrix.e,
      top: box.y * matrix.d + matrix.f,
      right: (box.x + box.width) * matrix.a + matrix.e,
      bottom: (box.y + box.height) * matrix.d + matrix.f,
    };
    const archify = (
      window as unknown as {
        Archify: {
          view: {
            state(): { scale: number; x: number; y: number; mode: string };
          };
        };
      }
    ).Archify;
    return {
      width: innerWidth,
      height: innerHeight,
      bounds,
      scale: matrix.a,
      camera: archify.view.state(),
      scrollHeight: document.documentElement.scrollHeight,
      scrollWidth: document.documentElement.scrollWidth,
      viewBox: {
        width: svg.viewBox.baseVal.width,
        height: svg.viewBox.baseVal.height,
      },
      controls: [
        ...document.querySelectorAll<HTMLButtonElement>(".diagram-nav button"),
      ]
        .filter((e) => e.getClientRects().length)
        .map((e) => ({
          name: e.getAttribute("aria-label"),
          ...e.getBoundingClientRect().toJSON(),
        })),
    };
  });
}
function expectFit(m: Awaited<ReturnType<typeof metrics>>) {
  expect(m.scale).toBeGreaterThan(0);
  expect(m.bounds.left).toBeGreaterThanOrEqual(8);
  expect(m.bounds.top).toBeGreaterThanOrEqual(8);
  expect(m.bounds.right).toBeLessThanOrEqual(m.width - 8);
  expect(m.bounds.bottom).toBeLessThanOrEqual(m.height - 8);
  expect(m.scrollWidth).toBeLessThanOrEqual(m.width);
  expect(m.scrollHeight).toBeLessThanOrEqual(m.height);
  for (const c of m.controls) {
    expect(c.left, c.name).toBeGreaterThanOrEqual(0);
    expect(c.right, c.name).toBeLessThanOrEqual(m.width);
    expect(c.bottom, c.name).toBeLessThanOrEqual(m.height);
  }
}

for (const id of [
  "platform",
  "networking",
  "event-processing",
  "private-cd",
  "security",
]) {
  test(`${id}: measured fit, width camera, resize, pan, focus and fullscreen`, async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (message) => {
      if (message.type() === "error") errors.push(message.text());
    });
    await page.setViewportSize({ width: 1680, height: 900 });
    await page.goto("/architecture/" + id);
    const controls = page.frameLocator("iframe");
    await controls.locator("[data-view=reset]").waitFor();
    const frame = page.frames().find((f) => f.url() === "about:srcdoc")!;
    await page.waitForTimeout(250);
    const initial = await metrics(frame);
    expectFit(initial);
    const outer = await page.locator("iframe").boundingBox();
    expect(outer!.width).toBeGreaterThan(1370);
    expect(outer!.height).toBeGreaterThan(690);
    expect(outer!.y).toBeLessThan(900); // Readable guided tour precedes the panoramic canvas.
    await page.screenshot({
      path: `../.validation-results/local-ui/v21-${id}-normal.png`,
      fullPage: true,
    });
    await controls
      .getByRole("button", { name: "Fit diagram width", exact: true })
      .click();
    const width = await metrics(frame);
    expect(width.camera.mode).toBe("width");
    expect(width.scale).toBeGreaterThanOrEqual(initial.scale);
    expect(width.bounds.left).toBeGreaterThanOrEqual(8);
    expect(width.bounds.right).toBeLessThan(width.width);
    await page.setViewportSize({ width: 1600, height: 920 });
    await expect
      .poll(async () => (await metrics(frame)).width)
      .not.toBe(initial.width);
    expect((await metrics(frame)).camera.mode).toBe("width");
    await controls
      .getByRole("button", { name: "Zoom in", exact: true })
      .click();
    const manual = await metrics(frame);
    expect(manual.camera.mode).toBe("manual");
    await page.setViewportSize({ width: 1620, height: 900 });
    await page.waitForTimeout(250);
    expect((await metrics(frame)).camera.scale).toBe(manual.camera.scale);
    // Physical pointer drag on the empty stage, away from nodes and controls.
    await page
      .locator(".diagram-viewer")
      .evaluate((e) => e.scrollIntoView({ block: "start" }));
    const beforePan = await metrics(frame);
    const iframeBox = (await page.locator("iframe").boundingBox())!;
    const background = await frame.evaluate(() => {
      for (let y = 85; y < innerHeight - 150; y += 25)
        for (let x = 20; x < innerWidth - 100; x += 25) {
          const target = document.elementFromPoint(x, y);
          if (
            target?.closest(".diagram-container") &&
            !target.closest(
              "[data-node-id], [data-relationship-hit-key], .diagram-nav, .focus-chip, .node-finder, .diagram-guide, .overview-map, .route-probe, .semantic-lens, .toolbar",
            )
          )
            return { x, y };
        }
      throw new Error("No empty stage area found for pointer pan");
    });
    await page.mouse.move(
      iframeBox.x + background.x,
      iframeBox.y + background.y,
    );
    await page.mouse.down();
    await page.mouse.move(
      iframeBox.x + background.x + 60,
      iframeBox.y + background.y + 50,
      { steps: 6 },
    );
    await page.mouse.up();
    const panned = await metrics(frame);
    expect(
      panned.camera.x !== beforePan.camera.x ||
        panned.camera.y !== beforePan.camera.y,
    ).toBe(true);
    await controls.locator("[data-view=reset]").click();
    await page.waitForTimeout(200);
    expectFit(await metrics(frame));
    const node = controls.locator("svg [data-node-id]").first();
    const label = (await node.getAttribute("data-node-label"))!;
    await controls
      .getByRole("button", { name: "Find a node", exact: true })
      .click();
    await controls
      .getByRole("searchbox", { name: "Search diagram nodes" })
      .fill(label);
    await controls.locator(".node-finder-result").first().click();
    await expect(node).toHaveAttribute("aria-pressed", "true");
    const theme = await controls.locator("html").getAttribute("data-theme");
    await controls.getByRole("button", { name: "Toggle color theme" }).click();
    expect(await controls.locator("html").getAttribute("data-theme")).not.toBe(
      theme,
    );
    await controls
      .getByRole("button", { name: "Zoom in", exact: true })
      .click();
    const beforeFocus = await metrics(frame);
    await page
      .getByRole("button", { name: "Expand view", exact: true })
      .click();
    await expect(page.locator(".diagram-viewer")).toHaveClass(/is-expanded/);
    await expect(node).toHaveAttribute("aria-pressed", "true");
    expect((await metrics(frame)).camera.scale).toBe(beforeFocus.camera.scale);
    await controls.locator("[data-view=reset]").click();
    await page.waitForTimeout(250);
    const focus = await metrics(frame);
    expectFit(focus);
    expect(focus.width).toBeGreaterThan(1590);
    await page.screenshot({
      path: `../.validation-results/local-ui/v21-${id}-focus.png`,
    });
    await page.getByRole("button", { name: "Fullscreen", exact: true }).click();
    await expect
      .poll(() => page.evaluate(() => !!document.fullscreenElement))
      .toBe(true);
    await page.waitForTimeout(250);
    expectFit(await metrics(frame));
    await page.screenshot({
      path: `../.validation-results/local-ui/v21-${id}-fullscreen.png`,
    });
    await controls.locator("[data-view=reset]").press("Escape");
    await expect
      .poll(() => page.evaluate(() => !!document.fullscreenElement))
      .toBe(false);
    await expect(page.locator(".diagram-viewer")).toHaveClass(/is-expanded/);
    await controls.locator("[data-view=reset]").press("Escape");
    await expect(page.locator(".diagram-viewer")).not.toHaveClass(
      /is-expanded/,
    );
    expect(await page.evaluate(() => document.body.style.overflow)).not.toBe(
      "hidden",
    );
    expect(errors).toEqual([]);
    await writeFile(
      `../.validation-results/local-ui/v21-${id}-metrics.json`,
      JSON.stringify(
        { outer, initial, width, manual, panned, focus, errors },
        null,
        2,
      ),
    );
  });
}

test("responsive fit, reachable controls and separate reading measure", async ({
  page,
}) => {
  test.setTimeout(60000);
  const measurements = [];
  for (const viewport of [
    { width: 1920, height: 1080 },
    { width: 1366, height: 768 },
    { width: 820, height: 1180 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    for (const id of [
      "platform",
      "networking",
      "event-processing",
      "private-cd",
      "security",
    ]) {
      await page.goto("/architecture/" + id);
      await page.frameLocator("iframe").locator("[data-view=reset]").waitFor();
      const frame = page.frames().find((f) => f.url() === "about:srcdoc")!;
      // Archify fits asynchronously after fonts/layout and its camera transition.
      // Wait for the actual geometry, rather than sampling a fixed 160 ms frame.
      await frame.evaluate(() => document.fonts.ready.then(() => undefined));
      await expect(async () => expectFit(await metrics(frame))).toPass({
        timeout: 5000,
        intervals: [50, 100, 250],
      });
      const m = await metrics(frame);
      expectFit(m);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      measurements.push({ id, viewport, ...m });
      if (id === "platform")
        await page.screenshot({
          path: `../.validation-results/local-ui/v21-responsive-${viewport.width}.png`,
          fullPage: true,
        });
    }
  }
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/architecture/evidence");
  const reading = (await page.locator("main").boundingBox())!;
  expect(reading.width).toBeLessThanOrEqual(1240);
  await page.goto("/architecture/platform");
  expect((await page.locator("main").boundingBox())!.width).toBeGreaterThan(
    reading.width + 300,
  );
  await writeFile(
    "../.validation-results/local-ui/v21-responsive-metrics.json",
    JSON.stringify(measurements, null, 2),
  );
});

test("mobile touch pan and orientation preserve manual exploration", async ({
  browser,
}) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });
  const page = await context.newPage();
  await page.goto(
    (process.env.UI_TEST_URL ?? "http://127.0.0.1:5173") +
      "/architecture/platform",
  );
  const controls = page.frameLocator("iframe");
  await controls.locator("[data-view=reset]").waitFor();
  await page.getByRole("button", { name: "Expand view", exact: true }).click();
  await controls.getByRole("button", { name: "Zoom in", exact: true }).click();
  await controls.getByRole("button", { name: "Zoom in", exact: true }).click();
  const frame = page.frames().find((f) => f.url() === "about:srcdoc")!;
  const before = await metrics(frame);
  const box = (await page.locator("iframe").boundingBox())!;
  const background = await frame.evaluate(() => {
    for (let y = 85; y < innerHeight - 150; y += 25)
      for (let x = 20; x < innerWidth - 75; x += 25) {
        const target = document.elementFromPoint(x, y);
        if (
          target?.closest(".diagram-container") &&
          !target.closest(
            "[data-node-id], [data-relationship-hit-key], .diagram-nav, .focus-chip, .node-finder, .diagram-guide, .overview-map, .route-probe, .semantic-lens, .toolbar",
          )
        )
          return { x, y };
      }
    throw new Error("No empty stage area found for a touch pan");
  });
  const session = await context.newCDPSession(page);
  await session.send("Input.dispatchTouchEvent", {
    type: "touchStart",
    touchPoints: [{ x: box.x + background.x, y: box.y + background.y }],
  });
  for (let i = 1; i <= 5; i++) {
    await session.send("Input.dispatchTouchEvent", {
      type: "touchMove",
      touchPoints: [
        { x: box.x + background.x + i * 10, y: box.y + background.y + i * 8 },
      ],
    });
    await page.waitForTimeout(30);
  }
  await session.send("Input.dispatchTouchEvent", {
    type: "touchEnd",
    touchPoints: [],
  });
  const after = await metrics(frame);
  expect(
    after.camera.x !== before.camera.x || after.camera.y !== before.camera.y,
  ).toBe(true);
  await page.setViewportSize({ width: 844, height: 390 });
  await page.waitForTimeout(250);
  expect((await metrics(frame)).camera.scale).toBe(after.camera.scale);
  await controls.locator("[data-view=reset]").click();
  await page.waitForTimeout(200);
  expectFit(await metrics(frame));
  await page
    .getByRole("button", { name: "Close expanded view", exact: true })
    .click();
  expect(await page.evaluate(() => document.body.style.overflow)).not.toBe(
    "hidden",
  );
  await context.close();
});

test("host accessibility, invalid messages and intact sandbox in focus", async ({
  page,
}) => {
  await page.goto("/architecture/platform");
  await page.frameLocator("iframe").locator("[data-view=reset]").waitFor();
  await page.getByRole("button", { name: "Expand view", exact: true }).click();
  const frame = page.frames().find((f) => f.url() === "about:srcdoc")!;
  await frame.evaluate(() =>
    parent.postMessage(
      { type: "archify-viewer-escape", unexpected: true },
      "*",
    ),
  );
  await expect(page.locator(".diagram-viewer")).toHaveClass(/is-expanded/);
  await expect(page.locator("iframe")).toHaveAttribute(
    "sandbox",
    "allow-scripts allow-downloads",
  );
  expect(
    await frame.evaluate(() => {
      try {
        void parent.document.body;
        return false;
      } catch {
        return true;
      }
    }),
  ).toBe(true);
  expect(
    await frame.evaluate(() => {
      try {
        void sessionStorage.length;
        return false;
      } catch {
        return true;
      }
    }),
  ).toBe(true);
  await page
    .getByRole("button", { name: "Close expanded view", exact: true })
    .click();
  // Archify is a separately reviewed interactive artifact; check the React host.
  const result = await new AxeBuilder({ page })
    .exclude("iframe")
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(result.violations).toEqual([]);
});
