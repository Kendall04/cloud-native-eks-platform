using Amazon.Runtime;
using Microsoft.Extensions.Logging;
using Npgsql;
using System.Net;
using System.Net.Sockets;
using System.Text.Json;
using Xunit;
using Tracking = TrackingService.Infrastructure.Observability.SafeDiagnostics;
using Shipment = ShipmentService.Infrastructure.Observability.SafeDiagnostics;

namespace EventReliability.Tests;

public sealed class SafeDiagnosticsTests
{
    private const string Secret = "password=DO_NOT_EMIT_payload_connection_string";
    private sealed class Capture : ILogger
    {
        public List<object> Values { get; } = [];
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull { Values.Add(state); return null; }
        public bool IsEnabled(LogLevel level) => true;
        public void Log<TState>(LogLevel level, EventId id, TState state, Exception? exception, Func<TState, Exception?, string> format)
        { Assert.Null(exception); Values.Add(format(state, exception)); }
    }

    [Theory]
    [InlineData("AccessDeniedException", "Authorization", 403)]
    [InlineData("ThrottlingException", "Throttling", 429)]
    [InlineData("RequestTimeout", "Timeout", 504)]
    public void AwsFailuresRetainCodesAndRequestIdentityWithoutMessages(string code, string category, int status)
    {
        var id = Guid.NewGuid().ToString();
        var error = new AmazonServiceException(Secret, null, ErrorType.Sender, code, id, (HttpStatusCode)status);
        foreach (var fields in new[] { Tracking.Describe(error), Shipment.Describe(error) })
        {
            Assert.Equal(category, fields["ErrorCategory"]);
            Assert.Equal(code, fields["AwsErrorCode"]);
            Assert.Equal(id, fields["AwsRequestId"]);
            Assert.Equal(status, fields["HttpStatusCode"]);
        }
        AssertSafeLogs(error);
    }

    [Fact]
    public void WrappedDatabaseFailureRetainsSqlStateButNotSqlOrDetail()
    {
        var error = new Microsoft.EntityFrameworkCore.DbUpdateException(Secret,
            new PostgresException(Secret, "ERROR", "ERROR", "23505", detail: Secret, tableName: Secret));
        foreach (var fields in new[] { Tracking.Describe(error), Shipment.Describe(error) })
        {
            Assert.Equal("Constraint", fields["ErrorCategory"]);
            Assert.Equal("23505", fields["SqlState"]);
        }
        AssertSafeLogs(error);
    }

    [Fact]
    public void NetworkTimeoutTlsAndCancellationAreDistinct()
    {
        (Exception Error, string Category)[] cases = [
            (new HttpRequestException(Secret, new SocketException()), "Network"),
            (new TimeoutException(Secret), "Timeout"),
            (new OperationCanceledException(Secret), "Timeout"),
            (new System.Security.Authentication.AuthenticationException(Secret), "TLS"),
            (new Exception(Secret), "Unknown")];
        foreach (var (error, category) in cases)
        {
            Assert.Equal(category, Tracking.Describe(error)["ErrorCategory"]);
            Assert.Equal(category, Shipment.Describe(error)["ErrorCategory"]);
            AssertSafeLogs(error);
        }
        Assert.Equal("Cancelled", Tracking.Describe(new OperationCanceledException(), true)["ErrorCategory"]);
    }

    [Fact]
    public void UntrustedAwsCodeAndRequestIdAreNotEchoed()
    {
        var error = new AmazonServiceException(Secret, null, ErrorType.Unknown, Secret, Secret, HttpStatusCode.BadRequest);
        AssertSafeLogs(error);
    }

    private static void AssertSafeLogs(Exception error)
    {
        var logger = new Capture();
        Tracking.Log(logger, "EventBridge.PutEvents", error);
        Shipment.Log(logger, "TrackingEvent.Process", error);
        Assert.DoesNotContain(Secret, JsonSerializer.Serialize(logger.Values));
    }
}
