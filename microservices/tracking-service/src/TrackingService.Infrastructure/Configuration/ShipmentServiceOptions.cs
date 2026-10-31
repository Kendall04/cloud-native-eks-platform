using System.ComponentModel.DataAnnotations;

namespace TrackingService.Infrastructure.Configuration;

public sealed class ShipmentServiceOptions
{
    public const string SectionName = "ShipmentService";

    [Required]
    [Url]
    public string BaseUrl { get; set; } = string.Empty;
}
