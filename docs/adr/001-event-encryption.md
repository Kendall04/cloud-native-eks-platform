# ADR-001 — EventBridge/SQS encryption

Status: Accepted and implemented. Live observations and their limits are recorded in [results](../results.md).

Decision: share one customer-managed environment KMS key across the active shipment queue, processing DLQ and EventBridge delivery DLQ. SQS resource policy and KMS key policy remain distinct. EventBridge gets GenerateDataKey/Decrypt through key policy; Shipment gets scoped Decrypt. Tracking publishes to EventBridge, not directly to SQS. KEDA reads queue attributes and needs no decrypt.

Why: the AWS-managed SQS key cannot be edited to grant the EventBridge service principal the required access. One key suffices for this trust domain; per-queue keys add no necessary portfolio isolation.

Alternatives rejected: alias/aws/sqs for this delivery pipeline, one key per queue, giving publisher/metrics roles blanket KMS privileges.

Evidence: infra/modules/event-encryption, sqs, eventbridge; infra/live/dev/iam. Validation: validate_r2 and negative policy tests. Functional event delivery was observed; not every failure-DLQ scenario is established by the final evidence.
