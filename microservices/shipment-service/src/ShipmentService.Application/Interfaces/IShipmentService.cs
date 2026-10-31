using ShipmentService.Application.Common.Authorization;
using ShipmentService.Application.Contracts.Shipments;

namespace ShipmentService.Application.Interfaces;

public interface IShipmentService
{
    Task<bool> ExistsAsync(
        Guid shipmentId,
        CancellationToken cancellationToken = default);

    Task<ShipmentSummaryResponse?> GetSummaryByIdAsync(
        Guid shipmentId,
        CancellationToken cancellationToken = default);

    Task<ShipmentSummaryResponse?> GetSummaryByTrackingNumberAsync(
        string trackingNumber,
        CancellationToken cancellationToken = default);

    Task<ShipmentResponse> CreateAsync(
        CreateShipmentRequest request,
        RequestUserContext currentUser,
        CancellationToken cancellationToken = default);

    Task<ShipmentResponse> GetByIdAsync(
        Guid shipmentId,
        RequestUserContext currentUser,
        CancellationToken cancellationToken = default);

    Task<PagedResult<ShipmentResponse>> ListAsync(
        ListShipmentsRequest request,
        RequestUserContext currentUser,
        CancellationToken cancellationToken = default);

    Task<ShipmentResponse> GetByTrackingNumberAsync(
        string trackingNumber,
        RequestUserContext currentUser,
        CancellationToken cancellationToken = default);
}
