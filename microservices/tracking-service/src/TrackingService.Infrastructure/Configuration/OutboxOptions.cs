using System.ComponentModel.DataAnnotations;

namespace TrackingService.Infrastructure.Configuration;

public sealed class OutboxOptions
{
    public const string SectionName = "Outbox";
    public bool Enabled { get; set; } = true;
    [Range(1, 10)] public int BatchSize { get; set; } = 10;
    [Range(1, 60)] public int PollIntervalSeconds { get; set; } = 2;
    [Range(30, 300)] public int LeaseDurationSeconds { get; set; } = 60;
    [Range(1, 100)] public int MaxAttempts { get; set; } = 12;
    [Range(1, 60)] public int BaseRetryDelaySeconds { get; set; } = 2;
    [Range(60, 3600)] public int MaxRetryDelaySeconds { get; set; } = 300;

    public TimeSpan RetryDelay(int attempts, double jitter) => TimeSpan.FromSeconds(
        Math.Min(MaxRetryDelaySeconds, BaseRetryDelaySeconds * Math.Pow(2, Math.Min(attempts - 1, 20))) * (0.5 + Math.Clamp(jitter, 0, 1) * 0.5));
}
