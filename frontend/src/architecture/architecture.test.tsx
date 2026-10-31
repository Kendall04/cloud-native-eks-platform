import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, it, expect, vi } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { App } from "../App";
import { createDemoApi } from "../demo";
import { DiagramViewer } from "./DiagramViewer";
import {
  presentationExport,
  diagramNames,
  publicEvidence,
  sha256,
} from "../../scripts/architecture-assets.mjs";
import { diagrams } from "./catalog";
import { adaptViewport } from "../../scripts/architecture-viewport.mjs";
const mount = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <App mode="local" />
    </MemoryRouter>,
  );
describe("public architecture navigation", () => {
  it.each(["demo", "aws"] as const)(
    "labels the %s edition without claiming live health",
    (mode) => {
      render(
        <MemoryRouter initialEntries={["/architecture"]}>
          <App mode={mode} />
        </MemoryRouter>,
      );
      expect(
        screen.getAllByText(
          mode === "aws" ? "AWS API EDITION" : "DEMO EDITION · SYNTHETIC DATA",
        ),
      ).toHaveLength(2);
      expect(screen.queryByText("AWS RUNTIME OFFLINE")).not.toBeInTheDocument();
      expect(screen.getByText(/does not report backend health/)).toBeVisible();
    },
  );
  it("opens without product authentication and marks the selected space", () => {
    mount("/architecture");
    expect(
      screen.getByRole("heading", { name: "Architecture Explorer" }),
    ).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Architecture Explorer" }),
    ).toHaveAttribute("aria-current", "page");
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
  });
  it("switches to protected product and back", async () => {
    mount("/architecture/evidence");
    expect(
      screen.getByRole("heading", { name: "Validation evidence" }),
    ).toBeVisible();
    await userEvent.click(screen.getByRole("link", { name: "Logistics Demo" }));
    expect(screen.getByLabelText("Password")).toBeVisible();
    await userEvent.click(
      screen.getByRole("link", { name: "Architecture Explorer" }),
    );
    expect(
      screen.getByRole("heading", { name: "Architecture Explorer" }),
    ).toBeVisible();
  });
  it("preserves product session while exploring without handing it to the viewer", async () => {
    render(
      <MemoryRouter initialEntries={["/demo"]}>
        <App mode="demo" client={createDemoApi()} />
      </MemoryRouter>,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Enter demo workspace →" }),
    );
    await screen.findByRole("heading", { name: "Shipment overview" });
    await userEvent.click(
      screen.getByRole("link", { name: "Architecture Explorer" }),
    );
    await userEvent.click(screen.getByRole("link", { name: "Logistics Demo" }));
    expect(
      await screen.findByRole("heading", { name: "Shipment overview" }),
    ).toBeVisible();
  });
  it("shows a useful architecture unknown-route page", () => {
    mount("/architecture/missing");
    expect(
      screen.getByRole("heading", { name: "Architecture page not found" }),
    ).toBeVisible();
  });
  it.each(["scaling", "evidence", "lifecycle"])(
    "supports public %s deep links",
    (path) => {
      mount("/architecture/" + path);
      expect(screen.getByRole("main")).toBeVisible();
      expect(screen.getByRole("main")).toHaveClass("reading-layout");
      expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
    },
  );
});
describe("reviewed diagram exports", () => {
  it("registers exactly the five reviewed diagrams", () => {
    expect(diagrams.map((d) => d.id)).toEqual(diagramNames);
  });
  it.each(diagramNames)(
    "%s is self-contained and stripped of repository context",
    (name) => {
      const value = presentationExport(name);
      expect(value.html).not.toContain("Kendall04");
      expect(value.html).not.toMatch(
        /<script[^>]+src=|<link[^>]+href=|<iframe|<object/i,
      );
      expect(value.html).not.toMatch(/<a[^>]+href=/i);
      expect(value.html).toContain("connect-src 'none'");
      expect(value.html).toContain("archify 3.1.0");
      expect(value.originalSha256).toHaveLength(64);
      expect(value.presentationSha256).toHaveLength(64);
      const original = readFileSync(
        resolve(process.cwd(), "../docs/interactive", name + ".html"),
        "utf8",
      );
      const svg = (html: string) =>
        new DOMParser()
          .parseFromString(html, "text/html")
          .querySelector(".diagram-container > svg")!.outerHTML;
      expect(svg(value.html)).toBe(
        svg(original).replace('role="img"', 'role="group"'),
      );
    },
  );
  it("rejects unknown artifacts", () => {
    expect(() => presentationExport("unknown")).toThrow();
  });
  it("fails closed when the renderer no longer has the reviewed viewport anchors", () => {
    expect(() => adaptViewport("<html>unreviewed renderer</html>")).toThrow(
      /anchor changed/,
    );
  });
  it.each(diagramNames)(
    "%s has one expansion owner and a native width camera",
    (name) => {
      const html = presentationExport(name).html;
      expect(html).toContain("Fit diagram width");
      expect(html).toContain("mode: 'width'");
      expect(html).toContain(
        "else if (state.mode === 'width') Archify.view.fitWidth()",
      );
      expect(html).not.toContain("} else if (e.key === 'f' || e.key === 'F')");
      expect(html).not.toContain("Archify.presentation.exit();");
    },
  );
});
describe("diagram viewer state and sandbox", () => {
  it("loads reviewed content with scripts but no same-origin access", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(Response.json(presentationExport("platform"))),
    );
    render(<DiagramViewer id="platform" title="Platform" />);
    const frame = await screen.findByTitle("Platform interactive diagram");
    expect(frame).toHaveAttribute("sandbox", "allow-scripts allow-downloads");
    expect(frame.getAttribute("sandbox")).not.toContain("allow-same-origin");
    expect(frame).toHaveAttribute("referrerpolicy", "no-referrer");
    fireEvent.load(frame);
    expect(
      screen.queryByText("Preparing interactive controls…"),
    ).not.toBeInTheDocument();
  });
  it("rejects modified presentation bytes even if its self-declared digest is changed", async () => {
    const payload = presentationExport("platform");
    payload.html += "<script>bad()</script>";
    payload.presentationSha256 = sha256(payload.html);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(payload)));
    render(<DiagramViewer id="platform" title="Platform" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("integrity");
    expect(
      screen.queryByTitle("Platform interactive diagram"),
    ).not.toBeInTheDocument();
  });
  it("shows a failed-resource error and allows retry", async () => {
    const f = vi
      .fn()
      .mockResolvedValueOnce(new Response("", { status: 404 }))
      .mockResolvedValueOnce(Response.json(presentationExport("platform")));
    vi.stubGlobal("fetch", f);
    render(<DiagramViewer id="platform" title="Platform" />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "could not be loaded",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Retry diagram" }),
    );
    expect(
      await screen.findByTitle("Platform interactive diagram"),
    ).toBeVisible();
  });
  it("expands and closes with Escape, restoring focus", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(Response.json(presentationExport("platform"))),
    );
    render(<DiagramViewer id="platform" title="Platform" />);
    await screen.findByTitle("Platform interactive diagram");
    await userEvent.click(screen.getByRole("button", { name: "Expand view" }));
    expect(
      screen.getByRole("button", { name: "Close expanded view" }),
    ).toBeVisible();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.getByRole("button", { name: "Expand view" })).toHaveFocus();
  });
  it("provides a fullscreen fallback when unsupported", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(Response.json(presentationExport("platform"))),
    );
    render(<DiagramViewer id="platform" title="Platform" />);
    await userEvent.click(screen.getByRole("button", { name: "Fullscreen" }));
    expect(
      await screen.findByText(/Native fullscreen is unavailable/),
    ).toBeVisible();
  });
  it("does not accept arbitrary parent-message senders", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(Response.json(presentationExport("platform"))),
    );
    render(<DiagramViewer id="platform" title="Platform" />);
    await userEvent.click(screen.getByRole("button", { name: "Expand view" }));
    fireEvent(
      window,
      new MessageEvent("message", {
        data: { type: "archify-viewer-escape" },
        origin: "https://untrusted.invalid",
      }),
    );
    expect(
      screen.getByRole("button", { name: "Close expanded view" }),
    ).toBeVisible();
  });
});

