import { z } from "zod";
export const statuses = [
  "CREATED",
  "PICKED_UP",
  "IN_WAREHOUSE",
  "IN_TRANSIT",
  "OUT_FOR_DELIVERY",
  "DELIVERED",
  "DELAYED",
  "CANCELLED",
] as const;
const date = z.string().datetime({ offset: true });
export const shipmentSchema = z.object({
  id: z.string().uuid(),
  trackingNumber: z.string(),
  customerId: z.string(),
  origin: z.string(),
  destination: z.string(),
  weight: z.number(),
  status: z.enum(statuses),
  referenceNumber: z.string().nullable(),
  priority: z.string().nullable(),
  lastTrackingEventAt: date.nullable(),
  version: z.number().int(),
  createdAt: date,
  updatedAt: date,
});
export const pageSchema = z.object({
  items: z.array(shipmentSchema),
  pageNumber: z.number().int().positive(),
  pageSize: z.number().int().positive(),
  totalCount: z.number().int().nonnegative(),
});
export const eventSchema = z.object({
  id: z.string().uuid(),
  shipmentId: z.string().uuid(),
  status: z.enum(statuses),
  location: z.string(),
  notes: z.string().nullable(),
  sourceType: z.enum(["ADMIN", "SYSTEM", "EXTERNAL"]),
  occurredAt: date,
  createdAt: date,
  createdBy: z.string().nullable(),
  sequenceNumber: z.number().int(),
});
export const profileSchema = z.object({
  userId: z.string().uuid(),
  email: z.string(),
  userName: z.string(),
  firstName: z.string(),
  lastName: z.string(),
  isActive: z.boolean(),
  createdAt: date,
  roles: z.array(z.string()),
});
export const tokensSchema = z.object({
  accessToken: z.string().min(1),
  accessTokenExpiresAt: date,
  refreshToken: z.string(),
  refreshTokenExpiresAt: date,
});
export const createSchema = z.object({
  customerId: z.string().trim().min(1).max(100),
  origin: z.string().trim().min(1).max(200),
  destination: z.string().trim().min(1).max(200),
  weight: z.number().min(0.01).max(100000),
  referenceNumber: z.string().max(100).nullable().optional(),
  priority: z.string().max(50).nullable().optional(),
});
export type Shipment = z.infer<typeof shipmentSchema>;
export type ShipmentPage = z.infer<typeof pageSchema>;
export type TrackingEvent = z.infer<typeof eventSchema>;
export type Profile = z.infer<typeof profileSchema>;
export type Tokens = z.infer<typeof tokensSchema>;
export type CreateShipment = z.infer<typeof createSchema>;
export interface PlatformApi {
  register(input: {
    email: string;
    password: string;
    firstName: string;
    lastName: string;
  }): Promise<unknown>;
  login(email: string, password: string): Promise<Tokens>;
  me(): Promise<Profile>;
  list(page?: number, status?: string): Promise<ShipmentPage>;
  get(id: string): Promise<Shipment>;
  lookup(number: string): Promise<Shipment>;
  create(input: CreateShipment): Promise<Shipment>;
  timeline(number: string): Promise<TrackingEvent[]>;
  setToken(token: string | null): void;
}
