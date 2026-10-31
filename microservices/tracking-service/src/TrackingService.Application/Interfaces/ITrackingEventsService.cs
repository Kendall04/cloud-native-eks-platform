using TrackingService.Application.Common.Authorization;
using TrackingService.Application.Contracts.Tracking;

namespace TrackingService.Application.Interfaces;

public interface ITrackingEventsService
{
    Task<IReadOnlyCollection<TrackingEventResponse>> GetTimelineByShipmentIdAsync(
        Guid shipmentId,
        RequestUserContext currentUser,
        CancellationToken cancellationToken = default);

    Task<IReadOnlyCollection<TrackingEventResponse>> GetTimelineByTrackingNumberAsync(
        string trackingNumber,
        RequestUserContext currentUser,
        CancellationToken cancellationToken = default);

    Task<TrackingEventResponse> CreateAsync(
        CreateTrackingEventRequest request,
        RequestUserContext currentUser,
        CancellationToken cancellationToken = default);
}
