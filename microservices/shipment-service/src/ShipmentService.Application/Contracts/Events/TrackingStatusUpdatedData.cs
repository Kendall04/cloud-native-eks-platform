using ShipmentService.Domain.Enums;

namespace ShipmentService.Application.Contracts.Events;

public sealed record TrackingStatusUpdatedData(
    Guid ShipmentId,
    string TrackingEventId,
    ShipmentStatus Status,
    string Location,
    DateTime EventOccurredAt,
    long SequenceNumber = 0);
