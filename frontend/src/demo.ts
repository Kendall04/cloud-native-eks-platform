import {
  createSchema,
  type PlatformApi,
  type Shipment,
  type Profile,
  type TrackingEvent,
} from "./contracts";
import { ApiError } from "./api";
export const demoProfile: Profile = {
  userId: "10000000-0000-4000-8000-000000000001",
  email: "demo@example.invalid",
  userName: "demo",
  firstName: "Alex",
  lastName: "Rivera",
  isActive: true,
  createdAt: "2026-10-01T08:00:00Z",
  roles: ["USER"],
};
export function createDemoApi(): PlatformApi {
  let active = false;
  const seeds = [
    ["IN_TRANSIT", "San José, CR", "Austin, TX"],
    ["DELIVERED", "Heredia, CR", "San Francisco, CA"],
    ["CREATED", "Cartago, CR", "Miami, FL"],
    ["DELAYED", "Alajuela, CR", "Seattle, WA"],
  ] as const;
  const shipments: Shipment[] = seeds.map(
    ([status, origin, destination], i) => ({
      id: `20000000-0000-4000-8000-00000000000${i + 1}`,
      trackingNumber: `DEMO-2026-00${i + 1}`,
      customerId: demoProfile.userId,
      origin,
      destination,
      weight: [2.4, 3.2, 1.8, 5.6][i],
      status,
      referenceNumber: ["NOVA-2401", "STUDIO-1842", "COAST-3106", "CEDAR-0912"][
        i
      ],
      priority: i === 0 ? "Express" : "Standard",
      lastTrackingEventAt: i === 2 ? null : `2026-10-${15 - i}T16:00:00.000Z`,
      version: 1,
      createdAt: `2026-10-${15 - i}T08:00:00Z`,
      updatedAt: `2026-10-${15 - i}T${i === 2 ? "08" : "16"}:00:00Z`,
    }),
  );
  const guard = () => {
    if (!active) throw new ApiError(401, "Please enter the demo first.");
  };
  return {
    register: async () => {
      throw new Error("Registration is not used in DEMO.");
    },
    setToken: (t) => {
      active = !!t;
    },
    login: async () => {
      active = true;
      return {
        accessToken: "synthetic-demo-session",
        refreshToken: "",
        accessTokenExpiresAt: new Date(Date.now() + 3600000).toISOString(),
        refreshTokenExpiresAt: new Date(Date.now() + 3600000).toISOString(),
      };
    },
    me: async () => {
      guard();
      return demoProfile;
    },
    list: async (page = 1, status = "") => {
      guard();
      const filtered = shipments.filter((s) => !status || s.status === status);
      return {
        items: filtered
          .slice((page - 1) * 20, page * 20)
          .map((s) => ({ ...s })),
        pageNumber: page,
        pageSize: 20,
        totalCount: filtered.length,
      };
    },
    lookup: async (number) => {
      guard();
      const shipment = shipments.find((s) => s.trackingNumber === number);
      if (!shipment) throw new ApiError(404, "Tracking number not found.");
      return { ...shipment };
    },
    get: async (id) => {
      guard();
      const s = shipments.find((s) => s.id === id);
      if (!s) throw new ApiError(404, "Shipment not found.");
      return { ...s };
    },
    create: async (input) => {
      guard();
      createSchema.parse(input);
      const now = new Date().toISOString();
      const s: Shipment = {
        ...input,
        referenceNumber: input.referenceNumber ?? null,
        priority: input.priority ?? null,
        id: crypto.randomUUID(),
        trackingNumber: `DEMO-${crypto.randomUUID().slice(0, 8).toUpperCase()}`,
        status: "CREATED",
        lastTrackingEventAt: null,
        version: 1,
        createdAt: now,
        updatedAt: now,
      };
      shipments.unshift(s);
      return { ...s };
    },
    timeline: async (number) => {
      guard();
      const s = shipments.find((s) => s.trackingNumber === number);
      if (!s) throw new ApiError(404, "Tracking number not found.");
      if (s.status === "CREATED") return [];
      return ["CREATED", "PICKED_UP", s.status].map((status, i) => ({
        id: `30000000-0000-4000-8000-${s.id.slice(-10)}0${i + 1}`,
        shipmentId: s.id,
        status: status as TrackingEvent["status"],
        location:
          i === 0
            ? s.origin
            : i === 1
              ? "Regional hub"
              : s.status === "DELIVERED"
                ? s.destination
                : "Transfer hub",
        notes: i === 2 ? "Synthetic demonstration event." : null,
        sourceType: "SYSTEM",
        occurredAt: new Date(
          Date.parse(s.createdAt) + i * 4 * 3600000,
        ).toISOString(),
        createdAt: new Date(
          Date.parse(s.createdAt) + i * 4 * 3600000 + 1000,
        ).toISOString(),
        createdBy: null,
        sequenceNumber: i + 1,
      }));
    },
  };
}
