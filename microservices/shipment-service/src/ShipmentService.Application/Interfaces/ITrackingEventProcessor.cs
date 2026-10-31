using ShipmentService.Application.Contracts.Events;

namespace ShipmentService.Application.Interfaces;

public interface ITrackingEventProcessor
{
    Task<TrackingEventHandlingResult> ProcessAsync(
        string messageBody,
        CancellationToken cancellationToken = default);
}
