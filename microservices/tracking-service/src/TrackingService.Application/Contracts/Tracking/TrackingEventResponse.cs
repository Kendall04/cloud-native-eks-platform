using TrackingService.Domain.Enums;

namespace TrackingService.Application.Contracts.Tracking;

public sealed record TrackingEventResponse(
    Guid Id,
    Guid ShipmentId,
    TrackingStatus Status,
    string Location,
    string? Notes,
    TrackingSourceType SourceType,
    DateTime OccurredAt,
    DateTime CreatedAt,
    string? CreatedBy,
    int SequenceNumber);
