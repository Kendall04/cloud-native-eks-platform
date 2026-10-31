using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using ShipmentService.Application.Common.Authorization;
using ShipmentService.Application.Common.Exceptions;
using ShipmentService.Application.Contracts.Shipments;
using ShipmentService.Application.Interfaces;
using ShipmentService.Domain.Entities;
using ShipmentService.Infrastructure.Persistence;

namespace ShipmentService.Infrastructure.Services;

public sealed class ShipmentApplicationService(
    ShipmentDbContext dbContext,
    ITrackingNumberGenerator trackingNumberGenerator,
    TimeProvider timeProvider,
    ILogger<ShipmentApplicationService> logger) : IShipmentService
{
    public Task<bool> ExistsAsync(
        Guid shipmentId,
        CancellationToken cancellationToken = default) =>
        dbContext.Shipments
            .AsNoTracking()
            .AnyAsync(candidate => candidate.Id == shipmentId, cancellationToken);

    public async Task<ShipmentSummaryResponse?> GetSummaryByIdAsync(
        Guid shipmentId,
        CancellationToken cancellationToken = default)
    {
        var shipment = await dbContext.Shipments
            .AsNoTracking()
            .SingleOrDefaultAsync(candidate => candidate.Id == shipmentId, cancellationToken);

        return shipment is null ? null : ShipmentMappings.ToSummaryResponse(shipment);
    }

    public async Task<ShipmentSummaryResponse?> GetSummaryByTrackingNumberAsync(
        string trackingNumber,
        CancellationToken cancellationToken = default)
    {
        var normalizedTrackingNumber = trackingNumber.Trim();

        if (string.IsNullOrWhiteSpace(normalizedTrackingNumber))
        {
            throw new ValidationException("Tracking number is required.");
        }

        var shipment = await dbContext.Shipments
            .AsNoTracking()
            .SingleOrDefaultAsync(
                candidate => candidate.TrackingNumber == normalizedTrackingNumber,
                cancellationToken);

        return shipment is null ? null : ShipmentMappings.ToSummaryResponse(shipment);
    }

    public async Task<ShipmentResponse> CreateAsync(
        CreateShipmentRequest request,
        RequestUserContext currentUser,
        CancellationToken cancellationToken = default)
    {
        if (!currentUser.IsAdmin &&
            !string.Equals(request.CustomerId.Trim(), currentUser.UserId, StringComparison.Ordinal))
        {
            throw new ForbiddenAppException("Users can only create shipments for themselves.");
        }

        var shipment = await CreateShipmentWithUniqueTrackingNumberAsync(request, cancellationToken);

        logger.LogInformation(
            "Created shipment {ShipmentId} with tracking number {TrackingNumber} for customer {CustomerId}",
            shipment.Id,
            shipment.TrackingNumber,
            shipment.CustomerId);

        return ShipmentMappings.ToResponse(shipment);
    }

    public async Task<ShipmentResponse> GetByIdAsync(
        Guid shipmentId,
        RequestUserContext currentUser,
        CancellationToken cancellationToken = default)
    {
        var shipment = await dbContext.Shipments
            .AsNoTracking()
            .SingleOrDefaultAsync(candidate => candidate.Id == shipmentId, cancellationToken)
            ?? throw new NotFoundException("Shipment was not found.");

        EnsureAccessible(shipment, currentUser);
        return ShipmentMappings.ToResponse(shipment);
    }

    public async Task<PagedResult<ShipmentResponse>> ListAsync(
        ListShipmentsRequest request,
        RequestUserContext currentUser,
        CancellationToken cancellationToken = default)
    {
        var pageNumber = Math.Max(request.PageNumber, 1);
        var pageSize = Math.Clamp(request.PageSize, 1, 100);

        IQueryable<Shipment> query = dbContext.Shipments.AsNoTracking();

        if (request.Status.HasValue)
        {
            query = query.Where(shipment => shipment.Status == request.Status.Value);
        }

        if (currentUser.IsAdmin)
        {
            if (!string.IsNullOrWhiteSpace(request.CustomerId))
            {
                var customerId = request.CustomerId.Trim();
                query = query.Where(shipment => shipment.CustomerId == customerId);
            }
        }
        else
        {
            query = query.Where(shipment => shipment.CustomerId == currentUser.UserId);
        }

        query = query.OrderByDescending(shipment => shipment.CreatedAt);

        var totalCount = await query.CountAsync(cancellationToken);
        var shipments = await query
            .Skip((pageNumber - 1) * pageSize)
            .Take(pageSize)
            .ToListAsync(cancellationToken);

        return new PagedResult<ShipmentResponse>(
            shipments.Select(ShipmentMappings.ToResponse).ToArray(),
            pageNumber,
            pageSize,
            totalCount);
    }

    public async Task<ShipmentResponse> GetByTrackingNumberAsync(
        string trackingNumber,
        RequestUserContext currentUser,
        CancellationToken cancellationToken = default)
    {
        var normalizedTrackingNumber = trackingNumber.Trim();

        var shipment = await dbContext.Shipments
            .AsNoTracking()
            .SingleOrDefaultAsync(
                candidate => candidate.TrackingNumber == normalizedTrackingNumber,
                cancellationToken)
            ?? throw new NotFoundException("Shipment was not found.");

        EnsureAccessible(shipment, currentUser);
        return ShipmentMappings.ToResponse(shipment);
    }

    private async Task<Shipment> CreateShipmentWithUniqueTrackingNumberAsync(
        CreateShipmentRequest request,
        CancellationToken cancellationToken)
    {
        const int maxAttempts = 5;

        for (var attempt = 0; attempt < maxAttempts; attempt++)
        {
            var utcNow = timeProvider.GetUtcNow().UtcDateTime;
            var trackingNumber = trackingNumberGenerator.Generate();
            var shipment = Shipment.Create(
                trackingNumber,
                request.CustomerId,
                request.Origin,
                request.Destination,
                request.Weight,
                request.ReferenceNumber,
                request.Priority,
                utcNow);

            dbContext.Shipments.Add(shipment);

            try
            {
                await dbContext.SaveChangesAsync(cancellationToken);
                return shipment;
            }
            catch (DbUpdateException exception) when (IsTrackingNumberConflict(exception) && attempt < maxAttempts - 1)
            {
                dbContext.Entry(shipment).State = EntityState.Detached;

                logger.LogWarning(
                    "Retrying shipment creation because tracking number {TrackingNumber} conflicted with an existing record",
                    trackingNumber);
            }
        }

        throw new ConflictException("Unable to generate a unique tracking number.");
    }

    private static bool IsTrackingNumberConflict(DbUpdateException exception)
    {
        var message = exception.InnerException?.Message ?? exception.Message;
        return message.Contains("TrackingNumber", StringComparison.OrdinalIgnoreCase) ||
               message.Contains("IX_Shipments_TrackingNumber", StringComparison.OrdinalIgnoreCase);
    }

    private static void EnsureAccessible(Shipment shipment, RequestUserContext currentUser)
    {
        if (currentUser.IsAdmin)
        {
            return;
        }

        if (!string.Equals(shipment.CustomerId, currentUser.UserId, StringComparison.Ordinal))
        {
            throw new NotFoundException("Shipment was not found.");
        }
    }
}
