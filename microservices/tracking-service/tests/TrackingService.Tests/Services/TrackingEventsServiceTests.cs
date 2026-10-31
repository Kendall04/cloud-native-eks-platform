using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging.Abstractions;
using TrackingService.Application.Common.Authorization;
using TrackingService.Application.Common.Exceptions;
using TrackingService.Application.Contracts.Shipments;
using TrackingService.Application.Contracts.Tracking;
using TrackingService.Application.Interfaces;
using TrackingService.Domain.Constants;
using TrackingService.Domain.Entities;
using TrackingService.Domain.Enums;
using TrackingService.Infrastructure.Persistence;
using TrackingService.Infrastructure.Services;

namespace TrackingService.Tests.Services;

public sealed class TrackingEventsServiceTests
{
    [Fact]
    public async Task CreateAsync_PersistsTrackingEventWithExpectedValues()
    {
        await using var connection = CreateConnection();
        await using var dbContext = CreateDbContext(connection);
        await dbContext.Database.EnsureCreatedAsync();

        var shipmentId = Guid.NewGuid();
        var shipmentLookupService = new FakeShipmentLookupService(new ShipmentSummary(shipmentId, "SHP-TEST123456", "cust-123"));
        var service = new TrackingEventsService(
            dbContext,
            shipmentLookupService,
            new FrozenTimeProvider(new DateTime(2026, 3, 12, 12, 5, 0, DateTimeKind.Utc)),
            NullLogger<TrackingEventsService>.Instance);

        var response = await service.CreateAsync(
            new CreateTrackingEventRequest
            {
                ShipmentId = shipmentId,
                Status = TrackingStatus.IN_TRANSIT,
                Location = "Los Angeles Hub",
                Notes = "Package departed from hub",
                OccurredAt = new DateTime(2026, 3, 12, 12, 0, 0, DateTimeKind.Utc),
                SourceType = TrackingSourceType.ADMIN
            },
            new RequestUserContext("admin-1", "admin@example.com", [ApplicationRoles.Admin]));

        var trackingEvent = await dbContext.TrackingEvents.SingleAsync(candidate => candidate.Id == response.Id);

        Assert.Equal(shipmentId, response.ShipmentId);
        Assert.Equal(TrackingStatus.IN_TRANSIT, response.Status);
        Assert.Equal("Los Angeles Hub", response.Location);
        Assert.Equal("Package departed from hub", response.Notes);
        Assert.Equal(TrackingSourceType.ADMIN, response.SourceType);
        Assert.Equal(1, response.SequenceNumber);
        Assert.Equal("admin-1", trackingEvent.CreatedBy);
        Assert.Single(dbContext.OutboxMessages);
        Assert.Equal(1, shipmentLookupService.ShipmentExistsCalls);
        Assert.Equal(0, shipmentLookupService.GetShipmentByIdCalls);
    }

    [Fact]
    public async Task GetTimelineByShipmentIdAsync_OrdersByOccurredAtThenSequenceNumber()
    {
        await using var connection = CreateConnection();
        await using var dbContext = CreateDbContext(connection);
        await dbContext.Database.EnsureCreatedAsync();

        var shipmentId = Guid.NewGuid();
        dbContext.TrackingEvents.AddRange(
            TrackingEvent.Create(
                shipmentId,
                TrackingStatus.IN_TRANSIT,
                "Los Angeles",
                null,
                TrackingSourceType.SYSTEM,
                new DateTime(2026, 3, 12, 13, 0, 0, DateTimeKind.Utc),
                new DateTime(2026, 3, 12, 13, 1, 0, DateTimeKind.Utc),
                null,
                3),
            TrackingEvent.Create(
                shipmentId,
                TrackingStatus.PICKED_UP,
                "San Jose",
                null,
                TrackingSourceType.SYSTEM,
                new DateTime(2026, 3, 12, 10, 0, 0, DateTimeKind.Utc),
                new DateTime(2026, 3, 12, 10, 1, 0, DateTimeKind.Utc),
                null,
                1),
            TrackingEvent.Create(
                shipmentId,
                TrackingStatus.IN_WAREHOUSE,
                "San Jose Hub",
                null,
                TrackingSourceType.SYSTEM,
                new DateTime(2026, 3, 12, 10, 0, 0, DateTimeKind.Utc),
                new DateTime(2026, 3, 12, 10, 2, 0, DateTimeKind.Utc),
                null,
                2));
        await dbContext.SaveChangesAsync();

        var shipmentLookupService = new FakeShipmentLookupService(new ShipmentSummary(shipmentId, "SHP-TEST123456", "cust-123"));
        var service = new TrackingEventsService(
            dbContext,
            shipmentLookupService,
            new FrozenTimeProvider(new DateTime(2026, 3, 12, 13, 5, 0, DateTimeKind.Utc)),
            NullLogger<TrackingEventsService>.Instance);

        var response = await service.GetTimelineByShipmentIdAsync(
            shipmentId,
            new RequestUserContext("cust-123", "user@example.com", [ApplicationRoles.User]));

        Assert.Collection(
            response,
            first => Assert.Equal(TrackingStatus.PICKED_UP, first.Status),
            second => Assert.Equal(TrackingStatus.IN_WAREHOUSE, second.Status),
            third => Assert.Equal(TrackingStatus.IN_TRANSIT, third.Status));
        Assert.Equal(1, shipmentLookupService.GetShipmentByIdCalls);
    }

