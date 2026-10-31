using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging.Abstractions;
using TrackingService.Application.Common.Authorization;
using TrackingService.Application.Common.Exceptions;
using TrackingService.Application.Contracts.Shipments;
using TrackingService.Application.Contracts.Tracking;
using TrackingService.Application.Interfaces;
using TrackingService.Domain.Entities;
using TrackingService.Domain.Enums;
using TrackingService.Infrastructure.Persistence;
using TrackingService.Infrastructure.Services;

namespace TrackingService.Tests.Services;

public sealed class TrackingValidityTests
{
    [Theory]
    [InlineData(999, 0)]
    [InlineData(0, 999)]
    public void DomainRejectsUndefinedEnums(int status, int source)
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => TrackingEvent.Create(Guid.NewGuid(),
            (TrackingStatus)status, "hub", null, (TrackingSourceType)source,
            DateTime.UtcNow, DateTime.UtcNow, "admin", 1));
    }

    [Theory]
    [InlineData(999, 0)]
    [InlineData(0, 999)]
    public async Task ApplicationRejectsBeforeLookupOrAnyDatabaseOperation(int status, int source)
    {
        // No provider: touching persistence would fail instead of the expected
        // application validation. No SQLite substitutes PostgreSQL here.
        await using var db = new TrackingDbContext(new DbContextOptionsBuilder<TrackingDbContext>().Options);
        var service = new TrackingEventsService(db, new ForbiddenLookup(), TimeProvider.System, NullLogger<TrackingEventsService>.Instance);
        await Assert.ThrowsAsync<ValidationException>(() => service.CreateAsync(new CreateTrackingEventRequest
        {
            ShipmentId = Guid.NewGuid(), Status = (TrackingStatus)status,
            SourceType = (TrackingSourceType)source, Location = "hub", OccurredAt = DateTime.UtcNow
        }, new RequestUserContext("admin", "admin@example.invalid", ["ADMIN"])));
    }

    private sealed class ForbiddenLookup : IShipmentLookupService
    {
        public Task<bool> ShipmentExistsAsync(Guid id, CancellationToken ct = default) => throw new InvalidOperationException("Lookup must not run");
        public Task<ShipmentSummary?> GetShipmentByIdAsync(Guid id, CancellationToken ct = default) => throw new NotSupportedException();
        public Task<ShipmentSummary?> GetShipmentByTrackingNumberAsync(string number, CancellationToken ct = default) => throw new NotSupportedException();
    }
}
