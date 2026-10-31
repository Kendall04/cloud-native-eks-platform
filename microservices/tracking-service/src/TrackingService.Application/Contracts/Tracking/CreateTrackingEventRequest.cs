using System.ComponentModel.DataAnnotations;
using TrackingService.Domain.Enums;

namespace TrackingService.Application.Contracts.Tracking;

public sealed class CreateTrackingEventRequest
{
    public Guid ShipmentId { get; set; }

    [Required]
    public TrackingStatus? Status { get; set; }

    [Required]
    [MaxLength(200)]
    public string Location { get; set; } = string.Empty;

    [MaxLength(500)]
    public string? Notes { get; set; }

    public DateTime OccurredAt { get; set; }

    public TrackingSourceType SourceType { get; set; } = TrackingSourceType.ADMIN;
}
