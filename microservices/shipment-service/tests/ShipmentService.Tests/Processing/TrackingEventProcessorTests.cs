using System.Text.Json;
using System.Text.Json.Serialization;
using ShipmentService.Application.Contracts.Events;
using ShipmentService.Domain.Entities;
using ShipmentService.Domain.Enums;
using ShipmentService.Infrastructure.Services;

namespace ShipmentService.Tests.Processing;

public sealed class TrackingEventProcessorTests
{
    [Theory]
    [InlineData("1.0")]
    [InlineData("3.0")]
    public void UnknownContractIsNotPartiallyInterpreted(string version)
    {
        var body = JsonSerializer.Serialize(new EventEnvelope<TrackingStatusUpdatedData>(Guid.NewGuid().ToString(),
            "TrackingStatusUpdated", version, "tracking-service", DateTime.UtcNow,
            new(Guid.NewGuid(), Guid.NewGuid().ToString(), ShipmentStatus.PICKED_UP, "hub", DateTime.UtcNow, 1)),
            new JsonSerializerOptions { Converters = { new JsonStringEnumConverter() } });
        Assert.Throws<InvalidOperationException>(() => TrackingEventProcessor.Parse(body));
    }

    [Theory]
    [InlineData(TrackingEventHandlingOutcome.WaitingPredecessor, false)]
    [InlineData(TrackingEventHandlingOutcome.ShipmentNotFound, false)]
    [InlineData(TrackingEventHandlingOutcome.BaselineRequired, false)]
    [InlineData(TrackingEventHandlingOutcome.RejectedInvalidTransition, true)]
    [InlineData(TrackingEventHandlingOutcome.IgnoredHistorical, true)]
    [InlineData(TrackingEventHandlingOutcome.Duplicate, true)]
    public void AckRequiresDefinitiveOutcome(TrackingEventHandlingOutcome outcome, bool ack) =>
        Assert.Equal(ack, new TrackingEventHandlingResult("id", "TrackingStatusUpdated", outcome).ShouldAcknowledge);

    [Fact]
    public void DomainSequenceIsIndependentOfOptimisticVersion()
    {
        var shipment = Shipment.Create("test", "customer", "origin", "destination", 1, null, null, DateTime.UtcNow);
        shipment.UpdateMetadata("ref", null, DateTime.UtcNow);
        Assert.Equal(2, shipment.Version);
        Assert.Equal(0, shipment.LastProcessedTrackingSequence);
        Assert.Throws<InvalidOperationException>(() => shipment.AdvanceTrackingSequence(2));
        shipment.AdvanceTrackingSequence(1);
        Assert.Equal(1, shipment.LastProcessedTrackingSequence);
    }
}
