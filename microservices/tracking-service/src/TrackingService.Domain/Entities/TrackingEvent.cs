using TrackingService.Domain.Enums;

namespace TrackingService.Domain.Entities;

public sealed class TrackingEvent
{
    public Guid Id { get; private set; } = Guid.NewGuid();

    public Guid ShipmentId { get; private set; }

    public TrackingStatus Status { get; private set; }

    public string Location { get; private set; } = string.Empty;

    public string? Notes { get; private set; }

    public TrackingSourceType SourceType { get; private set; }

    public DateTime OccurredAt { get; private set; }

    public DateTime CreatedAt { get; private set; } = DateTime.UtcNow;

    public string? CreatedBy { get; private set; }

    public int SequenceNumber { get; private set; }

    public static TrackingEvent Create(
        Guid shipmentId,
        TrackingStatus status,
        string location,
        string? notes,
        TrackingSourceType sourceType,
        DateTime occurredAt,
        DateTime createdAt,
        string? createdBy,
        int sequenceNumber)
    {
        if (!Enum.IsDefined(status))
            throw new ArgumentOutOfRangeException(nameof(status), "Status must be a defined tracking status.");
        if (!Enum.IsDefined(sourceType))
            throw new ArgumentOutOfRangeException(nameof(sourceType), "SourceType must be a defined tracking source.");

        if (shipmentId == Guid.Empty)
        {
            throw new ArgumentException("ShipmentId is required.", nameof(shipmentId));
        }

        ArgumentException.ThrowIfNullOrWhiteSpace(location);

        if (occurredAt == default)
        {
            throw new ArgumentException("OccurredAt is required.", nameof(occurredAt));
        }

        if (occurredAt.Kind == DateTimeKind.Unspecified)
        {
            throw new ArgumentException("OccurredAt must include UTC information.", nameof(occurredAt));
        }

        if (sequenceNumber <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(sequenceNumber), "Sequence number must be greater than zero.");
        }

        return new TrackingEvent
        {
            Id = Guid.NewGuid(),
            ShipmentId = shipmentId,
            Status = status,
            Location = location.Trim(),
            Notes = Normalize(notes),
            SourceType = sourceType,
            OccurredAt = occurredAt.Kind == DateTimeKind.Utc ? occurredAt : occurredAt.ToUniversalTime(),
            CreatedAt = createdAt.Kind == DateTimeKind.Utc ? createdAt : createdAt.ToUniversalTime(),
            CreatedBy = Normalize(createdBy),
            SequenceNumber = sequenceNumber
        };
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
