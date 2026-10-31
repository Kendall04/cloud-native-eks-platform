using Amazon;
using Amazon.Runtime;
using Amazon.SQS;
using Amazon.SQS.Model;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using ShipmentService.Application.Contracts.Events;
using ShipmentService.Application.Interfaces;
using ShipmentService.Infrastructure.Configuration;
using ShipmentService.Infrastructure.Messaging;
using Xunit;

namespace EventReliability.Tests;

public sealed class ConsumerTests
{
    private sealed class Processor(Task<TrackingEventHandlingResult> result) : ITrackingEventProcessor
    {
        public Task<TrackingEventHandlingResult> ProcessAsync(string body, CancellationToken ct = default) => result;
    }
    private sealed class Queue : AmazonSQSClient
    {
        public int Deletes; public int Delays;
        public Queue() : base(new AnonymousAWSCredentials(), RegionEndpoint.USEast1) { }
        public override Task<DeleteMessageResponse> DeleteMessageAsync(string url, string receipt, CancellationToken ct = default)
        { Deletes++; return Task.FromResult(new DeleteMessageResponse()); }
        public override Task<ChangeMessageVisibilityResponse> ChangeMessageVisibilityAsync(string url, string receipt, int? delay, CancellationToken ct = default)
        { Assert.Equal(60, delay); Delays++; return Task.FromResult(new ChangeMessageVisibilityResponse()); }
    }
    private static SqsTrackingEventsConsumer Consumer(Queue queue, IServiceProvider provider) => new(queue,
        Options.Create(new AwsOptions { ShipmentEventsQueueUrl = "https://example.invalid/queue" }),
        Options.Create(new ShipmentConsumerOptions()), provider.GetRequiredService<IServiceScopeFactory>(), NullLogger<SqsTrackingEventsConsumer>.Instance);

    [Theory]
    [InlineData(TrackingEventHandlingOutcome.WaitingPredecessor)]
    [InlineData(TrackingEventHandlingOutcome.ShipmentNotFound)]
    [InlineData(TrackingEventHandlingOutcome.BaselineRequired)]
    public async Task RetryableResultDelaysWithoutDelete(TrackingEventHandlingOutcome outcome)
    {
        using var queue = new Queue();
        using var provider = new ServiceCollection().AddScoped<ITrackingEventProcessor>(_ => new Processor(Task.FromResult(new TrackingEventHandlingResult("id", "TrackingStatusUpdated", outcome, Guid.NewGuid())))).BuildServiceProvider();
        using var consumer = Consumer(queue, provider);
        await consumer.HandleAsync(new Message { Body = "body", ReceiptHandle = "receipt" }, default);
        Assert.Equal(0, queue.Deletes); Assert.Equal(1, queue.Delays);
    }

    [Fact]
    public async Task DeleteWaitsForSuccessfulProcessorCompletion()
    {
        var completion = new TaskCompletionSource<TrackingEventHandlingResult>(TaskCreationOptions.RunContinuationsAsynchronously);
        using var queue = new Queue();
        using var provider = new ServiceCollection().AddScoped<ITrackingEventProcessor>(_ => new Processor(completion.Task)).BuildServiceProvider();
        using var consumer = Consumer(queue, provider);
        var task = consumer.HandleAsync(new Message { Body = "body", ReceiptHandle = "receipt" }, default);
        Assert.Equal(0, queue.Deletes);
        completion.SetResult(new("id", "TrackingStatusUpdated", TrackingEventHandlingOutcome.Applied, Guid.NewGuid()));
        await task; Assert.Equal(1, queue.Deletes);
    }

    [Fact]
    public async Task FailedProcessorNeverDeletes()
    {
        using var queue = new Queue();
        using var provider = new ServiceCollection().AddScoped<ITrackingEventProcessor>(_ => new Processor(Task.FromException<TrackingEventHandlingResult>(new InvalidOperationException("UnsupportedTrackingContract")))).BuildServiceProvider();
        using var consumer = Consumer(queue, provider);
        await consumer.HandleAsync(new Message { Body = "body", ReceiptHandle = "receipt" }, default);
        Assert.Equal(0, queue.Deletes); Assert.Equal(0, queue.Delays);
    }
}
