# Event operations

[Architecture](../architecture/current-platform.md#event-path) · [Deployment](deployment.md) · [Database](secrets-database.md)

Tracking publishes `TrackingStatusUpdated` v2.0 through a durable outbox. Shipment consumes the standard queue with a durable inbox and per-shipment sequence checkpoint. The stable domain EventId differs from EventBridge/SQS transport IDs. Recovery must preserve domain EventId, aggregate, sequence and payload.

## Diagnose before replay

Use the generated environment contract for exact bus, queue, DLQ and KMS identities; verify account/region first. Inspect outbox age/failures, queue age/depth, DLQs and Shipment checkpoints together. A quiet approximate queue count does not prove that all events committed.

The [operator CLI](../../scripts/operations/events.py) requires `R5_OPERATOR_DSN` in the local process environment and suitable database privileges. Remote connections require VerifyFull TLS. Do not log the DSN. These commands output metadata, excluding event payloads and credentials:

```bash
python3 scripts/operations/events.py list-failed
python3 scripts/operations/events.py inspect --event-id <uuid>
python3 scripts/operations/events.py requeue --event-id <uuid>
```

`requeue` mutates PostgreSQL. It accepts only a failed, unpublished row with no active lease, resets its retry cycle and retains event identity. Do not clear PublishedAt globally. After publish-before-marker failure, duplicates are expected and must pass through durable deduplication.

## Distinct failure queues

| Queue | Meaning | Recovery |
| --- | --- | --- |
| EventBridge delivery DLQ | Target delivery failed/exhausted retries | Fix target/KMS/policy, recover the original envelope, deliberately republish through EventBridge |
| Shipment processing DLQ | Consumer failed repeatedly | Diagnose inbox/checkpoint/predecessor, repair cause, then redrive a reviewed batch or selected message |

Inspect a small receive batch without deleting; receiving temporarily hides messages. Keep receipt handles private. For delivery failures record bounded failure attributes and EventId, compare with the source outbox, and extract the v2 envelope from `detail` if wrapped. Normal routing uses `$.detail`. Republish the exact envelope with Source `tracking-service` and DetailType `TrackingStatusUpdated`; confirm the durable Shipment outcome before deleting the original DLQ message. Do not use native SQS redrive for an EventBridge-source DLQ.

For the processing DLQ, distinguish malformed/unsupported payload, missing shipment, transient DB failure and missing predecessor. For a reviewed homogeneous batch, use SQS StartMessageMoveTask with the consumer DLQ ARN and source queue ARN from the contract, a bounded rate and monitored task handle. For selected messages, send the unchanged envelope and confirm the inbox before deleting its original receipt. Replay permissions belong to an operator, not Shipment/CD.

For checkpoint N and delayed N+2, locate N+1 in TrackingEvents/OutboxMessages, restore it from failed/published outbox or DLQs, verify processing, then replay successors. If the predecessor cannot be established, reconcile authoritative history under review. Never advance a checkpoint merely to drain the queue.

Source settings: EventBridge target age 3600 seconds/max 10 retries; source retention four days; both DLQs 14 days; processing redrive after five receives. These are retry/retention limits, not delivery-time guarantees.

## Existing event-v1 data

Fresh reconstruction uses v2 directly. Restoring old v1 data requires a maintenance cutover; SQL migrations alone do not reconcile historical events.

1. Stop admin tracking writes and alternate writers. Drain/reconcile v1 queue/DLQs using the old consumer; ambiguous history blocks progress.
2. Build a reviewed bridge artifact from v2 code with tracked values `services.tracking.env.Outbox__Enabled: "false"` and `services.shipment.env.ShipmentConsumer__Enabled: "false"`. Deploy through the normal artifact path; wait for all old Tracking/Shipment pods to exit.
3. With writes/workers still paused, review each historical shipment:

   ```bash
   python3 scripts/operations/events.py baseline-report --shipment-id <uuid>
   python3 scripts/operations/events.py baseline --shipment-id <uuid> --review-token <hash> --reviewed-sequence <N>
   ```

   Nonempty history needs an explicitly reconciled prefix. The CLI locks the shipment/history, checks the current fingerprint and rejects baselining over existing v2 outbox rows.
4. Enable the v2 consumer first in a new reviewed artifact, then enable the outbox dispatcher and restore tracking writes after checking every baseline. Verify the first v2 sequence is the expected successor.
5. Once v2 is active, only v2-compatible rollback artifacts are valid. Helm does not downgrade the event protocol or undo data reconciliation.

Recovery commands and cutover constraints are source-backed procedures. The final lifecycle record proves functional EventBridge/SQS processing; it does not prove every DLQ/cutover scenario was exercised live.
