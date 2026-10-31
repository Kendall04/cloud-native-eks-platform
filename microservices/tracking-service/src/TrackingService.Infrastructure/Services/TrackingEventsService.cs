using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Npgsql;
using TrackingService.Infrastructure.Messaging;
using TrackingService.Application.Common.Authorization;
using TrackingService.Application.Common.Exceptions;
using TrackingService.Application.Contracts.Shipments;
using TrackingService.Application.Contracts.Tracking;
using TrackingService.Application.Interfaces;
using TrackingService.Domain.Entities;
using TrackingService.Infrastructure.Persistence;

namespace TrackingService.Infrastructure.Services;

public sealed class TrackingEventsService(
    TrackingDbContext dbContext,
    IShipmentLookupService shipmentLookupService,
    TimeProvider timeProvider,
    ILogger<TrackingEventsService> logger) : ITrackingEventsService
{
    public async Task<IReadOnlyCollection<TrackingEventResponse>> GetTimelineByShipmentIdAsync(
        Guid shipmentId,
        RequestUserContext currentUser,
        CancellationToken cancellationToken = default)
    {
        if (shipmentId == Guid.Empty)
        {
            throw new ValidationException("ShipmentId is required.");
        }

        logger.LogInformation("Timeline requested for shipment {ShipmentId}", shipmentId);

        var shipment = await shipmentLookupService.GetShipmentByIdAsync(shipmentId, cancellationToken);

        if (shipment is null)
        {
            throw new NotFoundException("Shipment was not found.");
        }

        EnsureAccessible(shipment, currentUser);
        return await LoadTimelineAsync(shipment.Id, cancellationToken);
    }

    public async Task<IReadOnlyCollection<TrackingEventResponse>> GetTimelineByTrackingNumberAsync(
        string trackingNumber,
        RequestUserContext currentUser,
        CancellationToken cancellationToken = default)
    {
        var normalizedTrackingNumber = trackingNumber.Trim();

        if (string.IsNullOrWhiteSpace(normalizedTrackingNumber))
        {
            throw new ValidationException("Tracking number is required.");
        }

        logger.LogInformation("Timeline requested for tracking number {TrackingNumber}", normalizedTrackingNumber);

        var shipment = await shipmentLookupService.GetShipmentByTrackingNumberAsync(
            normalizedTrackingNumber,
            cancellationToken);

        if (shipment is null)
        {
            throw new NotFoundException("Shipment was not found.");
        }

        EnsureAccessible(shipment, currentUser);
        return await LoadTimelineAsync(shipment.Id, cancellationToken);
    }

    public async Task<TrackingEventResponse> CreateAsync(
        CreateTrackingEventRequest request,
        RequestUserContext currentUser,
        CancellationToken cancellationToken = default)
    {
        if (!currentUser.IsAdmin)
        {
            throw new ForbiddenAppException("Only administrators can create tracking events.");
        }

        if (request.ShipmentId == Guid.Empty)
        {
            throw new ValidationException("ShipmentId is required.");
        }

        if (request.Status is null)
        {
            throw new ValidationException("Status is required.");
        }

        // Validate before lookup, transaction or sequence allocation, including
        // callers that bypass HTTP deserialization.
        if (!Enum.IsDefined(request.Status.Value))
            throw new ValidationException("Status must be a defined tracking status.");
        if (!Enum.IsDefined(request.SourceType))
            throw new ValidationException("SourceType must be a defined tracking source.");

        var occurredAt = NormalizeOccurredAt(request.OccurredAt);

        logger.LogInformation(
            "Creating tracking event for shipment {ShipmentId} with status {Status} from source {SourceType}",
            request.ShipmentId,
            request.Status.Value,
            request.SourceType);

        var shipmentExists = await shipmentLookupService.ShipmentExistsAsync(request.ShipmentId, cancellationToken);

        if (!shipmentExists)
        {
            throw new NotFoundException("Shipment was not found.");
        }

        var trackingEvent = await CreateTrackingEventWithSequenceAsync(
            request,
            occurredAt,
            currentUser.UserId,
            cancellationToken);

        return TrackingMappings.ToResponse(trackingEvent);
    }

    private async Task<IReadOnlyCollection<TrackingEventResponse>> LoadTimelineAsync(
        Guid shipmentId,
        CancellationToken cancellationToken)
    {
        var timeline = await dbContext.TrackingEvents
            .AsNoTracking()
            .Where(trackingEvent => trackingEvent.ShipmentId == shipmentId)
            .OrderBy(trackingEvent => trackingEvent.OccurredAt)
            .ThenBy(trackingEvent => trackingEvent.SequenceNumber)
            .ToListAsync(cancellationToken);

        return timeline.Select(TrackingMappings.ToResponse).ToArray();
    }

    private async Task<TrackingEvent> CreateTrackingEventWithSequenceAsync(
        CreateTrackingEventRequest request,
        DateTime occurredAt,
        string createdBy,
        CancellationToken cancellationToken)
    {
        const int maxAttempts = 5;
        var eventId = Guid.NewGuid(); // One logical outbound identity, including sequence retries.

        for (var attempt = 0; attempt < maxAttempts; attempt++)
        {
            await using var transaction = await dbContext.Database.BeginTransactionAsync(cancellationToken);

            var nextSequenceNumber = (await dbContext.TrackingEvents
                .Where(trackingEvent => trackingEvent.ShipmentId == request.ShipmentId)
                .Select(trackingEvent => (int?)trackingEvent.SequenceNumber)
                .MaxAsync(cancellationToken) ?? 0) + 1;

            var utcNow = timeProvider.GetUtcNow().UtcDateTime;
            var trackingEvent = TrackingEvent.Create(
                request.ShipmentId,
                request.Status.GetValueOrDefault(),
                request.Location,
                request.Notes,
                request.SourceType,
                occurredAt,
                utcNow,
                createdBy,
                nextSequenceNumber);

            dbContext.TrackingEvents.Add(trackingEvent);
            var outbox = OutboxFactory.Create(trackingEvent, eventId);
            dbContext.OutboxMessages.Add(outbox);

            try
            {
                await dbContext.SaveChangesAsync(cancellationToken);
                await transaction.CommitAsync(cancellationToken);
                logger.LogInformation("Tracking committed EventId={EventId} ShipmentId={ShipmentId} SequenceNumber={SequenceNumber}",
                    eventId, trackingEvent.ShipmentId, trackingEvent.SequenceNumber);

                logger.LogInformation(
                    "Created tracking event {TrackingEventId} with sequence {SequenceNumber} for shipment {ShipmentId}",
                    trackingEvent.Id,
                    trackingEvent.SequenceNumber,
                    trackingEvent.ShipmentId);

                return trackingEvent;
            }
            catch (DbUpdateException exception) when (IsSequenceConflict(exception))
            {
                await transaction.RollbackAsync(cancellationToken);
                dbContext.Entry(trackingEvent).State = EntityState.Detached;
                dbContext.Entry(outbox).State = EntityState.Detached;
                if (attempt == maxAttempts - 1) break;
                await Task.Delay(TimeSpan.FromMilliseconds(Random.Shared.Next(10, 60)), cancellationToken);

                logger.LogWarning(
                    "Retrying tracking event creation because sequence assignment conflicted for shipment {ShipmentId}",
                    request.ShipmentId);
            }
        }

        throw new ConflictException("Unable to assign a sequence number to the tracking event.");
    }

    private static DateTime NormalizeOccurredAt(DateTime occurredAt)
    {
        if (occurredAt == default)
        {
            throw new ValidationException("OccurredAt is required.");
        }

        if (occurredAt.Kind == DateTimeKind.Unspecified)
        {
            throw new ValidationException("OccurredAt must include timezone or UTC information.");
        }

        return occurredAt.Kind == DateTimeKind.Utc
            ? occurredAt
            : occurredAt.ToUniversalTime();
    }

    private static bool IsSequenceConflict(DbUpdateException exception)
    {
        return exception.InnerException is PostgresException
        {
            SqlState: PostgresErrorCodes.UniqueViolation,
            ConstraintName: "IX_TrackingEvents_ShipmentId_SequenceNumber" or "IX_OutboxMessages_AggregateId_AggregateSequence"
        };
    }

    private static void EnsureAccessible(ShipmentSummary shipment, RequestUserContext currentUser)
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
