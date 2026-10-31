# ADR-003 — Event reliability

Status: Accepted and implemented. Live observations and their limits are recorded in [results](../results.md).

Decision: only TrackingStatusUpdated v2.0 is active. Tracking business state/outbox commit together. In-process dispatcher claims durable rows with leases and bounded retry, retains EventId, and records publication. Shipment uses PostgreSQL row locking, durable ProcessedEvents and SequenceNumber. Future sequences wait without inbox mutation; duplicates acknowledge only after durable state confirms processing. Operator recovery addresses gaps/quarantine.

Why: removes DB/EventBridge dual-write loss without adding a service/database. At-least-once publication can duplicate after publish-before-marker failure; inbox makes business effects idempotent. Sequence is separate from optimistic metadata version.

Alternatives rejected: exactly-once delivery claims, marking future transitions permanently processed, FIFO as a substitute for the full EventBridge/source ordering problem, a new messaging platform. ShipmentCreated/ShipmentStatusChanged and analytics are outside current scope; notification is historical/extended.

Evidence: Tracking OutboxStore/Dispatcher, Shipment TrackingEventProcessor, EventReliability.Tests, event recovery runbook. Validation: required real PostgreSQL CI, no skipped tests accepted. Those fault cases have local regression coverage; the final runtime record establishes functional propagation, not exhaustive failure-path certification.
