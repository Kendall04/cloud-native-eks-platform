using TrackingService.Domain.Enums;

namespace TrackingService.Application.Contracts.Events;

public sealed record TrackingStatusUpdatedEventData(
    Guid ShipmentId,
    Guid TrackingEventId,
    TrackingStatus Status,
    string Location,
    DateTime EventOccurredAt,
    long SequenceNumber);
