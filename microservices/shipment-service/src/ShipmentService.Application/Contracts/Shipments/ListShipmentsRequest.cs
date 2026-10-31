using ShipmentService.Domain.Enums;

namespace ShipmentService.Application.Contracts.Shipments;

public sealed class ListShipmentsRequest
{
    public int PageNumber { get; set; } = 1;

    public int PageSize { get; set; } = 20;

    public ShipmentStatus? Status { get; set; }

    public string? CustomerId { get; set; }
}
