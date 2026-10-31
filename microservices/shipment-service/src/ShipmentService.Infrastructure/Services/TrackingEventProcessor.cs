using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using ShipmentService.Application.Contracts.Events;
using ShipmentService.Application.Interfaces;
using ShipmentService.Domain.Entities;
using ShipmentService.Domain.Enums;
using ShipmentService.Infrastructure.Messaging;
using ShipmentService.Infrastructure.Persistence;

namespace ShipmentService.Infrastructure.Services;

public sealed class TrackingEventProcessor(ShipmentDbContext dbContext, TimeProvider timeProvider,
    ILogger<TrackingEventProcessor> logger) : ITrackingEventProcessor
{
    public static EventEnvelope<TrackingStatusUpdatedData> Parse(string body)
    {
        var e = JsonSerializer.Deserialize<EventEnvelope<TrackingStatusUpdatedData>>(body, ShipmentEventJson.Options)
            ?? throw new InvalidOperationException("InvalidTrackingPayload");
        if (e.EventType != "TrackingStatusUpdated" || e.EventVersion != "2.0" || e.Source != "tracking-service")
            throw new InvalidOperationException("UnsupportedTrackingContract");
        if (!Guid.TryParse(e.EventId, out var id) || id == Guid.Empty || e.Data is null || e.Data.ShipmentId == Guid.Empty ||
            !Guid.TryParse(e.Data.TrackingEventId, out var trackingId) || trackingId == Guid.Empty || e.Data.SequenceNumber < 1 ||
            e.Data.EventOccurredAt == default || e.Data.EventOccurredAt.Kind != DateTimeKind.Utc || !Enum.IsDefined(e.Data.Status))
            throw new InvalidOperationException("InvalidTrackingPayload");
        return e;
    }

    public async Task<TrackingEventHandlingResult> ProcessAsync(string messageBody, CancellationToken cancellationToken = default)
    {
        var envelope = Parse(messageBody);
        await using var transaction = await dbContext.Database.BeginTransactionAsync(cancellationToken);
        // Always read locked state afresh even if this scoped context was previously used.
        dbContext.ChangeTracker.Clear();
        var rows = await dbContext.Shipments.FromSqlInterpolated($"""
            SELECT * FROM "Shipments" WHERE "Id" = {envelope.Data.ShipmentId} FOR UPDATE
            """).ToListAsync(cancellationToken);
        var shipment = rows.SingleOrDefault();
        var existing = await dbContext.ProcessedEvents.AsNoTracking()
            .SingleOrDefaultAsync(x => x.EventId == envelope.EventId, cancellationToken);
        if (existing is not null)
        {
            if (existing.ShipmentId != envelope.Data.ShipmentId || existing.SequenceNumber != envelope.Data.SequenceNumber)
                throw new InvalidOperationException("EventIdentityConflict");
            await transaction.CommitAsync(cancellationToken);
            return Result(TrackingEventHandlingOutcome.Duplicate);
        }
        if (shipment is null) return Result(TrackingEventHandlingOutcome.ShipmentNotFound);
        if (shipment.LastProcessedTrackingSequence is null) return Result(TrackingEventHandlingOutcome.BaselineRequired);
        if (envelope.Data.SequenceNumber > shipment.LastProcessedTrackingSequence + 1)
            return Result(TrackingEventHandlingOutcome.WaitingPredecessor);

        TrackingEventHandlingOutcome outcome;
        if (envelope.Data.SequenceNumber <= shipment.LastProcessedTrackingSequence)
            outcome = TrackingEventHandlingOutcome.RejectedSequenceConflict;
        else
        {
            outcome = shipment.ApplyTrackingStatusUpdate(envelope.Data.Status, envelope.Data.EventOccurredAt,
                timeProvider.GetUtcNow().UtcDateTime) switch
            {
                TrackingStatusUpdateOutcome.Applied => TrackingEventHandlingOutcome.Applied,
                TrackingStatusUpdateOutcome.AppliedWithoutStatusChange => TrackingEventHandlingOutcome.AppliedWithoutStatusChange,
                TrackingStatusUpdateOutcome.IgnoredOutOfOrder => TrackingEventHandlingOutcome.IgnoredHistorical,
                TrackingStatusUpdateOutcome.RejectedInvalidTransition => TrackingEventHandlingOutcome.RejectedInvalidTransition,
                _ => throw new InvalidOperationException("UnknownTransitionOutcome")
            };
            shipment.AdvanceTrackingSequence(envelope.Data.SequenceNumber);
        }
        dbContext.ProcessedEvents.Add(new ProcessedEvent
        {
            EventId = envelope.EventId, EventType = envelope.EventType, ShipmentId = shipment.Id,
            SequenceNumber = envelope.Data.SequenceNumber, Outcome = outcome.ToString(), ProcessedAt = timeProvider.GetUtcNow().UtcDateTime
        });
        await dbContext.SaveChangesAsync(cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return Result(outcome);

        TrackingEventHandlingResult Result(TrackingEventHandlingOutcome result)
        {
            var metric = result switch
            {
                TrackingEventHandlingOutcome.Applied or TrackingEventHandlingOutcome.AppliedWithoutStatusChange => "shipment.consumer.applied",
                TrackingEventHandlingOutcome.Duplicate => "shipment.consumer.duplicate",
                TrackingEventHandlingOutcome.WaitingPredecessor => "shipment.consumer.sequence_gap",
                TrackingEventHandlingOutcome.RejectedInvalidTransition or TrackingEventHandlingOutcome.RejectedSequenceConflict or TrackingEventHandlingOutcome.IgnoredHistorical => "shipment.consumer.rejected",
                _ => null
            };
            if (metric is not null) Observability.OperationalMetrics.Count(metric);
            logger.LogInformation("Tracking EventId={EventId} ShipmentId={ShipmentId} SequenceNumber={SequenceNumber} Outcome={Outcome}",
                envelope.EventId, envelope.Data.ShipmentId, envelope.Data.SequenceNumber, result);
            return new(envelope.EventId, envelope.EventType, result, envelope.Data.ShipmentId);
        }
    }
}
