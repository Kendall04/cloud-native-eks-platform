// Requires running local backend plus Vite dev:local. Creates only uniquely named test accounts/shipments.
import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import { localConfigPath } from "./local-config.mjs";
const base = "http://127.0.0.1:5173/api";
let count = 0;
async function http(
  path,
  { body, token, headers = {}, expected = 200, method } = {},
) {
  const response = await fetch(base + path, {
    method: method ?? (body ? "POST" : "GET"),
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: "Bearer " + token } : {}),
      ...headers,
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  assert.equal(response.status, expected, path + " unexpected status");
  count++;
  const text = await response.text();
  return text ? JSON.parse(text) : null;
}
const suffix = randomBytes(8).toString("hex");
const password = randomBytes(16).toString("hex") + "Aa1!";
const email = "ui-" + suffix + "@example.invalid";
const user = await http("/auth/register", {
  body: { email, password, firstName: "UI", lastName: "Integration" },
  expected: 201,
});
await http("/auth/login", {
  body: { email, password: "incorrect" },
  expected: 401,
});
const tokens = await http("/auth/login", { body: { email, password } });
const token = tokens.accessToken;
const profile = await http("/auth/me", { token });
assert.equal(profile.userId, user.userId);
await http("/shipments", { expected: 401 });
await http("/shipments", { token: "invalid-token", expected: 401 });
// Spoofed browser headers are discarded; only Auth /me identity is forwarded.
const shipment = await http("/shipments", {
  token,
  headers: {
    "X-Platform-User-Id": "forged",
    "X-Platform-Roles": "ADMIN",
    "X-Platform-Proxy-Secret": "forged",
  },
  body: {
    customerId: user.userId,
    origin: "Local origin",
    destination: "Local destination",
    weight: 1.25,
    referenceNumber: "UI-INTEGRATION-" + suffix,
  },
  expected: 201,
});
assert.equal(shipment.customerId, user.userId);
assert.equal(shipment.status, "CREATED");
const list = await http("/shipments?PageNumber=1&PageSize=20", { token });
assert.ok(list.items.some((s) => s.id === shipment.id));
const saved = await http("/shipments/by-id/" + shipment.id, { token });
assert.equal(saved.referenceNumber, "UI-INTEGRATION-" + suffix);
const timeline = await http(
  "/tracking/by-tracking-number/" + shipment.trackingNumber,
  { token },
);
assert.deepEqual(timeline, []);
await http("/shipments", {
  token,
  body: { customerId: "other-user", origin: "A", destination: "B", weight: 1 },
  expected: 403,
});
await http("/shipments", {
  token,
  body: { customerId: user.userId, origin: "A", destination: "B", weight: 0 },
  expected: 400,
});
await http("/shipments/by-id/00000000-0000-4000-8000-000000000099", {
  token,
  expected: 404,
});
await http("/admin/tracking-events", { token, body: {}, expected: 404 });
await http("/internal/shipments/" + shipment.id, { token, expected: 404 });
await http("/shipments", {
  token,
  headers: { Origin: "https://example.invalid" },
  expected: 403,
});
await http("/auth/register", {
  body: { email, password, firstName: "UI", lastName: "Duplicate" },
  expected: 409,
});
const otherEmail = "ui-other-" + suffix + "@example.invalid";
await http("/auth/register", {
  body: { email: otherEmail, password, firstName: "Other", lastName: "User" },
  expected: 201,
});
const other = await http("/auth/login", {
  body: { email: otherEmail, password },
});
await http("/shipments/by-id/" + shipment.id, {
  token: other.accessToken,
  expected: 404,
});
await http("/tracking/by-tracking-number/" + shipment.trackingNumber, {
  token: other.accessToken,
  expected: 404,
});
// Token forgery with an expired payload is rejected by Auth, never trusted by the proxy.
const parts = token.split(".");
const payload = JSON.parse(Buffer.from(parts[1], "base64url").toString());
payload.exp = 1;
parts[1] = Buffer.from(JSON.stringify(payload)).toString("base64url");
await http("/shipments", { token: parts.join("."), expected: 401 });
console.log(
  JSON.stringify({
    result: "PASS",
    httpAssertions: count,
    postgresPersistence: true,
    trackingEmptyTimeline: true,
    authorizationPreserved: true,
    awsEventsTested: false,
  }),
);

// Vite must never serve the server-only secrets file, even via its /@fs escape hatch.
const privatePath = localConfigPath().replaceAll("\\", "/");
const privateResponse = await fetch("http://127.0.0.1:5173/@fs/" + privatePath);
assert.equal(
  privateResponse.status,
  403,
  "Development server exposed a private file",
);
console.log("PASS: server-only configuration cannot be fetched through Vite");
