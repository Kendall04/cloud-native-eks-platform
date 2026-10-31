using System.ComponentModel.DataAnnotations;

namespace ShipmentService.Application.Contracts.Shipments;

public sealed class CreateShipmentRequest
{
    [Required]
    [MaxLength(100)]
    public string CustomerId { get; set; } = string.Empty;

    [Required]
    [MaxLength(200)]
    public string Origin { get; set; } = string.Empty;

    [Required]
    [MaxLength(200)]
    public string Destination { get; set; } = string.Empty;

    [Range(0.01, 100000)]
    public decimal Weight { get; set; }

    [MaxLength(100)]
    public string? ReferenceNumber { get; set; }

    [MaxLength(50)]
    public string? Priority { get; set; }
}
