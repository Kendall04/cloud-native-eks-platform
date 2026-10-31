namespace ShipmentService.Domain.Enums;

public enum TrackingStatusUpdateOutcome
{
    Applied,
    AppliedWithoutStatusChange,
    IgnoredOutOfOrder,
    RejectedInvalidTransition
}
