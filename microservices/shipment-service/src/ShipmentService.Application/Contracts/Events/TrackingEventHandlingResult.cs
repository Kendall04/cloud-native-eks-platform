namespace ShipmentService.Application.Contracts.Events;

public sealed record TrackingEventHandlingResult(
    string EventId,
    string EventType,
    TrackingEventHandlingOutcome Outcome,
    Guid? ShipmentId = null)
{
    public bool ShouldAcknowledge => Outcome is not (TrackingEventHandlingOutcome.WaitingPredecessor
        or TrackingEventHandlingOutcome.ShipmentNotFound or TrackingEventHandlingOutcome.BaselineRequired);
}
