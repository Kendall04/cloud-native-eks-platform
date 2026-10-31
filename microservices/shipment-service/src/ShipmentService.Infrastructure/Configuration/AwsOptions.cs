using System.ComponentModel.DataAnnotations;

namespace ShipmentService.Infrastructure.Configuration;

public sealed class AwsOptions
{
    public const string SectionName = "AWS";

    [Required]
    public string Region { get; set; } = string.Empty;

    [Required]
    public string ShipmentEventsQueueUrl { get; set; } = string.Empty;
}
