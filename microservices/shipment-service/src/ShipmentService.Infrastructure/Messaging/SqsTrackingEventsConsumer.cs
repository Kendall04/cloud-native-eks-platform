using Amazon.SQS;
using Amazon.SQS.Model;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using ShipmentService.Application.Interfaces;
using ShipmentService.Infrastructure.Configuration;

namespace ShipmentService.Infrastructure.Messaging;

public sealed class SqsTrackingEventsConsumer(IAmazonSQS sqs, IOptions<AwsOptions> awsOptions,
    IOptions<ShipmentConsumerOptions> options, IServiceScopeFactory scopes,
    ILogger<SqsTrackingEventsConsumer> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!options.Value.Enabled) return;
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                var response = await sqs.ReceiveMessageAsync(new ReceiveMessageRequest
                {
                    QueueUrl = awsOptions.Value.ShipmentEventsQueueUrl,
                    MaxNumberOfMessages = options.Value.MaxMessagesPerPoll,
                    WaitTimeSeconds = options.Value.WaitTimeSeconds,
                    VisibilityTimeout = options.Value.VisibilityTimeoutSeconds,
                    MessageSystemAttributeNames = ["ApproximateReceiveCount"]
                }, stoppingToken);
                // Start the bounded batch together: later messages do not exhaust visibility waiting locally.
                await Task.WhenAll((response.Messages ?? []).Select(m => HandleAsync(m, stoppingToken)));
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
            catch (Exception exception)
            {
                Observability.SafeDiagnostics.Log(logger, "SQS.ReceiveMessage", exception);
                try { await Task.Delay(TimeSpan.FromSeconds(options.Value.FailureBackoffSeconds), stoppingToken); }
                catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
            }
        }
    }

    public async Task HandleAsync(Message message, CancellationToken stoppingToken)
    {
        var operation = "TrackingEvent.Process";
        try
        {
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
            timeout.CancelAfter(TimeSpan.FromSeconds(options.Value.ProcessingTimeoutSeconds));
            using var scope = scopes.CreateScope();
            var result = await scope.ServiceProvider.GetRequiredService<ITrackingEventProcessor>().ProcessAsync(message.Body, timeout.Token);
            var receiveCount = message.Attributes?.GetValueOrDefault("ApproximateReceiveCount");
            logger.LogInformation("SQS MessageId={MessageId} EventId={EventId} Outcome={Outcome} ReceiveCount={ReceiveCount}", message.MessageId, result.EventId, result.Outcome, receiveCount);
            if (!result.ShouldAcknowledge)
            {
                operation = "SQS.ChangeMessageVisibility";
                await sqs.ChangeMessageVisibilityAsync(awsOptions.Value.ShipmentEventsQueueUrl, message.ReceiptHandle,
                    options.Value.RetryVisibilitySeconds, stoppingToken);
                return;
            }
            // ProcessAsync returns an ACK outcome only after the PostgreSQL transaction committed.
            operation = "SQS.DeleteMessage";
            await sqs.DeleteMessageAsync(awsOptions.Value.ShipmentEventsQueueUrl, message.ReceiptHandle, stoppingToken);
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { }
        catch (Exception exception)
        {
            Observability.SafeDiagnostics.Log(logger, operation, exception);
            var code = exception is InvalidOperationException && exception.Message is
                "UnsupportedTrackingContract" or "InvalidTrackingPayload" or "EventIdentityConflict"
                ? exception.Message : exception is OperationCanceledException ? "ProcessingTimeout" : "ProcessingFailure";
            logger.LogWarning("SQS MessageId={MessageId} ErrorCode={ErrorCode}; retained for retry/DLQ", message.MessageId, code);
        }
    }
}
