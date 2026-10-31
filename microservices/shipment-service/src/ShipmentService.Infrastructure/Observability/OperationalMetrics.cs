using System.Text.Json;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace ShipmentService.Infrastructure.Observability;

// Small EMF emitter, local to each independently buildable service image.
// No IDs, routes, user data or pod names are accepted as metric dimensions.
public static class OperationalMetrics
{
    private static readonly object Gate = new();
    private static readonly Dictionary<string, double> Counts = new();
    private static readonly List<double> Latencies = new();
    private static bool enabled;
    private static string environment = "dev";
    private static readonly HashSet<string> Allowed = ["http.requests", "http.errors", "tracking.publish.success", "tracking.publish.failure", "shipment.consumer.applied", "shipment.consumer.duplicate", "shipment.consumer.sequence_gap", "shipment.consumer.rejected"];
    public static void Configure(bool active, string env)
    {
        if (env is not ("dev" or "prod")) throw new InvalidOperationException("Telemetry environment must be dev or prod.");
        enabled = active; environment = env;
    }
    public static void Count(string name)
    {
        if (!Allowed.Contains(name)) throw new ArgumentException("Unknown bounded metric", nameof(name));
        if (!enabled) return;
        lock (Gate) Counts[name] = Counts.GetValueOrDefault(name) + 1;
    }
    public static void Http(double milliseconds, int status)
    {
        Count("http.requests"); if (status >= 500) Count("http.errors");
        if (enabled) lock (Gate) { if (Latencies.Count < 100) Latencies.Add(milliseconds); }
    }
    public static string Serialize(IReadOnlyDictionary<string, double> values, string env, long timestamp)
    {
        if (env is not ("dev" or "prod")) throw new ArgumentException("Invalid telemetry environment");
        if (values.Any(x => (!Allowed.Contains(x.Key) && x.Key is not ("tracking.outbox.pending" or "tracking.outbox.oldest_age" or "tracking.outbox.failed")) || !double.IsFinite(x.Value) || x.Value < 0))
            throw new ArgumentException("Invalid bounded metric value");
        var units = values.Select(x => new { Name = x.Key, Unit = x.Key.EndsWith("oldest_age") ? "Seconds" : "Count", StorageResolution = 60 }).ToArray();
        var record = new Dictionary<string, object> { ["Environment"] = env, ["Service"] = "shipment", ["_aws"] = new {
            Timestamp = timestamp, CloudWatchMetrics = new[] { new { Namespace = "Platform/Operations", Dimensions = new[] { new[] { "Environment", "Service" } }, Metrics = units } }
        }};
        foreach (var value in values) record[value.Key] = value.Value;
        return JsonSerializer.Serialize(record);
    }
    public static void Gauges(double pending, double oldestAge, double failed)
    {
        if (!enabled) return;
        Write(Serialize(new Dictionary<string, double> { ["tracking.outbox.pending"] = pending, ["tracking.outbox.oldest_age"] = oldestAge, ["tracking.outbox.failed"] = failed }, environment, DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()));
    }
    public static void Flush()
    {
        if (!enabled) return;
        Dictionary<string, double> values; double[] durations;
        lock (Gate) { values = new(Counts); Counts.Clear(); durations = Latencies.ToArray(); Latencies.Clear(); }
        values.TryAdd("http.requests", 0); values.TryAdd("http.errors", 0);
        Write(Serialize(values, environment, DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()));
        if (durations.Length > 0) Write(JsonSerializer.Serialize(new {
            _aws = new { Timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(), CloudWatchMetrics = new[] { new { Namespace = "Platform/Operations", Dimensions = new[] { new[] { "Environment", "Service" } }, Metrics = new[] { new { Name = "http.duration_ms", Unit = "Milliseconds", StorageResolution = 60 } } } } },
            Environment = environment, Service = "shipment", DurationSamples = durations
        }).Replace("\"DurationSamples\"", "\"http.duration_ms\""));
    }
    private static void Write(string json)
    {
        try { Console.WriteLine(json); } catch (IOException) { /* Telemetry must not fail business commits. */ }
    }
}

public sealed class MetricsFlushService : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(60));
        try { while (await timer.WaitForNextTickAsync(stoppingToken)) OperationalMetrics.Flush(); }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { }
        finally { OperationalMetrics.Flush(); }
    }
}
