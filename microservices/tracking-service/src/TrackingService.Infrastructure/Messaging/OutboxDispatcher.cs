using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using TrackingService.Infrastructure.Configuration;

namespace TrackingService.Infrastructure.Messaging;

public sealed class OutboxDispatcher(IServiceScopeFactory scopes, IOptions<OutboxOptions> options,
    EventBridgeTrackingEventPublisher publisher, ILogger<OutboxDispatcher> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!options.Value.Enabled) return;
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                using var scope = scopes.CreateScope();
                var store = scope.ServiceProvider.GetRequiredService<OutboxStore>();
                var batch = await store.ClaimAsync(options.Value, stoppingToken);
                if (batch.Count > 0)
                {
                    IReadOnlyList<PublishResult> results;
                    using var timeout = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
                    timeout.CancelAfter(TimeSpan.FromSeconds(20));
                    try { results = await publisher.PublishAsync(batch, timeout.Token); }
                    catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
                    catch (Exception error) { Observability.SafeDiagnostics.Log(logger, "EventBridge.PutEvents", error); results = batch.Select(_ => new PublishResult(false, "PublishFailed")).ToArray(); }
                    for (var i = 0; i < batch.Count; i++)
                    {
                        var row = batch[i];
                        var updated = await store.CompleteAsync(row, results[i], options.Value, stoppingToken);
                        Observability.OperationalMetrics.Count(results[i].Success ? "tracking.publish.success" : "tracking.publish.failure");
                        using var diagnosticScope = logger.BeginScope(results[i].Diagnostic ?? new Dictionary<string, object>());
                        logger.LogInformation("Outbox EventId={EventId} ShipmentId={ShipmentId} SequenceNumber={SequenceNumber} Attempt={Attempt} Outcome={Outcome} ErrorCode={ErrorCode}",
                            row.EventId, row.AggregateId, row.AggregateSequence, row.Attempts,
                            updated == 0 ? "StaleLease" : results[i].Success ? "Published" : row.Attempts >= options.Value.MaxAttempts ? "Quarantined" : "RetryScheduled", results[i].ErrorCode);
                    }
                }
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
            catch (Exception error) { Observability.SafeDiagnostics.Log(logger, "Outbox.ClaimOrComplete", error); }
            try { await Task.Delay(TimeSpan.FromSeconds(options.Value.PollIntervalSeconds), stoppingToken); }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
        }
    }
}
