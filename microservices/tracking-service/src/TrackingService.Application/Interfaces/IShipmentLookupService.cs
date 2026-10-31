using TrackingService.Application.Contracts.Shipments;

namespace TrackingService.Application.Interfaces;

public interface IShipmentLookupService
{
    Task<bool> ShipmentExistsAsync(Guid shipmentId, CancellationToken cancellationToken = default);

    Task<ShipmentSummary?> GetShipmentByIdAsync(Guid shipmentId, CancellationToken cancellationToken = default);

    Task<ShipmentSummary?> GetShipmentByTrackingNumberAsync(
        string trackingNumber,
        CancellationToken cancellationToken = default);
}
