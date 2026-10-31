using System.Text.Json;
using ShipmentService.Infrastructure.Observability;
using Xunit;

namespace ShipmentService.Tests;

public class OperationalMetricsTests
{
    [Fact]
    public void Emf_has_root_metadata_bounded_dimensions_and_units()
    {
        using var doc = JsonDocument.Parse(OperationalMetrics.Serialize(new Dictionary<string,double>
            { ["http.requests"] = 3, ["tracking.outbox.oldest_age"] = 42 }, "dev", 1000));
        var root = doc.RootElement;
        var metrics = root.GetProperty("_aws").GetProperty("CloudWatchMetrics")[0];
        Assert.Equal("Platform/Operations", metrics.GetProperty("Namespace").GetString());
        Assert.Equal(new[] {"Environment", "Service"}, metrics.GetProperty("Dimensions")[0].EnumerateArray().Select(v => v.GetString()));
        Assert.Equal("shipment", root.GetProperty("Service").GetString());
        Assert.Equal(3, root.GetProperty("http.requests").GetDouble());
        Assert.Equal("Seconds", metrics.GetProperty("Metrics")[1].GetProperty("Unit").GetString());
        Assert.DoesNotContain("EventId", root.ToString());
    }
    [Theory]
    [InlineData("EventId", 1)]
    [InlineData("http.requests", -1)]
    [InlineData("http.requests", double.NaN)]
    public void Unbounded_or_invalid_metrics_rejected(string name, double value)
        => Assert.Throws<ArgumentException>(() => OperationalMetrics.Serialize(new Dictionary<string,double> {[name]=value}, "dev", 1000));
    [Fact]
    public void Unknown_counter_rejected()
        => Assert.Throws<ArgumentException>(() => OperationalMetrics.Count("ShipmentId"));
}
