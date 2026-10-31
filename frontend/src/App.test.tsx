import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, it, expect, vi } from "vitest";
import { App } from "./App";
import { createDemoApi } from "./demo";
import { ApiError } from "./api";
function mount(
  path = "/",
  client = createDemoApi(),
  mode: "demo" | "local" = "demo",
) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <App mode={mode} client={client} />
    </MemoryRouter>,
  );
  return client;
}
async function enter() {
  await userEvent.click(screen.getByRole("button", { name: /Enter demo/ }));
  await screen.findByRole("heading", { name: "Shipment overview" });
}
describe("workspace", () => {
  it("protects routes until authenticated", () => {
    mount("/shipments");
    expect(
      screen.queryByRole("navigation", { name: "Main navigation" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Enter demo/ })).toBeVisible();
  });
  it("renders an overview from API data, with visible demo label", async () => {
    mount();
    await enter();
    expect(await screen.findByText("DEMO-2026-001")).toBeVisible();
    expect(screen.getByText("DEMO · SYNTHETIC DATA")).toBeVisible();
    expect(screen.getByText("In transit · current page")).toBeVisible();
  });
  it("navigates, filters and opens shipment details and history", async () => {
    mount();
    await enter();
    await userEvent.click(screen.getByRole("link", { name: /Shipments/ }));
    await screen.findByRole("heading", { name: "Shipments" });
    await userEvent.selectOptions(
      screen.getByLabelText("Filter status"),
      "IN_TRANSIT",
    );
    await waitFor(() =>
      expect(screen.queryByText("DEMO-2026-002")).not.toBeInTheDocument(),
    );
    await userEvent.click(await screen.findByText("DEMO-2026-001"));
    expect(
      await screen.findByRole("heading", { name: "DEMO-2026-001" }),
    ).toBeVisible();
    expect(await screen.findByText("Regional hub")).toBeVisible();
  });
  it("creates and reads a shipment only after confirmation", async () => {
    mount();
    await enter();
    await userEvent.click(
      screen.getByRole("link", { name: /Create shipment/ }),
    );
    await userEvent.type(screen.getByLabelText("Origin *"), "Heredia");
    await userEvent.type(screen.getByLabelText("Destination *"), "Cartago");
    await userEvent.type(screen.getByLabelText("Weight (kg) *"), "1.5");
    await userEvent.click(
      screen.getByRole("button", { name: "Create shipment →" }),
    );
    expect(
      await screen.findByRole("heading", {
        name: "Awaiting first tracking update",
      }),
    ).toBeVisible();
    expect(screen.getByText("1.5 kg")).toBeVisible();
  });
  it("does not submit invalid data", async () => {
    const api = mount("/shipments/new");
    const create = vi.spyOn(api, "create");
    await userEvent.click(screen.getByRole("button", { name: /Enter demo/ }));
    fireEvent.submit(
      screen
        .getByRole("button", { name: "Create shipment →" })
        .closest("form")!,
    );
    expect(await screen.findByRole("alert")).toBeVisible();
    expect(create).not.toHaveBeenCalled();
  });
  it("shows backend creation failure without a success navigation", async () => {
    const api = mount("/shipments/new");
    vi.spyOn(api, "create").mockRejectedValue(
      new ApiError(409, "Conflicting shipment"),
    );
    await userEvent.click(screen.getByRole("button", { name: /Enter demo/ }));
    await userEvent.type(screen.getByLabelText("Origin *"), "A");
    await userEvent.type(screen.getByLabelText("Destination *"), "B");
    await userEvent.type(screen.getByLabelText("Weight (kg) *"), "1");
    await userEvent.click(
      screen.getByRole("button", { name: "Create shipment →" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Conflicting");
    expect(
      screen.getByRole("heading", { name: "Start a new journey" }),
    ).toBeVisible();
  });
  it("searches tracking, and reports a missing number", async () => {
    mount();
    await enter();
    await userEvent.click(screen.getByRole("link", { name: /^⌁ Tracking/ }));
    await userEvent.type(screen.getByLabelText("Tracking number"), "missing");
    await userEvent.click(
      screen.getByRole("button", { name: /Find shipment/ }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("not found");
  });
  it("shows useful empty states", async () => {
    const api = mount();
    vi.spyOn(api, "list").mockResolvedValue({
      items: [],
      pageNumber: 1,
      pageSize: 20,
      totalCount: 0,
    });
    await enter();
    expect(await screen.findByText("No shipments yet")).toBeVisible();
  });
  it("clears session on logout", async () => {
    mount();
    await enter();
    await userEvent.click(screen.getByRole("button", { name: /Sign out/ }));
    expect(screen.getByText("You have signed out.")).toBeVisible();
    expect(
      screen.queryByRole("navigation", { name: "Main navigation" }),
    ).not.toBeInTheDocument();
  });
  it("handles invalid login without starting a session", async () => {
    const api = createDemoApi();
    vi.spyOn(api, "login").mockRejectedValue(
      new ApiError(401, "Invalid credentials"),
    );
    mount("/", api, "local");
    await userEvent.type(
      screen.getByLabelText("Email"),
      "user@example.invalid",
    );
    await userEvent.type(screen.getByLabelText("Password"), "bad");
    await userEvent.click(screen.getByRole("button", { name: "Sign in →" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Invalid credentials",
    );
    expect(
      screen.queryByRole("navigation", { name: "Main navigation" }),
    ).not.toBeInTheDocument();
  });
  it("accepts valid local login without a DEMO banner", async () => {
    mount("/", createDemoApi(), "local");
    await userEvent.type(
      screen.getByLabelText("Email"),
      "user@example.invalid",
    );
    await userEvent.type(screen.getByLabelText("Password"), "valid");
    await userEvent.click(screen.getByRole("button", { name: "Sign in →" }));
    await screen.findByRole("heading", { name: "Shipment overview" });
    expect(screen.queryByText(/DEMO — Synthetic/)).not.toBeInTheDocument();
  });
  it("rejects a token already expired at login", async () => {
    const api = mount();
    vi.spyOn(api, "login").mockResolvedValue({
      accessToken: "expired",
      accessTokenExpiresAt: "2000-01-01T00:00:00Z",
      refreshToken: "",
      refreshTokenExpiresAt: "2000-01-01T00:00:00Z",
    });
    await userEvent.click(screen.getByRole("button", { name: /Enter demo/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("expired");
    expect(
      screen.queryByRole("navigation", { name: "Main navigation" }),
    ).not.toBeInTheDocument();
  });
});

describe("session lifecycle and paginated contracts", () => {
  it("expires an active memory session and protects routes again", async () => {
    const api = createDemoApi();
    const login = api.login.bind(api);
    vi.spyOn(api, "login").mockImplementation(async (e, p) => ({
      ...(await login(e, p)),
      accessTokenExpiresAt: new Date(Date.now() + 700).toISOString(),
    }));
    mount("/", api);
    await enter();
    expect(
      await screen.findByText(
        "Your session expired. Please sign in again.",
        {},
        { timeout: 2000 },
      ),
    ).toBeVisible();
    expect(
      screen.queryByRole("navigation", { name: "Main navigation" }),
    ).not.toBeInTheDocument();
  });
  it("requests the next page instead of pretending the first page is complete", async () => {
    const api = mount("/shipments");
    const list = vi.spyOn(api, "list").mockImplementation(async (page = 1) => ({
      items: [],
      pageNumber: page,
      pageSize: 20,
      totalCount: 41,
    }));
    await userEvent.click(screen.getByRole("button", { name: /Enter demo/ }));
    await userEvent.click(await screen.findByRole("button", { name: "Next" }));
    await waitFor(() => expect(list).toHaveBeenCalledWith(2, ""));
    expect(await screen.findByText("41 shipments · Page 2")).toBeVisible();
  });
  it("uses the existing Auth registration contract before logging in", async () => {
    const api = createDemoApi();
    const register = vi
      .spyOn(api, "register")
      .mockResolvedValue({ userId: "local" });
    mount("/", api, "local");
    await userEvent.click(
      screen.getByRole("button", { name: "New here? Create an account" }),
    );
    await userEvent.type(screen.getByLabelText("First name"), "Local");
    await userEvent.type(screen.getByLabelText("Last name"), "User");
    await userEvent.type(
      screen.getByLabelText("Email"),
      "local@example.invalid",
    );
    await userEvent.type(screen.getByLabelText("Password"), "Example1!");
    await userEvent.click(
      screen.getByRole("button", { name: "Create account →" }),
    );
    await screen.findByRole("heading", { name: "Shipment overview" });
    expect(register).toHaveBeenCalledWith({
      email: "local@example.invalid",
      password: "Example1!",
      firstName: "Local",
      lastName: "User",
    });
  });
});

describe("V2 product refinements", () => {
  it("prevents concurrent duplicate submissions without assuming server idempotency", async () => {
    const api = mount("/demo/shipments/new");
    let resolveCreate:
      ((value: Awaited<ReturnType<typeof api.create>>) => void) | undefined;
    const original = api.create.bind(api);
    const create = vi.spyOn(api, "create").mockImplementation(
      () =>
        new Promise((r) => {
          resolveCreate = r;
        }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Enter demo workspace →" }),
    );
    await userEvent.type(screen.getByLabelText("Origin *"), "A");
    await userEvent.type(screen.getByLabelText("Destination *"), "B");
    await userEvent.type(screen.getByLabelText("Weight (kg) *"), "1");
    const form = screen
      .getByRole("button", { name: "Create shipment →" })
      .closest("form")!;
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(create).toHaveBeenCalledTimes(1);
    resolveCreate?.(
      await original({
        customerId: "10000000-0000-4000-8000-000000000001",
        origin: "A",
        destination: "B",
        weight: 1,
      }),
    );
    await screen.findByRole("heading", {
      name: "Awaiting first tracking update",
    });
  });
  it("offers synthetic tracking examples only in DEMO", async () => {
    mount("/demo/tracking");
    await userEvent.click(
      screen.getByRole("button", { name: "Enter demo workspace →" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "DEMO-2026-002" }),
    );
    expect(await screen.findByText("Regional hub")).toBeVisible();
  });
  it("does not offer synthetic examples in LOCAL API", async () => {
    mount("/demo/tracking", createDemoApi(), "local");
    await userEvent.type(
      screen.getByLabelText("Email"),
      "user@example.invalid",
    );
    await userEvent.type(screen.getByLabelText("Password"), "valid");
    await userEvent.click(screen.getByRole("button", { name: "Sign in →" }));
    expect(
      screen.queryByRole("button", { name: "DEMO-2026-002" }),
    ).not.toBeInTheDocument();
  });
});