    [Fact]
    public async Task GetTimelineByShipmentIdAsync_HidesTimelineFromDifferentCustomer()
    {
        await using var connection = CreateConnection();
        await using var dbContext = CreateDbContext(connection);
        await dbContext.Database.EnsureCreatedAsync();

        var shipmentId = Guid.NewGuid();
        var shipmentLookupService = new FakeShipmentLookupService(new ShipmentSummary(shipmentId, "SHP-TEST123456", "cust-123"));
        var service = new TrackingEventsService(
            dbContext,
            shipmentLookupService,
            new FrozenTimeProvider(new DateTime(2026, 3, 12, 13, 5, 0, DateTimeKind.Utc)),
            NullLogger<TrackingEventsService>.Instance);

        await Assert.ThrowsAsync<NotFoundException>(() => service.GetTimelineByShipmentIdAsync(
            shipmentId,
            new RequestUserContext("cust-999", "user@example.com", [ApplicationRoles.User])));
    }

    [Fact]
    public async Task CreateAsync_PersistsOutboxWithoutNetworkPublisher()
    {
        await using var connection = CreateConnection();
        await using var dbContext = CreateDbContext(connection);
        await dbContext.Database.EnsureCreatedAsync();

        var shipmentId = Guid.NewGuid();
        var shipmentLookupService = new FakeShipmentLookupService(new ShipmentSummary(shipmentId, "SHP-TEST123456", "cust-123"));
        var service = new TrackingEventsService(
            dbContext,
            shipmentLookupService,
            new FrozenTimeProvider(new DateTime(2026, 3, 12, 12, 5, 0, DateTimeKind.Utc)),
            NullLogger<TrackingEventsService>.Instance);

        await service.CreateAsync(
            new CreateTrackingEventRequest
            {
                ShipmentId = shipmentId,
                Status = TrackingStatus.IN_TRANSIT,
                Location = "Los Angeles Hub",
                OccurredAt = new DateTime(2026, 3, 12, 12, 0, 0, DateTimeKind.Utc),
                SourceType = TrackingSourceType.ADMIN
            },
            new RequestUserContext("admin-1", "admin@example.com", [ApplicationRoles.Admin]));

        Assert.Single(dbContext.OutboxMessages);
        Assert.Equal(1, shipmentLookupService.ShipmentExistsCalls);
    }

    [Fact]
    public async Task CreateAsync_FailsWhenShipmentValidationReturnsMissingShipment()
    {
        await using var connection = CreateConnection();
        await using var dbContext = CreateDbContext(connection);
        await dbContext.Database.EnsureCreatedAsync();

        var shipmentLookupService = new FakeShipmentLookupService(null);
        var service = new TrackingEventsService(
            dbContext,
            shipmentLookupService,
            new FrozenTimeProvider(new DateTime(2026, 3, 12, 12, 5, 0, DateTimeKind.Utc)),
            NullLogger<TrackingEventsService>.Instance);

        await Assert.ThrowsAsync<NotFoundException>(() => service.CreateAsync(
            new CreateTrackingEventRequest
            {
                ShipmentId = Guid.NewGuid(),
                Status = TrackingStatus.IN_TRANSIT,
                Location = "Los Angeles Hub",
                OccurredAt = new DateTime(2026, 3, 12, 12, 0, 0, DateTimeKind.Utc),
                SourceType = TrackingSourceType.ADMIN
            },
            new RequestUserContext("admin-1", "admin@example.com", [ApplicationRoles.Admin])));

        Assert.Empty(dbContext.TrackingEvents);
        Assert.Empty(dbContext.OutboxMessages);
        Assert.Equal(1, shipmentLookupService.ShipmentExistsCalls);
    }

    private static SqliteConnection CreateConnection()
    {
        var connection = new SqliteConnection("DataSource=:memory:");
        connection.Open();
        return connection;
    }

    private static TrackingDbContext CreateDbContext(SqliteConnection connection)
    {
        var options = new DbContextOptionsBuilder<TrackingDbContext>()
            .UseSqlite(connection)
            .Options;

        return new TrackingDbContext(options);
    }

    private sealed class FakeShipmentLookupService(ShipmentSummary? shipment) : IShipmentLookupService
    {
        public int ShipmentExistsCalls { get; private set; }

        public int GetShipmentByIdCalls { get; private set; }

        public Task<bool> ShipmentExistsAsync(Guid shipmentId, CancellationToken cancellationToken = default)
        {
            ShipmentExistsCalls += 1;
            return Task.FromResult(shipment is not null && shipment.Id == shipmentId);
        }

        public Task<ShipmentSummary?> GetShipmentByIdAsync(Guid shipmentId, CancellationToken cancellationToken = default)
        {
            GetShipmentByIdCalls += 1;
            return Task.FromResult(shipment is not null && shipment.Id == shipmentId ? shipment : null);
        }

        public Task<ShipmentSummary?> GetShipmentByTrackingNumberAsync(
            string trackingNumber,
            CancellationToken cancellationToken = default) =>
            Task.FromResult(shipment is not null && shipment.TrackingNumber == trackingNumber ? shipment : null);
    }

    private sealed class FrozenTimeProvider(DateTime utcNow) : TimeProvider
    {
        private readonly DateTimeOffset _utcNow = new(utcNow, TimeSpan.Zero);

        public override DateTimeOffset GetUtcNow() => _utcNow;
    }
}
