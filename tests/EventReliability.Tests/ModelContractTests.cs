using Microsoft.EntityFrameworkCore;
using TrackingService.Domain.Entities;
using TrackingService.Infrastructure.Persistence;
using TrackingService.Infrastructure.Messaging;
using TrackingService.Domain.Enums;
using ShipmentService.Infrastructure.Services;
using Xunit;

namespace EventReliability.Tests;

public sealed class ModelContractTests
{
    [Fact]
    public void ConsumerStillRejectsUndefinedStatusFromExternalPayload()
    {
        var now = DateTime.UtcNow;
        var tracking = TrackingEvent.Create(Guid.NewGuid(), TrackingStatus.PICKED_UP, "hub", null, TrackingSourceType.ADMIN, now, now, "admin", 1);
        var payload = System.Text.Json.Nodes.JsonNode.Parse(OutboxFactory.Create(tracking, Guid.NewGuid()).Payload)!;
        payload["data"]!["status"] = 999;
        Assert.Throws<InvalidOperationException>(() => TrackingEventProcessor.Parse(payload.ToJsonString()));
    }

    [Fact]
    public void PostgreSqlModelHasStableUniqueIdentityAndAggregateSequence()
    {
        using var db = new TrackingDbContext(new DbContextOptionsBuilder<TrackingDbContext>().UseNpgsql("Host=localhost;Database=model_only").Options);
        var entity = db.Model.FindEntityType(typeof(OutboxMessage))!;
        Assert.Equal("tracking", entity.GetSchema());
        Assert.Equal("EventId", Assert.Single(entity.FindPrimaryKey()!.Properties).Name);
        Assert.Contains(entity.GetIndexes(), i => i.IsUnique && i.Properties.Select(p => p.Name).SequenceEqual(new[] { "AggregateId", "AggregateSequence" }));
        Assert.Equal("jsonb", entity.FindProperty("Payload")!.GetColumnType());
    }

    [Fact]
    public void RealProducerEnvelopeIsAcceptedByRealConsumerParser()
    {
        var now = DateTime.UtcNow;
        var tracking = TrackingEvent.Create(Guid.NewGuid(), TrackingStatus.PICKED_UP, "hub", null, TrackingSourceType.ADMIN, now, now, "admin", 7);
        var eventId = Guid.NewGuid();
        var row = OutboxFactory.Create(tracking, eventId);
        var parsed = TrackingEventProcessor.Parse(row.Payload);
        Assert.Equal("2.0", parsed.EventVersion); Assert.Equal(eventId.ToString(), parsed.EventId);
        Assert.Equal(7, parsed.Data.SequenceNumber); Assert.Equal(tracking.OccurredAt, parsed.Data.EventOccurredAt);
        Assert.Equal(tracking.Id.ToString(), parsed.Data.TrackingEventId);
    }
}
