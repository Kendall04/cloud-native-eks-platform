using ShipmentService.Domain.Entities;
using ShipmentService.Domain.Enums;

namespace ShipmentService.Tests.Domain;

public sealed class ShipmentCreationTests
{
    [Fact]
    public void Create_InitializesShipmentWithExpectedDefaults()
    {
        var utcNow = new DateTime(2026, 3, 11, 10, 0, 0, DateTimeKind.Utc);

        var shipment = Shipment.Create(
            "SHP-ABC123456789",
            "cust-123",
            " San Jose ",
            " Tokyo ",
            3.5m,
            " REF-001 ",
            " HIGH ",
            utcNow);

        Assert.Equal("SHP-ABC123456789", shipment.TrackingNumber);
        Assert.Equal("cust-123", shipment.CustomerId);
        Assert.Equal("San Jose", shipment.Origin);
        Assert.Equal("Tokyo", shipment.Destination);
        Assert.Equal(3.5m, shipment.Weight);
        Assert.Equal("REF-001", shipment.ReferenceNumber);
        Assert.Equal("HIGH", shipment.Priority);
        Assert.Equal(ShipmentStatus.CREATED, shipment.Status);
        Assert.Equal(1, shipment.Version);
        Assert.Null(shipment.LastTrackingEventAt);
        Assert.Equal(utcNow, shipment.CreatedAt);
        Assert.Equal(utcNow, shipment.UpdatedAt);
    }
}
