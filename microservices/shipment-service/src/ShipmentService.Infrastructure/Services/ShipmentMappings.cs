using ShipmentService.Application.Contracts.Shipments;
using ShipmentService.Domain.Entities;

namespace ShipmentService.Infrastructure.Services;

internal static class ShipmentMappings
{
    public static ShipmentSummaryResponse ToSummaryResponse(Shipment shipment) =>
        new(
            shipment.Id,
            shipment.TrackingNumber,
            shipment.CustomerId);

    public static ShipmentResponse ToResponse(Shipment shipment) =>
        new(
            shipment.Id,
            shipment.TrackingNumber,
            shipment.CustomerId,
            shipment.Origin,
            shipment.Destination,
            shipment.Weight,
            shipment.Status,
            shipment.ReferenceNumber,
            shipment.Priority,
            shipment.LastTrackingEventAt,
            shipment.Version,
            shipment.CreatedAt,
            shipment.UpdatedAt);
}
