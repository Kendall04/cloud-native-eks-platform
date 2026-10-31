using Amazon.Runtime;
using Microsoft.Extensions.Logging;
using Npgsql;
using System.Net.Sockets;
using System.Security.Authentication;

namespace ShipmentService.Infrastructure.Observability;

// Kept service-local so independent service build contexts stay self-contained.
// No messages, stack traces, SQL, payloads or arbitrary exception properties.
public static class SafeDiagnostics
{
    public static Dictionary<string, object> Describe(Exception error, bool cancelled = false)
    {
        var result = new Dictionary<string, object>();
        var category = "Unknown";
        var type = "Exception";
        for (var depth = 0; depth < 8 && error is not null; depth++, error = error.InnerException!)
        {
            if (error is PostgresException pg)
            {
                type = nameof(PostgresException);
                category = pg.SqlState.StartsWith("23", StringComparison.Ordinal) ? "Constraint" : "Database";
                if (System.Text.RegularExpressions.Regex.IsMatch(pg.SqlState, "^[0-9A-Z]{5}$")) result["SqlState"] = pg.SqlState;
                break;
            }
            if (error is AmazonServiceException aws)
            {
                type = nameof(AmazonServiceException);
                var code = aws.ErrorCode;
                category = code switch
                {
                    "AccessDenied" or "AccessDeniedException" or "NotAuthorizedForSourceException" or "NotAuthorizedForDetailTypeException" => "Authorization",
                    "Throttling" or "ThrottlingException" or "TooManyRequestsException" => "Throttling",
                    "RequestTimeout" or "RequestTimeoutException" => "Timeout",
                    "ExpiredToken" or "InvalidClientTokenId" => "Authentication",
                    "InternalFailure" or "ServiceUnavailable" => "DependencyUnavailable",
                    "MalformedDetail" or "InvalidArgument" or "RedactionFailure" => "InvalidData",
                    _ => (int)aws.StatusCode switch { 401 => "Authentication", 403 => "Authorization", 429 => "Throttling", >= 500 => "DependencyUnavailable", _ => "Unknown" }
                };
                result["AwsErrorCode"] = code is "AccessDenied" or "AccessDeniedException" or "NotAuthorizedForSourceException" or "NotAuthorizedForDetailTypeException" or "Throttling" or "ThrottlingException" or "TooManyRequestsException" or "RequestTimeout" or "RequestTimeoutException" or "ExpiredToken" or "InvalidClientTokenId" or "InternalFailure" or "ServiceUnavailable" or "MalformedDetail" or "InvalidArgument" or "RedactionFailure" ? code : "UnknownAwsError";
                if ((int)aws.StatusCode is >= 100 and <= 599) result["HttpStatusCode"] = (int)aws.StatusCode;
                if (Guid.TryParseExact(aws.RequestId, "D", out var requestId)) result["AwsRequestId"] = requestId.ToString();
                break;
            }
            if (error is OperationCanceledException) { category = cancelled ? "Cancelled" : "Timeout"; type = nameof(OperationCanceledException); break; }
            if (error is TimeoutException) { category = "Timeout"; type = nameof(TimeoutException); break; }
            if (error is AuthenticationException) { category = "TLS"; type = nameof(AuthenticationException); break; }
            if (error is SocketException) { category = "Network"; type = nameof(SocketException); break; }
            if (error is HttpRequestException http)
            {
                category = "Network"; type = nameof(HttpRequestException);
                if (http.StatusCode is { } status) result["HttpStatusCode"] = (int)status;
                if (error.InnerException is null) break;
            }
            if (error is NpgsqlException) { category = "Database"; type = nameof(NpgsqlException); }
            if (error is System.Text.Json.JsonException) { category = "InvalidData"; type = "JsonException"; break; }
            if (error is InvalidOperationException && error.Message is "UnsupportedTrackingContract" or "InvalidTrackingPayload" or "EventIdentityConflict")
            { category = "InvalidData"; type = nameof(InvalidOperationException); result["ErrorCode"] = error.Message; break; }
        }
        result["ErrorCategory"] = category;
        result["ExceptionType"] = type;
        return result;
    }

    public static void Log(ILogger logger, string operation, Exception error)
    {
        var fields = Describe(error);
        fields["Component"] = "ShipmentService";
        fields["Operation"] = operation;
        using var scope = logger.BeginScope(fields);
        logger.LogWarning("Dependency operation failed Operation={Operation} ErrorCategory={ErrorCategory}", operation, fields["ErrorCategory"]);
    }
}
