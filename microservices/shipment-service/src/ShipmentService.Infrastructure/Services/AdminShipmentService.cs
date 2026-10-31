using Microsoft.EntityFrameworkCore;
using ShipmentService.Application.Common.Exceptions;
using ShipmentService.Application.Contracts.Shipments;
using ShipmentService.Application.Interfaces;
using ShipmentService.Infrastructure.Persistence;

namespace ShipmentService.Infrastructure.Services;

public sealed class AdminShipmentService(
    ShipmentDbContext dbContext,
    TimeProvider timeProvider) : IAdminShipmentService
{
    public async Task<ShipmentResponse> UpdateMetadataAsync(
        Guid shipmentId,
        UpdateShipmentMetadataRequest request,
        CancellationToken cancellationToken = default)
    {
        var shipment = await dbContext.Shipments
            .SingleOrDefaultAsync(candidate => candidate.Id == shipmentId, cancellationToken)
            ?? throw new NotFoundException("Shipment was not found.");

        shipment.UpdateMetadata(
            request.ReferenceNumber,
            request.Priority,
            timeProvider.GetUtcNow().UtcDateTime);

        await dbContext.SaveChangesAsync(cancellationToken);
        return ShipmentMappings.ToResponse(shipment);
    }
}
