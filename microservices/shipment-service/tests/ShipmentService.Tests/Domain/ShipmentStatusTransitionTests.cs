using ShipmentService.Domain.Entities;
using ShipmentService.Domain.Enums;

namespace ShipmentService.Tests.Domain;

public sealed class ShipmentStatusTransitionTests
{
    [Fact]
    public void ApplyTrackingStatusUpdate_RejectsBackwardTransitionFromDelivered()
    {
        var createdAt = new DateTime(2026, 3, 11, 10, 0, 0, DateTimeKind.Utc);
        var shipment = Shipment.Create(
            "SHP-ABC123456789",
            "cust-123",
            "San Jose",
            "Tokyo",
            3.5m,
            null,
            null,
            createdAt);

        shipment.ApplyTrackingStatusUpdate(ShipmentStatus.PICKED_UP, createdAt.AddMinutes(5), createdAt.AddMinutes(5));
        shipment.ApplyTrackingStatusUpdate(ShipmentStatus.IN_TRANSIT, createdAt.AddMinutes(10), createdAt.AddMinutes(10));
        shipment.ApplyTrackingStatusUpdate(ShipmentStatus.OUT_FOR_DELIVERY, createdAt.AddMinutes(15), createdAt.AddMinutes(15));
        shipment.ApplyTrackingStatusUpdate(ShipmentStatus.DELIVERED, createdAt.AddMinutes(20), createdAt.AddMinutes(20));

        var outcome = shipment.ApplyTrackingStatusUpdate(
            ShipmentStatus.IN_TRANSIT,
            createdAt.AddMinutes(25),
            createdAt.AddMinutes(25));

        Assert.Equal(TrackingStatusUpdateOutcome.RejectedInvalidTransition, outcome);
        Assert.Equal(ShipmentStatus.DELIVERED, shipment.Status);
    }

    [Fact]
    public void ApplyTrackingStatusUpdate_AllowsForwardTransition()
    {
        var createdAt = new DateTime(2026, 3, 11, 10, 0, 0, DateTimeKind.Utc);
        var shipment = Shipment.Create(
            "SHP-XYZ987654321",
            "cust-123",
            "San Jose",
            "Tokyo",
            3.5m,
            null,
            null,
            createdAt);

        var outcome = shipment.ApplyTrackingStatusUpdate(
            ShipmentStatus.PICKED_UP,
            createdAt.AddMinutes(5),
            createdAt.AddMinutes(5));

        Assert.Equal(TrackingStatusUpdateOutcome.Applied, outcome);
        Assert.Equal(ShipmentStatus.PICKED_UP, shipment.Status);
        Assert.Equal(createdAt.AddMinutes(5), shipment.LastTrackingEventAt);
        Assert.Equal(2, shipment.Version);
    }
}
