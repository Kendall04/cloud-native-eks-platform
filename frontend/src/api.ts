import { z } from "zod";
export { readConfig } from "./config";
import {
  pageSchema,
  shipmentSchema,
  eventSchema,
  profileSchema,
  tokensSchema,
  createSchema,
  type PlatformApi,
} from "./contracts";
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
const messages: Record<number, string> = {
  400: "Check the submitted fields and try again.",
  401: "Your session is invalid or expired. Please sign in again.",
  403: "Your account cannot access this resource.",
  404: "This resource could not be found.",
  409: "This change conflicts with existing data. Refresh and try again.",
  429: "Too many requests. Please wait before trying again.",
  500: "The service encountered an error. Try again later.",
  502: "The backend is unavailable. Please try again later.",
  503: "A required service is unavailable. Please try again later.",
};
export function apiMessage(error: unknown) {
  return error instanceof Error
    ? error.message
    : "An unexpected error occurred.";
}
export function createHttpApi(
  base = "/api",
  onUnauthorized = () => {},
  timeoutMs = 10000,
): PlatformApi {
  let token: string | null = null;
  async function request<T>(
    path: string,
    schema: z.ZodType<T>,
    body?: unknown,
  ): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(base + path, {
        method: body === undefined ? "GET" : "POST",
        headers: {
          Accept: "application/json",
          ...(body === undefined ? {} : { "Content-Type": "application/json" }),
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
        credentials: "omit",
        cache: "no-store",
        redirect: "error",
      });
      if (!response.ok) {
        if (response.status === 401) {
          token = null;
          if (path !== "/auth/login") onUnauthorized();
        }
        throw new ApiError(
          response.status,
          (response.status === 401 && path === "/auth/login"
            ? "Email or password is incorrect."
            : messages[response.status]) ??
            `Request failed (HTTP ${response.status}).`,
        );
      }
      let value: unknown;
      try {
        value = await response.json();
      } catch {
        throw new ApiError(0, "The service returned an invalid response.");
      }
      const parsed = schema.safeParse(value);
      if (!parsed.success)
        throw new ApiError(0, "The service returned an invalid response.");
      return parsed.data;
    } catch (e) {
      if (e instanceof ApiError) throw e;
      throw new ApiError(
        0,
        controller.signal.aborted
          ? "The request timed out. Please try again."
          : "Cannot reach the backend. Check your connection and try again.",
      );
    } finally {
      clearTimeout(timer);
    }
  }
  return {
    setToken: (v) => {
      token = v;
    },
    register: (input) =>
      request("/auth/register", z.object({ userId: z.string().uuid() }), input),
    login: (email, password) =>
      request("/auth/login", tokensSchema, { email, password }),
    me: () => request("/auth/me", profileSchema),
    list: (page = 1, status = "") =>
      request(
        `/shipments?PageNumber=${page}&PageSize=20${status ? "&Status=" + encodeURIComponent(status) : ""}`,
        pageSchema,
      ),
    lookup: (number) =>
      request(
        "/shipments/by-tracking/" + encodeURIComponent(number),
        shipmentSchema,
      ),
    get: (id) =>
      request("/shipments/by-id/" + encodeURIComponent(id), shipmentSchema),
    create: (input) =>
      request("/shipments", shipmentSchema, createSchema.parse(input)),
    timeline: (number) =>
      request(
        "/tracking/by-tracking-number/" + encodeURIComponent(number),
        z.array(eventSchema),
      ),
  };
}
