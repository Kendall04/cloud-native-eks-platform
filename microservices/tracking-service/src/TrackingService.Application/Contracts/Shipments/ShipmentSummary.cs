namespace TrackingService.Application.Contracts.Shipments;

public sealed record ShipmentSummary(
    Guid Id,
    string TrackingNumber,
    string CustomerId);
