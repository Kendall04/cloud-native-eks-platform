using System.ComponentModel.DataAnnotations;

namespace ShipmentService.Application.Contracts.Shipments;

public sealed class UpdateShipmentMetadataRequest
{
    [MaxLength(100)]
    public string? ReferenceNumber { get; set; }

    [MaxLength(50)]
    public string? Priority { get; set; }
}
