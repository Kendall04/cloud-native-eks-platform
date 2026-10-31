using Amazon;
using Amazon.EventBridge;
using Amazon.EventBridge.Model;
using Amazon.Runtime;
using Microsoft.Extensions.Options;
using TrackingService.Domain.Entities;
using TrackingService.Infrastructure.Configuration;
using TrackingService.Infrastructure.Messaging;
using Xunit;

namespace EventReliability.Tests;

public sealed class PublisherTests
{
    private sealed class FakeBridge(PutEventsResponse response) : AmazonEventBridgeClient(new AnonymousAWSCredentials(), RegionEndpoint.USEast1)
    {
        public List<PutEventsRequest> Requests { get; } = [];
        public override Task<PutEventsResponse> PutEventsAsync(PutEventsRequest request, CancellationToken cancellationToken = default)
        {
            Requests.Add(request);
            return Task.FromResult(response);
        }
    }

    [Fact]
    public async Task PartialFailureIsPerEntryAndRetriesPreservePayload()
    {
        using var bridge = new FakeBridge(new PutEventsResponse { FailedEntryCount = 1, Entries = [
            new() { EventId = "aws-accepted" }, new() { ErrorCode = "ThrottlingException", ErrorMessage = "untrusted detail" }] });
        var publisher = new EventBridgeTrackingEventPublisher(bridge, Options.Create(new AwsOptions { EventBusName = "test-bus" }));
        OutboxMessage[] rows = [new() { Payload = "{\"eventId\":\"stable-one\"}" }, new() { Payload = "{\"eventId\":\"stable-two\"}" }];
        var results = await publisher.PublishAsync(rows, default);
        Assert.True(results[0].Success); Assert.False(results[1].Success);
        Assert.Null(results[0].ErrorCode);
        Assert.Equal("ThrottlingException", results[1].ErrorCode);
        Assert.Equal("Throttling", results[1].Diagnostic!["ErrorCategory"]);
        Assert.DoesNotContain("untrusted detail", System.Text.Json.JsonSerializer.Serialize(results));
        await publisher.PublishAsync(rows, default);
        Assert.Equal(bridge.Requests[0].Entries.Select(e => e.Detail), bridge.Requests[1].Entries.Select(e => e.Detail));
        Assert.All(bridge.Requests[0].Entries, e => Assert.Equal("test-bus", e.EventBusName));
    }

    [Fact]
    public async Task MissingPerEntryConfirmationIsNotSuccess()
    {
        using var bridge = new FakeBridge(new PutEventsResponse { FailedEntryCount = 0, Entries = [] });
        var publisher = new EventBridgeTrackingEventPublisher(bridge, Options.Create(new AwsOptions()));
        Assert.False((await publisher.PublishAsync([new OutboxMessage()], default))[0].Success);
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(() => publisher.PublishAsync(Enumerable.Range(0,11).Select(_ => new OutboxMessage()).ToArray(), default));
    }

    [Fact]
    public void RetryIsBoundedAndErrorClassificationDoesNotEchoSecrets()
    {
        var options = new OutboxOptions();
        Assert.True(options.RetryDelay(2, 1) > options.RetryDelay(1, 1));
        Assert.True(options.RetryDelay(100, 1).TotalSeconds <= options.MaxRetryDelaySeconds);
        Assert.Equal("PublishFailed", EventBridgeTrackingEventPublisher.SafeCode("password=never-log-this"));
    }
}
