using Amazon.EventBridge;
using Amazon.EventBridge.Model;
using Microsoft.Extensions.Options;
using TrackingService.Domain.Entities;
using TrackingService.Infrastructure.Configuration;

namespace TrackingService.Infrastructure.Messaging;

public sealed record PublishResult(bool Success, string? ErrorCode, Dictionary<string, object>? Diagnostic = null);

public sealed class EventBridgeTrackingEventPublisher(IAmazonEventBridge eventBridge, IOptions<AwsOptions> options)
{
    public async Task<IReadOnlyList<PublishResult>> PublishAsync(IReadOnlyList<OutboxMessage> batch, CancellationToken cancellationToken)
    {
        if (batch.Count is < 1 or > 10) throw new ArgumentOutOfRangeException(nameof(batch));
        var response = await eventBridge.PutEventsAsync(new PutEventsRequest
        {
            Entries = batch.Select(row => new PutEventsRequestEntry
            {
                EventBusName = options.Value.EventBusName, Source = "tracking-service",
                DetailType = row.EventType, Time = row.CreatedAt, Detail = row.Payload
            }).ToList()
        }, cancellationToken);
        if (response.Entries is null || response.Entries.Count != batch.Count ||
            response.FailedEntryCount != response.Entries.Count(e => !string.IsNullOrEmpty(e.ErrorCode)))
            return batch.Select(_ => new PublishResult(false, "InvalidResponse")).ToArray();
        // ErrorMessage is untrusted and may echo payload. Store a bounded classification only.
        return response.Entries.Select(e =>
        {
            var success = string.IsNullOrEmpty(e.ErrorCode) && !string.IsNullOrEmpty(e.EventId);
            return new PublishResult(success, success ? null : SafeCode(e.ErrorCode), success ? null :
                Observability.SafeDiagnostics.Describe(new Amazon.Runtime.AmazonServiceException(
                    "", null, Amazon.Runtime.ErrorType.Unknown, e.ErrorCode,
                    response.ResponseMetadata?.RequestId, response.HttpStatusCode)));
        }).ToArray();
    }

    public static string SafeCode(string? code) => code switch
    {
        "InternalFailure" or "ThrottlingException" or "AccessDeniedException" or "MalformedDetail" or
        "InvalidArgument" or "RedactionFailure" or "NotAuthorizedForSourceException" or
        "NotAuthorizedForDetailTypeException" => code,
        _ => "PublishFailed"
    };
}
