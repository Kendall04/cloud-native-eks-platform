import crypto from "node:crypto";

const issuer = process.env.JWT_ISSUER;
const audience = process.env.JWT_AUDIENCE;
const jwtSecretId = process.env.AUTH_SERVICE_JWT_SECRET_ID;
const proxySecretId = process.env.PLATFORM_TRUSTED_PROXY_SECRET_ID;
const secretCacheTtlMs = Number.parseInt(process.env.SECRET_CACHE_TTL_SECONDS ?? "300", 10) * 1000;

let secretsManagerClient;
let cachedSecrets;
let cachedSecretsExpiresAt = 0;

export const handler = async (event) => {
  try {
    const config = validateConfiguration();
    const secrets = await getAuthorizerSecrets(config);

    return authorizeRequest(event, config, secrets);
  } catch (error) {
    console.error("JWT authorizer denied the request", {
      message: error instanceof Error ? error.message : String(error),
      routeKey: event?.routeKey,
      requestId: event?.requestContext?.requestId,
    });

    return deny("JWT validation failed.");
  }
};

function authorizeRequest(event, config, secrets) {
  const authorizationHeader =
    event?.headers?.authorization ??
    event?.headers?.Authorization ??
    event?.headers?.AUTHORIZATION;

  if (!authorizationHeader) {
    return deny("Authorization header was missing.");
  }

  if (!authorizationHeader.startsWith("Bearer ")) {
    return deny("Authorization header did not contain a bearer token.");
  }

  const token = authorizationHeader.slice("Bearer ".length).trim();

  if (!token) {
    return deny("Bearer token was empty.");
  }

  const payload = validateToken(token, config, secrets.jwtSecret);
  const roles = extractRoles(payload);
  const userId = stringClaim(payload, "userId") ?? stringClaim(payload, "sub");
  const email = stringClaim(payload, "email") ?? "";

  if (!userId) {
    return deny("Validated token did not contain a user identifier.");
  }

  return {
    isAuthorized: true,
    context: {
      userId,
      email,
      roles: roles.join(","),
      proxySecret: secrets.proxySecret,
    },
  };
}

function validateConfiguration() {
  if (!issuer) {
    throw new Error("JWT_ISSUER is required.");
  }

  if (!audience) {
    throw new Error("JWT_AUDIENCE is required.");
  }

  if (!jwtSecretId) {
    throw new Error("AUTH_SERVICE_JWT_SECRET_ID is required.");
  }

  if (!proxySecretId) {
    throw new Error("PLATFORM_TRUSTED_PROXY_SECRET_ID is required.");
  }

  if (!Number.isFinite(secretCacheTtlMs) || secretCacheTtlMs <= 0) {
    throw new Error("SECRET_CACHE_TTL_SECONDS must be a positive integer.");
  }

  return {
    audience,
    issuer,
    jwtSecretId,
    proxySecretId,
  };
}

async function getAuthorizerSecrets(config) {
  const now = Date.now();

  if (cachedSecrets && cachedSecretsExpiresAt > now) {
    return cachedSecrets;
  }

  const [jwtSecret, proxySecret] = await Promise.all([
    getSecretString(config.jwtSecretId, "auth JWT secret"),
    getSecretString(config.proxySecretId, "trusted proxy secret"),
  ]);

  if (jwtSecret.length < 32) {
    throw new Error("Resolved auth JWT secret must be at least 32 characters long.");
  }

  if (proxySecret.length < 32) {
    throw new Error("Resolved trusted proxy secret must be at least 32 characters long.");
  }

  cachedSecrets = {
    jwtSecret,
    proxySecret,
  };
  cachedSecretsExpiresAt = now + secretCacheTtlMs;

  return cachedSecrets;
}

async function getSecretString(secretId, label) {
  const { GetSecretValueCommand } = await import("@aws-sdk/client-secrets-manager");
  const client = await getSecretsManagerClient();
  const response = await client.send(new GetSecretValueCommand({ SecretId: secretId }));

  if (typeof response.SecretString === "string" && response.SecretString.length > 0) {
    return extractSecretValue(response.SecretString, label);
  }

  if (response.SecretBinary) {
    return extractSecretValue(Buffer.from(response.SecretBinary).toString("utf8"), label);
  }

  throw new Error(`Secrets Manager returned an empty ${label}.`);
}

