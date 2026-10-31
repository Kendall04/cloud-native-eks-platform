using ShipmentService.Domain.Enums;

namespace ShipmentService.Domain.Entities;

public sealed class Shipment
{
    private static readonly IReadOnlyDictionary<ShipmentStatus, ShipmentStatus[]> AllowedTransitions =
        new Dictionary<ShipmentStatus, ShipmentStatus[]>
        {
            [ShipmentStatus.CREATED] = [ShipmentStatus.PICKED_UP, ShipmentStatus.IN_WAREHOUSE, ShipmentStatus.DELAYED, ShipmentStatus.CANCELLED],
            [ShipmentStatus.PICKED_UP] = [ShipmentStatus.IN_WAREHOUSE, ShipmentStatus.IN_TRANSIT, ShipmentStatus.DELAYED, ShipmentStatus.CANCELLED],
            [ShipmentStatus.IN_WAREHOUSE] = [ShipmentStatus.IN_TRANSIT, ShipmentStatus.DELAYED, ShipmentStatus.CANCELLED],
            [ShipmentStatus.IN_TRANSIT] = [ShipmentStatus.OUT_FOR_DELIVERY, ShipmentStatus.DELAYED],
            [ShipmentStatus.OUT_FOR_DELIVERY] = [ShipmentStatus.DELIVERED, ShipmentStatus.DELAYED],
            [ShipmentStatus.DELAYED] = [ShipmentStatus.IN_WAREHOUSE, ShipmentStatus.IN_TRANSIT, ShipmentStatus.OUT_FOR_DELIVERY, ShipmentStatus.DELIVERED, ShipmentStatus.CANCELLED],
            [ShipmentStatus.DELIVERED] = [],
            [ShipmentStatus.CANCELLED] = []
        };

    public Guid Id { get; private set; } = Guid.NewGuid();

    public string TrackingNumber { get; private set; } = string.Empty;

    public string CustomerId { get; private set; } = string.Empty;

    public string Origin { get; private set; } = string.Empty;

    public string Destination { get; private set; } = string.Empty;

    public decimal Weight { get; private set; }

    public ShipmentStatus Status { get; private set; } = ShipmentStatus.CREATED;

    public string? ReferenceNumber { get; private set; }

    public string? Priority { get; private set; }

    public DateTime? LastTrackingEventAt { get; private set; }

    public int Version { get; private set; } = 1;
    // Null means historical state has not received an operator-reviewed baseline.
    public long? LastProcessedTrackingSequence { get; private set; }

    public DateTime CreatedAt { get; private set; } = DateTime.UtcNow;

    public DateTime UpdatedAt { get; private set; } = DateTime.UtcNow;

    public static Shipment Create(
        string trackingNumber,
        string customerId,
        string origin,
        string destination,
        decimal weight,
        string? referenceNumber,
        string? priority,
        DateTime utcNow)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(trackingNumber);
        ArgumentException.ThrowIfNullOrWhiteSpace(customerId);
        ArgumentException.ThrowIfNullOrWhiteSpace(origin);
        ArgumentException.ThrowIfNullOrWhiteSpace(destination);

        if (weight <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(weight), "Weight must be greater than zero.");
        }

        return new Shipment
        {
            Id = Guid.NewGuid(),
            TrackingNumber = trackingNumber.Trim(),
            CustomerId = customerId.Trim(),
            Origin = origin.Trim(),
            Destination = destination.Trim(),
            Weight = decimal.Round(weight, 2, MidpointRounding.AwayFromZero),
            ReferenceNumber = Normalize(referenceNumber),
            Priority = Normalize(priority),
            Status = ShipmentStatus.CREATED,
            Version = 1,
            LastProcessedTrackingSequence = 0,
            CreatedAt = utcNow,
            UpdatedAt = utcNow
        };
    }

    public void UpdateMetadata(string? referenceNumber, string? priority, DateTime utcNow)
    {
        ReferenceNumber = Normalize(referenceNumber);
        Priority = Normalize(priority);
        UpdatedAt = utcNow;
        Version += 1;
    }

    public void AdvanceTrackingSequence(long sequence)
    {
        if (LastProcessedTrackingSequence is null || sequence != LastProcessedTrackingSequence + 1)
            throw new InvalidOperationException("Tracking predecessor or baseline missing.");
        LastProcessedTrackingSequence = sequence;
        Version += 1; // Also protects concurrent metadata writes; not the tracking sequence.
    }

    public TrackingStatusUpdateOutcome ApplyTrackingStatusUpdate(
        ShipmentStatus newStatus,
        DateTime eventOccurredAt,
        DateTime utcNow)
    {
        if (LastTrackingEventAt.HasValue && eventOccurredAt < LastTrackingEventAt.Value)
        {
            return TrackingStatusUpdateOutcome.IgnoredOutOfOrder;
        }

        if (Status != newStatus && !CanTransition(Status, newStatus))
        {
            return TrackingStatusUpdateOutcome.RejectedInvalidTransition;
        }

        var statusChanged = Status != newStatus;

        Status = newStatus;
        LastTrackingEventAt = eventOccurredAt;
        UpdatedAt = utcNow;
        Version += 1;

        return statusChanged
            ? TrackingStatusUpdateOutcome.Applied
            : TrackingStatusUpdateOutcome.AppliedWithoutStatusChange;
    }

    private static bool CanTransition(ShipmentStatus currentStatus, ShipmentStatus nextStatus)
    {
        return AllowedTransitions.TryGetValue(currentStatus, out var nextStatuses) &&
               nextStatuses.Contains(nextStatus);
    }

    private static string? Normalize(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        return value.Trim();
    }
}
