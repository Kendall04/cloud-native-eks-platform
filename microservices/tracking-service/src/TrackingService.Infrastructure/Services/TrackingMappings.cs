using TrackingService.Application.Contracts.Tracking;
using TrackingService.Domain.Entities;

namespace TrackingService.Infrastructure.Services;

internal static class TrackingMappings
{
    public static TrackingEventResponse ToResponse(TrackingEvent trackingEvent) =>
        new(
            trackingEvent.Id,
            trackingEvent.ShipmentId,
            trackingEvent.Status,
            trackingEvent.Location,
            trackingEvent.Notes,
            trackingEvent.SourceType,
            trackingEvent.OccurredAt,
            trackingEvent.CreatedAt,
            trackingEvent.CreatedBy,
            trackingEvent.SequenceNumber);
}
