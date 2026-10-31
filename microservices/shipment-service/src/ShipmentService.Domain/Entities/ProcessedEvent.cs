namespace ShipmentService.Domain.Entities;

public sealed class ProcessedEvent
{
    public string EventId { get; set; } = string.Empty;

    public string EventType { get; set; } = string.Empty;

    public DateTime ProcessedAt { get; set; } = DateTime.UtcNow;
    public Guid? ShipmentId { get; set; }
    public long? SequenceNumber { get; set; }
    public string? Outcome { get; set; }
}
