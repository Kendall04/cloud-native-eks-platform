using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using TrackingService.Infrastructure.Persistence;

namespace TrackingService.Infrastructure.Observability;

public sealed class OutboxMetricsService(IServiceScopeFactory scopes, ILogger<OutboxMetricsService> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(60));
        do
        {
            try
            {
                using var scope = scopes.CreateScope();
                var db = scope.ServiceProvider.GetRequiredService<TrackingDbContext>();
                var snapshot = await ReadSnapshotAsync(db, stoppingToken);
                // Each replica sees the same DB gauges. Dashboard/alarm uses Maximum, never Sum.
                OperationalMetrics.Gauges(snapshot.Pending, snapshot.OldestAge, snapshot.Failed);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { return; }
            catch (Exception) { logger.LogWarning("Outbox metric snapshot unavailable ErrorCode={ErrorCode}", "MetricDatabaseUnavailable"); }
            try { if (!await timer.WaitForNextTickAsync(stoppingToken)) return; }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { return; }
        } while (!stoppingToken.IsCancellationRequested);
    }
    public static Task<OutboxSnapshot> ReadSnapshotAsync(TrackingDbContext db, CancellationToken cancellationToken = default)
    {
        return db.Database.SqlQuery<OutboxSnapshot>($"""
                    SELECT COUNT(*) FILTER (WHERE "PublishedAt" IS NULL AND "FailedAt" IS NULL) AS "Pending",
                      COUNT(*) FILTER (WHERE "FailedAt" IS NOT NULL) AS "Failed",
                      COALESCE(GREATEST(0, EXTRACT(EPOCH FROM (clock_timestamp() - MIN("CreatedAt")
                        FILTER (WHERE "PublishedAt" IS NULL)))), 0)::double precision AS "OldestAge"
                    FROM tracking."OutboxMessages"
                    """).SingleAsync(cancellationToken);
    }
    public sealed class OutboxSnapshot
    {
        public long Pending { get; set; }
        public long Failed { get; set; }
        public double OldestAge { get; set; }
    }
}
