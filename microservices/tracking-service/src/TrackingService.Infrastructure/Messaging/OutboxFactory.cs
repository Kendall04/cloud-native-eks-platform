using System.Text.Json;
using TrackingService.Application.Contracts.Events;
using TrackingService.Domain.Entities;

namespace TrackingService.Infrastructure.Messaging;

public static class OutboxFactory
{
    public static OutboxMessage Create(TrackingEvent tracking, Guid eventId)
    {
        var data = new TrackingStatusUpdatedEventData(tracking.ShipmentId, tracking.Id,
            tracking.Status, tracking.Location, tracking.OccurredAt, tracking.SequenceNumber);
        var envelope = new EventEnvelope<TrackingStatusUpdatedEventData>(eventId.ToString(),
            "TrackingStatusUpdated", "2.0", "tracking-service", tracking.CreatedAt, data);
        return new OutboxMessage
        {
            EventId = eventId, AggregateId = tracking.ShipmentId, AggregateSequence = tracking.SequenceNumber,
            Payload = JsonSerializer.Serialize(envelope, TrackingEventJson.Options),
            CreatedAt = tracking.CreatedAt, NextAttemptAt = tracking.CreatedAt
        };
    }
}
