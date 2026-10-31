using System.ComponentModel.DataAnnotations;

namespace ShipmentService.Infrastructure.Configuration;

public sealed class ShipmentConsumerOptions
{
    public const string SectionName = "ShipmentConsumer";
    public bool Enabled { get; set; } = true;
    [Range(30, 900)] public int RetryVisibilitySeconds { get; set; } = 60;
    [Range(60, 900)] public int VisibilityTimeoutSeconds { get; set; } = 120;
    [Range(5, 30)] public int ProcessingTimeoutSeconds { get; set; } = 20;

    [Range(1, 10)]
    public int MaxMessagesPerPoll { get; set; } = 5;

    [Range(1, 20)]
    public int WaitTimeSeconds { get; set; } = 20;

    [Range(1, 300)]
    public int FailureBackoffSeconds { get; set; } = 5;
}
