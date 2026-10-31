namespace ShipmentService.Application.Contracts.Shipments;

public sealed record ShipmentSummaryResponse(
    Guid Id,
    string TrackingNumber,
    string CustomerId);
