namespace TrackingService.Domain.Entities;

public sealed class OutboxMessage
{
    public Guid EventId { get; set; }
    public Guid AggregateId { get; set; }
    public long AggregateSequence { get; set; }
    public string EventType { get; set; } = "TrackingStatusUpdated";
    public string EventVersion { get; set; } = "2.0";
    public string Payload { get; set; } = string.Empty;
    public DateTime CreatedAt { get; set; }
    public DateTime? PublishedAt { get; set; }
    public int Attempts { get; set; }
    public DateTime NextAttemptAt { get; set; }
    public string? LastError { get; set; }
    public DateTime? FailedAt { get; set; }
    public Guid? LeaseToken { get; set; }
    public DateTime? LeaseUntil { get; set; }
}
