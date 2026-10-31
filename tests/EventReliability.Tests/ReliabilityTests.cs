using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging.Abstractions;
using TrackingService.Application.Contracts.Tracking;
using TrackingService.Application.Common.Authorization;
using TrackingService.Application.Contracts.Shipments;
using TrackingService.Application.Interfaces;
using TrackingService.Domain.Entities;
using TrackingService.Domain.Enums;
using TrackingService.Infrastructure.Services;
using TrackingService.Infrastructure.Messaging;
using TrackingService.Infrastructure.Configuration;
using ShipmentService.Application.Contracts.Events;
using ShipmentService.Infrastructure.Services;
using Xunit;
using ShipmentEntity = ShipmentService.Domain.Entities.Shipment;
using ShipmentStatus = ShipmentService.Domain.Enums.ShipmentStatus;

namespace EventReliability.Tests;

public sealed class ReliabilityTests : PostgresFixture
{
    [PostgresFact]
    public async Task InvalidStatusConsumesNeitherRowsNorSequence()
    {
        var shipmentId = Guid.NewGuid();
        await Write(shipmentId);
        await using (var db = Tracking())
        {
            var service = new TrackingEventsService(db, new Lookup(shipmentId), TimeProvider.System, NullLogger<TrackingEventsService>.Instance);
            await Assert.ThrowsAsync<TrackingService.Application.Common.Exceptions.ValidationException>(() => service.CreateAsync(
                new CreateTrackingEventRequest { ShipmentId = shipmentId, Status = (TrackingStatus)999, Location = "hub", OccurredAt = DateTime.UtcNow },
                new RequestUserContext("admin", "admin@example.invalid", ["ADMIN"])));
            Assert.Equal(1, await db.TrackingEvents.CountAsync());
            Assert.Equal(1, await db.OutboxMessages.CountAsync());
            Assert.Equal(1, await db.TrackingEvents.MaxAsync(x => x.SequenceNumber));
        }
        await Write(shipmentId);
        await using var verify = Tracking();
        Assert.Equal(new[] { 1, 2 }, await verify.TrackingEvents.OrderBy(x => x.SequenceNumber).Select(x => x.SequenceNumber).ToArrayAsync());
        Assert.Equal(2, await verify.OutboxMessages.CountAsync());
    }

    [PostgresFact]
    public async Task OutboxTelemetryReflectsDurableBacklogAndFailure()
    {
        await using var db = Tracking();
        var pending = Event(Guid.NewGuid(), 1);
        pending.CreatedAt = DateTime.UtcNow.AddMinutes(-2);
        var failed = Event(Guid.NewGuid(), 1);
        failed.FailedAt = DateTime.UtcNow;
        var published = Event(Guid.NewGuid(), 1);
        published.PublishedAt = DateTime.UtcNow;
        db.OutboxMessages.AddRange(pending, failed, published);
        await db.SaveChangesAsync();
        var snapshot = await TrackingService.Infrastructure.Observability.OutboxMetricsService.ReadSnapshotAsync(db);
        Assert.Equal(1, snapshot.Pending);
        Assert.Equal(1, snapshot.Failed);
        Assert.True(snapshot.OldestAge >= 110);
    }

    [PostgresFact]
    public async Task InboxFailureRollsBackStateAndSequence()
    {
        var shipment = await SeedShipment();
        await Sql("ALTER TABLE shipment.\"ProcessedEvents\" ADD CONSTRAINT injected_failure CHECK (\"Outcome\" = 'never')");
        await Assert.ThrowsAsync<DbUpdateException>(() => Process(Event(shipment.Id, 1)));
        await using var db = Shipment();
        var current = await db.Shipments.SingleAsync();
        Assert.Equal(ShipmentStatus.CREATED, current.Status);
        Assert.Equal(0, current.LastProcessedTrackingSequence);
        Assert.Empty(await db.ProcessedEvents.ToListAsync());
    }

