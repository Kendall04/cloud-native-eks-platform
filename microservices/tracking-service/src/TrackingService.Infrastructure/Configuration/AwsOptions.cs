using System.ComponentModel.DataAnnotations;

namespace TrackingService.Infrastructure.Configuration;

public sealed class AwsOptions
{
    public const string SectionName = "AWS";

    [Required]
    public string Region { get; set; } = string.Empty;

    [Required]
    public string EventBusName { get; set; } = string.Empty;
}
