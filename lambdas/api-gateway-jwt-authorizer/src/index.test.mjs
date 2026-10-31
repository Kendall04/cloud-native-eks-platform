import assert from "node:assert/strict";
import test from "node:test";

import { __testing } from "./index.mjs";

test("extractSecretValue accepts a plain Secrets Manager string", () => {
  assert.equal(__testing.extractSecretValue("plain-secret-value", "test secret"), "plain-secret-value");
});

test("extractSecretValue accepts a JSON value field", () => {
  assert.equal(__testing.extractSecretValue('{"value":"json-secret-value"}', "test secret"), "json-secret-value");
});

test("extractSecretValue rejects JSON without a supported string field", () => {
  assert.throws(
    () => __testing.extractSecretValue('{"unexpected":"shape"}', "test secret"),
    /did not contain a supported string field/,
  );
});

// Exercise the production signature verification and identity-context path without AWS I/O.
import crypto from "node:crypto";
const config = { issuer: "r1-test", audience: "r1-clients" };
const secrets = { jwtSecret: crypto.randomBytes(48).toString("base64"), proxySecret: "test-only-proxy" };
function token(overrides = {}, key = secrets.jwtSecret) {
  const encode = value => Buffer.from(JSON.stringify(value)).toString("base64url");
  const input = `${encode({ alg: "HS256" })}.${encode({
    sub: "test-user", roles: "USER", iss: config.issuer, aud: config.audience,
    exp: Math.floor(Date.now() / 1000) + 60, ...overrides
  })}`;
  return `${input}.${crypto.createHmac("sha256", key).update(input).digest("base64url")}`;
}
for (const roles of ["USER", ["USER", "ADMIN"]]) {
  test(`validated roles form trusted context: ${roles}`, () => {
    const result = __testing.authorizeRequest({ headers: {
      authorization: `Bearer ${token({ roles })}`,
      "X-Platform-Roles": "ADMIN", "X-Platform-Proxy-Secret": "attacker"
    } }, config, secrets);
    assert.equal(result.isAuthorized, true);
    assert.equal(result.context.roles, Array.isArray(roles) ? roles.join(",") : roles);
    assert.equal(result.context.proxySecret, secrets.proxySecret);
    assert.equal(result.context.userId, "test-user");
  });
}
test("missing token is denied even with client identity headers", () => {
  assert.equal(__testing.authorizeRequest({ headers: { "X-Platform-Roles": "ADMIN" } }, config, secrets).isAuthorized, false);
});
for (const [name, jwt] of [
  ["invalid signature", token({}, "attacker-key")],
  ["expired", token({ exp: 1 })],
  ["wrong issuer", token({ iss: "attacker" })],
  ["wrong audience", token({ aud: "attacker" })]
]) {
  test(`${name} cannot form trusted identity`, () => {
    assert.throws(() => __testing.authorizeRequest({ headers: { authorization: `Bearer ${jwt}` } }, config, secrets));
  });
}
