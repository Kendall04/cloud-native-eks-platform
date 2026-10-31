namespace TrackingService.Application.Contracts.Events;

public sealed record EventEnvelope<T>(
    string EventId,
    string EventType,
    string EventVersion,
    string Source,
    DateTime Timestamp,
    T Data);
