import { describe, it, expect } from "vitest";
import { createDemoApi, demoProfile } from "./demo";
import { shipmentSchema, eventSchema } from "./contracts";
describe("coherent deterministic DEMO fixtures", () => {
  it("uses ordered UTC events at/after creation, matching status and last-event timestamps", async () => {
    const api = createDemoApi();
    await api.login("", "");
    const { items } = await api.list();
    for (const s of items) {
      shipmentSchema.parse(s);
      const events = await api.timeline(s.trackingNumber);
      for (const [i, event] of events.entries()) {
        eventSchema.parse(event);
        expect(event.shipmentId).toBe(s.id);
        expect(event.sequenceNumber).toBe(i + 1);
        expect(Date.parse(event.occurredAt)).toBeGreaterThanOrEqual(
          Date.parse(s.createdAt),
        );
        expect(Date.parse(event.createdAt)).toBeGreaterThanOrEqual(
          Date.parse(event.occurredAt),
        );
        if (i)
          expect(Date.parse(event.occurredAt)).toBeGreaterThan(
            Date.parse(events[i - 1].occurredAt),
          );
      }
      if (s.status === "CREATED") {
        expect(events).toEqual([]);
        expect(s.lastTrackingEventAt).toBeNull();
      } else {
        const first = events[0],
          last = events.at(-1)!;
        expect(first.status).toBe("CREATED");
        expect(Date.parse(first.occurredAt)).toBe(Date.parse(s.createdAt));
        expect(last.status).toBe(s.status);
        expect(last.occurredAt).toBe(s.lastTrackingEventAt);
        expect(Date.parse(s.updatedAt)).toBeGreaterThanOrEqual(
          Date.parse(last.occurredAt),
        );
        if (s.status === "DELIVERED") expect(last.location).toBe(s.destination);
      }
      expect((await api.lookup(s.trackingNumber)).id).toBe(s.id);
    }
  });
  it("keeps newly created synthetic shipments eventless and independent from seed data", async () => {
    const api = createDemoApi();
    await api.login("", "");
    const s = await api.create({
      customerId: demoProfile.userId,
      origin: "A",
      destination: "B",
      weight: 0.01,
      priority: "Customer-defined",
    });
    expect(s.createdAt).toBe(s.updatedAt);
    expect(s.lastTrackingEventAt).toBeNull();
    expect(await api.timeline(s.trackingNumber)).toEqual([]);
  });
});