    [PostgresFact]
    public async Task OperatorRequeuePreservesContractAndRejectsPublishedRow()
    {
        var row = Event(Guid.NewGuid(), 1);
        row.FailedAt = DateTime.UtcNow; row.Attempts = 12; row.LastError = "ThrottlingException";
        await using (var db = Tracking()) { db.OutboxMessages.Add(row); await db.SaveChangesAsync(); }
        OutboxMessage before;
        await using (var db = Tracking()) { before = await db.OutboxMessages.AsNoTracking().SingleAsync(); }
        // jsonb may reorder properties and whitespace on the initial INSERT.
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(row.Payload), JsonNode.Parse(before.Payload)));
        Assert.Equal(0, await Recovery("requeue", "--event-id", row.EventId.ToString()));
        string publishedState;
        await using (var db = Tracking())
        {
            var restored = await db.OutboxMessages.SingleAsync();
            Assert.Equal(before.EventId, restored.EventId);
            Assert.Equal(before.AggregateId, restored.AggregateId);
            Assert.Equal(before.AggregateSequence, restored.AggregateSequence);
            Assert.Equal(before.EventType, restored.EventType);
            Assert.Equal(before.EventVersion, restored.EventVersion);
            Assert.True(JsonNode.DeepEquals(JsonNode.Parse(before.Payload), JsonNode.Parse(restored.Payload)));
            Assert.Null(restored.FailedAt); Assert.Equal(0, restored.Attempts);
            restored.PublishedAt = DateTime.UtcNow; await db.SaveChangesAsync();
            await db.Entry(restored).ReloadAsync();
            publishedState = JsonSerializer.Serialize(restored);
        }
        Assert.NotEqual(0, await Recovery("requeue", "--event-id", row.EventId.ToString()));
        await using var verify = Tracking();
        var afterRejection = await verify.OutboxMessages.AsNoTracking().SingleAsync();
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(publishedState), JsonSerializer.SerializeToNode(afterRejection)));
    }

    private async Task<int> Recovery(params string[] args)
    {
        var root = new DirectoryInfo(AppContext.BaseDirectory);
        while (root is not null && !Directory.Exists(Path.Combine(root.FullName, "scripts", "operations"))) root = root.Parent;
        Assert.NotNull(root);
        var start = new System.Diagnostics.ProcessStartInfo("python") { RedirectStandardOutput = true, RedirectStandardError = true };
        start.ArgumentList.Add(Path.Combine(root!.FullName, "scripts", "operations", "events.py"));
        foreach (var arg in args) start.ArgumentList.Add(arg);
        var c = new Npgsql.NpgsqlConnectionStringBuilder(Connection);
        start.Environment["R5_OPERATOR_DSN"] = $"postgresql://{Uri.EscapeDataString(c.Username!)}:{Uri.EscapeDataString(c.Password ?? "")}@{c.Host}:{c.Port}/{c.Database}?sslmode=disable";
        using var process = System.Diagnostics.Process.Start(start)!;
        var output = process.StandardOutput.ReadToEndAsync(); var error = process.StandardError.ReadToEndAsync();
        await process.WaitForExitAsync(); await output; await error;
        return process.ExitCode;
    }

    private static readonly OutboxOptions Options = new() { BatchSize = 5 };
    private sealed class Lookup(Guid id) : IShipmentLookupService
    {
        public Task<bool> ShipmentExistsAsync(Guid value, CancellationToken ct = default) => Task.FromResult(value == id);
        public Task<ShipmentSummary?> GetShipmentByIdAsync(Guid value, CancellationToken ct = default) => Task.FromResult<ShipmentSummary?>(new(id,"test","customer"));
        public Task<ShipmentSummary?> GetShipmentByTrackingNumberAsync(string value, CancellationToken ct = default) => GetShipmentByIdAsync(id,ct);
    }
    private async Task Write(Guid shipmentId)
    {
        await using var db = Tracking();
        var service = new TrackingEventsService(db, new Lookup(shipmentId), TimeProvider.System, NullLogger<TrackingEventsService>.Instance);
        await service.CreateAsync(new CreateTrackingEventRequest { ShipmentId = shipmentId, Status = TrackingStatus.PICKED_UP,
            Location = "hub", OccurredAt = DateTime.UtcNow, SourceType = TrackingSourceType.ADMIN },
            new RequestUserContext("admin", "admin@example.invalid", ["ADMIN"]));
    }
    private async Task<ShipmentEntity> SeedShipment()
    {
        var shipment = ShipmentEntity.Create(Guid.NewGuid().ToString(), "customer", "origin", "destination", 1, null, null, DateTime.UtcNow);
        await using var db = Shipment(); db.Shipments.Add(shipment); await db.SaveChangesAsync(); return shipment;
    }
    private static OutboxMessage Event(Guid shipment, long sequence, TrackingStatus status = TrackingStatus.PICKED_UP, DateTime? occurred = null)
    {
        var tracking = TrackingEvent.Create(shipment,status,"hub",null,TrackingSourceType.ADMIN,occurred ?? DateTime.UtcNow,DateTime.UtcNow,"admin",(int)sequence);
        return OutboxFactory.Create(tracking, Guid.NewGuid());
    }
    private async Task<TrackingEventHandlingResult> Process(OutboxMessage message)
    {
        await using var db = Shipment();
        return await new TrackingEventProcessor(db, TimeProvider.System, NullLogger<TrackingEventProcessor>.Instance).ProcessAsync(message.Payload);
    }

    [PostgresFact]
    public async Task BusinessAndOutboxCommitTogether()
    {
        await Write(Guid.NewGuid());
        await using var db = Tracking();
        Assert.Single(await db.TrackingEvents.ToListAsync()); Assert.Single(await db.OutboxMessages.ToListAsync());
    }
    [PostgresFact]
    public async Task OutboxInsertFailureRollsBackBusiness()
    {
        await Sql("ALTER TABLE tracking.\"OutboxMessages\" ADD CONSTRAINT injected_failure CHECK (\"Attempts\" < 0)");
        await Assert.ThrowsAsync<DbUpdateException>(() => Write(Guid.NewGuid()));
        await using var db = Tracking(); Assert.Empty(await db.TrackingEvents.ToListAsync()); Assert.Empty(await db.OutboxMessages.ToListAsync());
    }
    [PostgresFact]
    public async Task BusinessInsertFailureLeavesNoOutbox()
    {
        await Sql("ALTER TABLE tracking.\"TrackingEvents\" ADD CONSTRAINT injected_failure CHECK (\"SequenceNumber\" < 0)");
        await Assert.ThrowsAsync<DbUpdateException>(() => Write(Guid.NewGuid()));
        await using var db = Tracking(); Assert.Empty(await db.TrackingEvents.ToListAsync()); Assert.Empty(await db.OutboxMessages.ToListAsync());
    }
    [PostgresFact]
    public async Task ConcurrentSequenceAllocationRetriesWholeUnit()
    {
        var id = Guid.NewGuid(); await Task.WhenAll(Enumerable.Range(0,4).Select(_ => Write(id)));
        await using var db = Tracking();
        Assert.Equal(new[] {1,2,3,4}, await db.TrackingEvents.OrderBy(x=>x.SequenceNumber).Select(x=>x.SequenceNumber).ToArrayAsync());
        Assert.Equal(new long[] {1,2,3,4}, await db.OutboxMessages.OrderBy(x=>x.AggregateSequence).Select(x=>x.AggregateSequence).ToArrayAsync());
    }
    [PostgresFact]
    public async Task TwoDispatchersClaimDisjointRows()
    {
        await using (var db = Tracking()) { db.OutboxMessages.AddRange(Enumerable.Range(1,10).Select(n=>Event(Guid.NewGuid(),n))); await db.SaveChangesAsync(); }
        await using var first = Tracking(); await using var second = Tracking();
        var claims = await Task.WhenAll(new OutboxStore(first).ClaimAsync(Options,default),new OutboxStore(second).ClaimAsync(Options,default));
        Assert.Equal(10,claims.Sum(x=>x.Count)); Assert.Equal(10,claims.SelectMany(x=>x).Select(x=>x.EventId).Distinct().Count());
    }
    [PostgresFact]
    public async Task StaleLeaseCannotCompleteAfterAnotherClaim()
    {
        await Write(Guid.NewGuid()); await using var db = Tracking(); var store = new OutboxStore(db);
        var first = Assert.Single(await store.ClaimAsync(Options,default));
        await Sql("UPDATE tracking.\"OutboxMessages\" SET \"LeaseUntil\" = clock_timestamp() - interval '1 second'");
        var second = Assert.Single(await store.ClaimAsync(Options,default));
        Assert.NotEqual(first.LeaseToken,second.LeaseToken);
        Assert.Equal(0,await store.CompleteAsync(first,new(true,null),Options,default));
        Assert.Equal(1,await store.CompleteAsync(second,new(true,null),Options,default));
    }
    [PostgresFact]
    public async Task AcceptedThenCrashRepublishesSameIdWithOneEffect()
    {
        var shipment = await SeedShipment(); await Write(shipment.Id);
        await using var db = Tracking(); var store = new OutboxStore(db);
        var first = Assert.Single(await store.ClaimAsync(Options,default));
        Assert.Equal(TrackingEventHandlingOutcome.Applied,(await Process(first)).Outcome); // AWS delivery simulated, PostgreSQL real.
        await Sql("UPDATE tracking.\"OutboxMessages\" SET \"LeaseUntil\" = clock_timestamp() - interval '1 second'");
        var replay = Assert.Single(await store.ClaimAsync(Options,default));
        Assert.Equal(first.EventId,replay.EventId); Assert.Equal(first.Payload,replay.Payload);
        Assert.Equal(TrackingEventHandlingOutcome.Duplicate,(await Process(replay)).Outcome);
        await using var consumer = Shipment(); Assert.Single(await consumer.ProcessedEvents.ToListAsync());
    }
    [PostgresFact]
    public async Task TwoBeforeOneWaitsThenMatchesOrderedDelivery()
    {
        var shipment = await SeedShipment(); var first = Event(shipment.Id,1); var second = Event(shipment.Id,2,TrackingStatus.IN_TRANSIT);
        var future = await Process(second); Assert.False(future.ShouldAcknowledge); Assert.Equal(TrackingEventHandlingOutcome.WaitingPredecessor,future.Outcome);
        await using (var db = Shipment()) { Assert.Empty(await db.ProcessedEvents.ToListAsync()); Assert.Equal(0,(await db.Shipments.SingleAsync()).LastProcessedTrackingSequence); }
        Assert.True((await Process(first)).ShouldAcknowledge); Assert.True((await Process(second)).ShouldAcknowledge);
        await using var check = Shipment(); var state = await check.Shipments.SingleAsync(); Assert.Equal(2,state.LastProcessedTrackingSequence); Assert.Equal(ShipmentStatus.IN_TRANSIT,state.Status);
    }
    [PostgresFact]
    public async Task ConcurrentDuplicateHasOneBusinessEffect()
    {
        var shipment = await SeedShipment(); var message = Event(shipment.Id,1);
        var results = await Task.WhenAll(Process(message),Process(message));
        Assert.Single(results.Where(x=>x.Outcome==TrackingEventHandlingOutcome.Applied)); Assert.Single(results.Where(x=>x.Outcome==TrackingEventHandlingOutcome.Duplicate));
        await using var db = Shipment(); Assert.Single(await db.ProcessedEvents.ToListAsync()); Assert.Equal(1,(await db.Shipments.SingleAsync()).LastProcessedTrackingSequence);
    }
    [PostgresFact]
    public async Task InvalidInOrderAndHistoricalAreDefinitive()
    {
        var shipment = await SeedShipment(); var now = DateTime.UtcNow;
        var future = Event(shipment.Id,2,TrackingStatus.DELIVERED);
        Assert.Equal(TrackingEventHandlingOutcome.WaitingPredecessor,(await Process(future)).Outcome);
        await Process(Event(shipment.Id,1,occurred:now));
        Assert.Equal(TrackingEventHandlingOutcome.RejectedInvalidTransition,(await Process(future)).Outcome);
        Assert.Equal(TrackingEventHandlingOutcome.IgnoredHistorical,(await Process(Event(shipment.Id,3,TrackingStatus.IN_TRANSIT,now.AddHours(-1)))).Outcome);
        await using var db = Shipment(); Assert.Equal(3,(await db.Shipments.SingleAsync()).LastProcessedTrackingSequence); Assert.Equal(3,await db.ProcessedEvents.CountAsync());
    }
    [PostgresFact]
    public async Task MissingShipmentAndUnknownVersionNeverEnterInbox()
    {
        var message = Event(Guid.NewGuid(),1); Assert.False((await Process(message)).ShouldAcknowledge);
        message.Payload=message.Payload.Replace("2.0","99.0");
        await Assert.ThrowsAsync<InvalidOperationException>(()=>Process(message));
        await using var db = Shipment(); Assert.Empty(await db.ProcessedEvents.ToListAsync());
    }
    [PostgresFact]
    public async Task MissingBaselineBlocksAndOldSequenceCannotReapply()
    {
        var shipment = await SeedShipment();
        await Sql("UPDATE shipment.\"Shipments\" SET \"LastProcessedTrackingSequence\" = NULL");
        Assert.Equal(TrackingEventHandlingOutcome.BaselineRequired,(await Process(Event(shipment.Id,1))).Outcome);
        await Sql("UPDATE shipment.\"Shipments\" SET \"LastProcessedTrackingSequence\" = 1");
        Assert.Equal(TrackingEventHandlingOutcome.RejectedSequenceConflict,(await Process(Event(shipment.Id,1))).Outcome);
        await using var db = Shipment(); Assert.Equal(ShipmentStatus.CREATED,(await db.Shipments.SingleAsync()).Status);
    }
    [PostgresFact]
    public async Task DurableRetryThenQuarantine()
    {
        await Write(Guid.NewGuid()); await using var db = Tracking(); var store = new OutboxStore(db);
        var row = Assert.Single(await store.ClaimAsync(Options,default));
        await store.CompleteAsync(row,new(false,"ThrottlingException"),new OutboxOptions { BaseRetryDelaySeconds = 60 },default);
        Assert.Empty(await store.ClaimAsync(Options,default));
        await Sql("UPDATE tracking.\"OutboxMessages\" SET \"NextAttemptAt\" = clock_timestamp() - interval '1 second'");
        row=Assert.Single(await store.ClaimAsync(Options,default));
        await store.CompleteAsync(row,new(false,"ThrottlingException"),new OutboxOptions {MaxAttempts=2},default);
        Assert.NotNull((await db.OutboxMessages.AsNoTracking().SingleAsync()).FailedAt);
        Assert.Empty(await store.ClaimAsync(Options,default));
    }
}
