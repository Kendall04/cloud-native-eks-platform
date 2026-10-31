import { test, expect } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { diagrams } from "../src/architecture/catalog";

const output =
  process.env.ARCHITECTURE_CAPTURE_DIR ??
  "../.validation-results/archify-final/browser";
for (const width of [1920, 1366, 820, 390]) {
  for (const diagram of diagrams) {
    test(`${diagram.id}: readable guided tour and accessible SVG at ${width}px`, async ({
      page,
    }) => {
      await mkdir(output, { recursive: true });
      await page.setViewportSize({
        width,
        height:
          width === 1920
            ? 1080
            : width === 1366
              ? 768
              : width === 820
                ? 1180
                : 844,
      });
      const external: string[] = [];
      page.on("request", (request) => {
        const url = new URL(request.url());
        if (
          url.protocol.startsWith("http") &&
          !["127.0.0.1", "localhost"].includes(url.hostname)
        )
          external.push(url.origin);
      });
      await page.goto(`/architecture/${diagram.id}`);
      const frame = page.frameLocator("iframe");
      await frame.locator("[data-view=reset]").waitFor();
      await expect(frame.locator(".diagram-container > svg")).toHaveAttribute(
        "role",
        "group",
      );
      await page
        .locator(".diagram-viewer")
        .screenshot({ path: `${output}/${diagram.id}-${width}-overview.png` });
      await page
        .getByRole("button", { name: "Start guided tour", exact: true })
        .click();
      const selected = frame.locator("[data-node-id][aria-pressed=true]");
      await expect(selected).toHaveCount(1);
      await expect(page.locator(".reader-detail h2")).toContainText("Step 1 /");
      await expect(page.locator(".reader-detail h2")).toContainText(
        "Component:",
      );
      const sizes = await selected.locator("text").evaluateAll((texts) =>
        texts.map((element) => {
          const text = element as SVGTextElement;
          return {
            label: text.textContent,
            px:
              parseFloat(getComputedStyle(text).fontSize) *
              Math.abs(text.getScreenCTM()!.a),
          };
        }),
      );
      expect(sizes.length).toBeGreaterThanOrEqual(2);
      expect(sizes[0].px).toBeGreaterThanOrEqual(12);
      for (const auxiliary of sizes.slice(1))
        expect(auxiliary.px).toBeGreaterThanOrEqual(10);
      expect(
        await page
          .locator(".reader-detail h2")
          .evaluate((element) =>
            parseFloat(getComputedStyle(element).fontSize),
          ),
      ).toBeGreaterThanOrEqual(18);
      await page
        .locator(".diagram-viewer")
        .screenshot({ path: `${output}/${diagram.id}-${width}-reading.png` });
      await page
        .getByRole("button", { name: "Next component", exact: true })
        .focus();
      await page.keyboard.press("Enter");
      await expect(page.locator(".reader-detail h2")).toContainText("2 /");
      await page
        .getByRole("button", { name: "Previous component", exact: true })
        .focus();
      await page.keyboard.press("Space");
      await expect(page.locator(".reader-detail h2")).toContainText("1 /");
      // Every tour stop must be visible, not merely have a large computed font.
      // This catches the native passport covering a selected node on mobile.
      const tour = page.getByRole("combobox", { name: /Reading tour/ });
      await expect(tour).toBeVisible();
      const tourValues = await tour
        .locator("option")
        .evaluateAll((options) =>
          options.map((item) => (item as HTMLOptionElement).value),
        );
      const visited: string[] = [];
      expect(tourValues.length).toBeGreaterThan(0);
      for (const value of tourValues) {
        await tour.selectOption(value);
        await page
          .getByRole("button", {
            name: "Focus selected component",
            exact: true,
          })
          .click();
        const total = Number(
          (await page.locator(".reader-detail h2").textContent())!.match(
            /\/ (\d+)/,
          )![1],
        );
        expect(total).toBeGreaterThan(0);
        for (let ordinal = 0; ordinal < total; ordinal++) {
          await expect
            .poll(
              async () =>
                selected.evaluate((element) => {
                  const node = element.getBoundingClientRect();
                  const passport = document
                    .querySelector("#focus-chip")!
                    .getBoundingClientRect();
                  const nav = document
                    .querySelector(".diagram-nav")!
                    .getBoundingClientRect();
                  const overlaps =
                    node.left < passport.right &&
                    node.right > passport.left &&
                    node.top < passport.bottom &&
                    node.bottom > passport.top;
                  const texts = [...element.querySelectorAll("text")].map(
                    (text) =>
                      parseFloat(getComputedStyle(text).fontSize) *
                      Math.abs(text.getScreenCTM()!.a),
                  );
                  return (
                    !overlaps &&
                    node.left >= 0 &&
                    node.right <= innerWidth &&
                    node.top >= 58 &&
                    node.bottom < nav.top &&
                    texts[0] >= 12 &&
                    texts.slice(1).every((px) => px >= 10)
                  );
                }),
              {
                message: `${diagram.id} tour ${value}: visible, unobscured reading-size component`,
              },
            )
            .toBe(true);
          visited.push((await selected.getAttribute("data-node-id"))!);
          const next = page.getByRole("button", {
            name: "Next component",
            exact: true,
          });
          if (ordinal === total - 1) {
            await expect(next).toBeDisabled();
            break;
          }
          const previous = await page
            .locator(".reader-detail h2")
            .textContent();
          await next.click();
          await expect(page.locator(".reader-detail h2")).not.toHaveText(
            previous!,
          );
        }
      }
      expect(new Set(visited).size).toBeGreaterThanOrEqual(8);
      await page
        .getByText("Complete text alternative, sources and evidence", {
          exact: true,
        })
        .click();
      await expect(page.locator(".diagram-transcript")).toContainText(
        "DECLARED",
      );
      await expect(page.locator(".diagram-transcript")).toContainText("PROVEN");
      await expect(page.locator(".diagram-transcript")).toContainText(
        "Source:",
      );
      // The opaque iframe is audited directly, without removing its sandbox or
      // disabling nested-interactive (or any other axe rule).
      let violations: unknown[] = [];
      if (width === 1920 || width === 390) {
        const inner = page
          .frames()
          .find((item) => item.url() === "about:srcdoc")!;
        if (diagram.id === "event-processing" && width === 1920) {
          await inner.evaluate(() => {
            document.documentElement.setAttribute("data-theme", "light");
          });
          await expect(
            frame
              .locator(
                '.relationship-lens-row[data-direction="out"] .relationship-lens-direction',
              )
              .first(),
          ).toHaveCSS("color", "rgb(14, 116, 144)");
        }
        await inner.addScriptTag({
          content: await readFile("node_modules/axe-core/axe.min.js", "utf8"),
        });
        violations = await inner.evaluate(async () => {
          const runtime = window as unknown as {
            axe: {
              run(
                root: Document,
                options: unknown,
              ): Promise<{ violations: unknown[] }>;
            };
          };
          return (
            await runtime.axe.run(document, {
              runOnly: {
                type: "tag",
                values: ["wcag2a", "wcag2aa", "wcag21aa"],
              },
            })
          ).violations;
        });
        expect(violations).toEqual([]);
      }
      expect(external).toEqual([]);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await writeFile(
        `${output}/${diagram.id}-${width}.json`,
        JSON.stringify({ sizes, visited, violations, external }, null, 2),
      );
    });
  }
}

test("historical lifecycle bookmark has an explicit transition and one security route", async ({
  page,
}) => {
  await page.goto("/architecture/lifecycle");
  await expect(
    page.getByRole("heading", {
      name: "Infrastructure Lifecycle — historical diagram",
    }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Continue to Security & Trust Boundaries →" })
    .click();
  await expect(page).toHaveURL(/\/architecture\/security$/);
  await expect(
    page.getByRole("heading", {
      name: "Security & Trust Boundaries",
      exact: true,
    }),
  ).toHaveCount(1);
});