async function getSecretsManagerClient() {
  if (secretsManagerClient) {
    return secretsManagerClient;
  }

  const { SecretsManagerClient } = await import("@aws-sdk/client-secrets-manager");
  secretsManagerClient = new SecretsManagerClient({});
  return secretsManagerClient;
}

function extractSecretValue(rawValue, label) {
  const trimmedValue = rawValue.trim();

  if (!trimmedValue) {
    throw new Error(`Secrets Manager returned a blank ${label}.`);
  }

  if (!trimmedValue.startsWith("{")) {
    return trimmedValue;
  }

  const parsedValue = JSON.parse(trimmedValue);
  const candidate =
    parsedValue.value ??
    parsedValue.secret ??
    parsedValue.jwtSecret ??
    parsedValue.proxySecret ??
    parsedValue.AUTH_SERVICE_JWT_SECRET ??
    parsedValue.PLATFORM_TRUSTED_PROXY_SECRET;

  if (typeof candidate !== "string" || !candidate.trim()) {
    throw new Error(`Secrets Manager JSON for ${label} did not contain a supported string field.`);
  }

  return candidate.trim();
}

function validateToken(token, config, secret) {
  const segments = token.split(".");

  if (segments.length !== 3) {
    throw new Error("JWT did not contain three segments.");
  }

  const [encodedHeader, encodedPayload, encodedSignature] = segments;
  const header = JSON.parse(base64UrlDecode(encodedHeader));
  const payload = JSON.parse(base64UrlDecode(encodedPayload));

  if (header?.alg !== "HS256") {
    throw new Error(`Unsupported JWT algorithm '${header?.alg ?? "unknown"}'.`);
  }

  const signingInput = `${encodedHeader}.${encodedPayload}`;
  const expectedSignature = crypto.createHmac("sha256", secret).update(signingInput).digest();
  const actualSignature = base64UrlDecodeToBuffer(encodedSignature);

  if (
    expectedSignature.length !== actualSignature.length ||
    !crypto.timingSafeEqual(expectedSignature, actualSignature)
  ) {
    throw new Error("JWT signature validation failed.");
  }

  const now = Math.floor(Date.now() / 1000);
  const exp = numericClaim(payload, "exp");
  const nbf = numericClaim(payload, "nbf");
  const iss = stringClaim(payload, "iss");
  const aud = payload?.aud;

  if (!exp || exp <= now) {
    throw new Error("JWT has expired.");
  }

  if (nbf && nbf > now) {
    throw new Error("JWT is not valid yet.");
  }

  if (iss !== config.issuer) {
    throw new Error("JWT issuer was invalid.");
  }

  if (!matchesAudience(aud, config.audience)) {
    throw new Error("JWT audience was invalid.");
  }

  return payload;
}

function extractRoles(payload) {
  const roleClaims = [payload?.roles, payload?.role].flatMap((value) => {
    if (Array.isArray(value)) {
      return value;
    }

    if (typeof value === "string" && value.trim()) {
      return value.split(",").map((entry) => entry.trim());
    }

    return [];
  });

  return [...new Set(roleClaims.filter((value) => typeof value === "string" && value.trim()))];
}

function matchesAudience(claimValue, expectedAudience) {
  if (Array.isArray(claimValue)) {
    return claimValue.includes(expectedAudience);
  }

  return claimValue === expectedAudience;
}

function stringClaim(payload, name) {
  const value = payload?.[name];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function numericClaim(payload, name) {
  const value = payload?.[name];
  return typeof value === "number" ? value : null;
}

function deny(reason) {
  return {
    isAuthorized: false,
    context: {
      denialReason: reason,
    },
  };
}

function base64UrlDecode(value) {
  return base64UrlDecodeToBuffer(value).toString("utf8");
}

function base64UrlDecodeToBuffer(value) {
  const normalized = value.replaceAll("-", "+").replaceAll("_", "/");
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
  return Buffer.from(padded, "base64");
}

export const __testing = {
  authorizeRequest,
  extractSecretValue,
  resetCache() {
    cachedSecrets = undefined;
    cachedSecretsExpiresAt = 0;
    secretsManagerClient = undefined;
  },
};
