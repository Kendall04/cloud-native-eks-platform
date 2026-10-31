using ShipmentService.Domain.Enums;

namespace ShipmentService.Application.Contracts.Shipments;

public sealed record ShipmentResponse(
    Guid Id,
    string TrackingNumber,
    string CustomerId,
    string Origin,
    string Destination,
    decimal Weight,
    ShipmentStatus Status,
    string? ReferenceNumber,
    string? Priority,
    DateTime? LastTrackingEventAt,
    int Version,
    DateTime CreatedAt,
    DateTime UpdatedAt);
