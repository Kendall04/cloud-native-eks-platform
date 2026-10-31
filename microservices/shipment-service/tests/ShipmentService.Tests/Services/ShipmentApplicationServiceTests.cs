using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging.Abstractions;
using ShipmentService.Application.Common.Authorization;
using ShipmentService.Application.Common.Exceptions;
using ShipmentService.Application.Contracts.Shipments;
using ShipmentService.Application.Interfaces;
using ShipmentService.Domain.Constants;
using ShipmentService.Domain.Entities;
using ShipmentService.Domain.Enums;
using ShipmentService.Infrastructure.Persistence;
using ShipmentService.Infrastructure.Services;

namespace ShipmentService.Tests.Services;

public sealed class ShipmentApplicationServiceTests
{
    [Fact]
    public async Task CreateAsync_PersistsCreatedShipmentWithoutOutboundEvent()
    {
        await using var connection = new SqliteConnection("DataSource=:memory:");
        await connection.OpenAsync();

        await using var dbContext = CreateDbContext(connection);
        await dbContext.Database.EnsureCreatedAsync();

        var fixedNow = new DateTime(2026, 3, 11, 10, 0, 0, DateTimeKind.Utc);
        var service = new ShipmentApplicationService(
            dbContext,
            new FixedTrackingNumberGenerator("SHP-TEST123456"),
            new FrozenTimeProvider(fixedNow),
            NullLogger<ShipmentApplicationService>.Instance);

        var request = new CreateShipmentRequest
        {
            CustomerId = "cust-123",
            Origin = "San Jose",
            Destination = "Tokyo",
            Weight = 3.5m,
            ReferenceNumber = "REF-001",
            Priority = "HIGH"
        };

        var response = await service.CreateAsync(
            request,
            new RequestUserContext("cust-123", "user@example.com", [ApplicationRoles.User]));

        var shipment = await dbContext.Shipments.SingleAsync(candidate => candidate.Id == response.Id);

        Assert.Equal(ShipmentStatus.CREATED, response.Status);
        Assert.Equal("SHP-TEST123456", response.TrackingNumber);
        Assert.Equal("cust-123", response.CustomerId);
        Assert.Equal("San Jose", shipment.Origin);
        Assert.Equal("Tokyo", shipment.Destination);
        Assert.Equal(1, shipment.Version);
        Assert.Equal(fixedNow, shipment.CreatedAt);
        Assert.Equal(fixedNow, shipment.UpdatedAt);
    }

    [Fact]
    public async Task CreateAsync_RejectsUserCreatingShipmentForDifferentCustomer()
    {
        await using var connection = new SqliteConnection("DataSource=:memory:");
        await connection.OpenAsync();

        await using var dbContext = CreateDbContext(connection);
        await dbContext.Database.EnsureCreatedAsync();

        var service = new ShipmentApplicationService(
            dbContext,
            new FixedTrackingNumberGenerator("SHP-TEST123456"),
            new FrozenTimeProvider(new DateTime(2026, 3, 11, 10, 0, 0, DateTimeKind.Utc)),
            NullLogger<ShipmentApplicationService>.Instance);

        var request = new CreateShipmentRequest
        {
            CustomerId = "cust-456",
            Origin = "San Jose",
            Destination = "Tokyo",
            Weight = 3.5m
        };

        await Assert.ThrowsAsync<ForbiddenAppException>(() => service.CreateAsync(
            request,
            new RequestUserContext("cust-123", "user@example.com", [ApplicationRoles.User])));

        Assert.Empty(dbContext.Shipments);
    }

    private static ShipmentDbContext CreateDbContext(SqliteConnection connection)
    {
        var options = new DbContextOptionsBuilder<ShipmentDbContext>()
            .UseSqlite(connection)
            .Options;

        return new ShipmentDbContext(options);
    }

    private sealed class FixedTrackingNumberGenerator(string trackingNumber) : ITrackingNumberGenerator
    {
        public string Generate() => trackingNumber;
    }

    private sealed class FrozenTimeProvider(DateTime utcNow) : TimeProvider
    {
        private readonly DateTimeOffset _utcNow = new(utcNow, TimeSpan.Zero);

        public override DateTimeOffset GetUtcNow() => _utcNow;
    }
}