describe("curated evidence publication", () => {
  it("selects supported metrics without private raw records", () => {
    const evidence = publicEvidence();
    expect(evidence.security.uniqueExceptions).toBe(9);
    expect(evidence.security.severity).toEqual({ HIGH: 6, CRITICAL: 3 });
    expect(evidence.security.expiry).toEqual(["2027-01-12"]);
    expect(evidence.historicalAws.redeploy.stacks).toBe(18);
    expect(evidence.runtime.versions.sdk).toBe("10.0.402");
    expect(evidence.october24Aws.checks.C3Checks).toBe(53);
    expect(evidence.october24Aws.retirement.completedStages).toBe(39);
    expect(evidence.october24Aws.retirement.newKeyPendingDeletion).toBe(true);
    expect(evidence.october24Aws.retirement.globalInventoryComplete).toBe(
      false,
    );
    expect(evidence.latestAws.observedOn).toBe("2026-10-29");
    expect(evidence.latestAws.privateDelivery.helmRevision).toBe(4);
    expect(evidence.latestAws.networkLimits.natReplacementPrivateEgress).toBe(
      "UNVERIFIED",
    );
    expect(evidence.latestAws.networkLimits.continuousEgressProven).toBe(false);
    expect(JSON.stringify(evidence.latestAws)).not.toMatch(
      /retirement\/|fixtureUsers|fixturePassword|token|accountId|principal|endpoint|runId/,
    );
    expect(evidence.historicalAws.podEgress["us-east-1a"]).toBe("NOT_TESTED");
    expect(JSON.stringify(evidence)).not.toMatch(
      /Kendall04|arn:aws:|https:\/\/.*amazonaws/,
    );
  });
});

describe("implementation references", () => {
  it("points to existing repository paths", () => {
    for (const d of diagrams)
      for (const path of d.sources)
        expect(existsSync(resolve(process.cwd(), "..", path)), path).toBe(true);
  });
});
