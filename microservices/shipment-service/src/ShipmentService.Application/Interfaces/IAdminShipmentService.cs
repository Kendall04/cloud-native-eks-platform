using ShipmentService.Application.Contracts.Shipments;

namespace ShipmentService.Application.Interfaces;

public interface IAdminShipmentService
{
    Task<ShipmentResponse> UpdateMetadataAsync(
        Guid shipmentId,
        UpdateShipmentMetadataRequest request,
        CancellationToken cancellationToken = default);
}
