namespace ShipmentService.Domain.Enums;

public enum ShipmentStatus
{
    CREATED,
    PICKED_UP,
    IN_WAREHOUSE,
    IN_TRANSIT,
    OUT_FOR_DELIVERY,
    DELIVERED,
    DELAYED,
    CANCELLED
}
