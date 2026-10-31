using Microsoft.EntityFrameworkCore;
using TrackingService.Domain.Entities;
using TrackingService.Infrastructure.Configuration;
using TrackingService.Infrastructure.Persistence;

namespace TrackingService.Infrastructure.Messaging;

public sealed class OutboxStore(TrackingDbContext db)
{
    public async Task<List<OutboxMessage>> ClaimAsync(OutboxOptions options, CancellationToken ct)
    {
        // A single statement is a short implicit transaction. No AWS call holds row locks.
        var token = Guid.NewGuid();
        await db.Database.ExecuteSqlInterpolatedAsync($"""
            UPDATE tracking."OutboxMessages" SET "FailedAt" = clock_timestamp(),
              "LastError" = 'LeaseAttemptsExhausted', "LeaseToken" = NULL, "LeaseUntil" = NULL
            WHERE "PublishedAt" IS NULL AND "FailedAt" IS NULL AND "Attempts" >= {options.MaxAttempts}
              AND ("LeaseUntil" IS NULL OR "LeaseUntil" <= clock_timestamp())
            """, ct);
        return await db.OutboxMessages.FromSqlInterpolated($"""
            WITH pending AS (
              SELECT "EventId" FROM tracking."OutboxMessages"
              WHERE "PublishedAt" IS NULL AND "FailedAt" IS NULL
                AND "NextAttemptAt" <= clock_timestamp()
                AND ("LeaseUntil" IS NULL OR "LeaseUntil" <= clock_timestamp())
                AND "Attempts" < {options.MaxAttempts}
              ORDER BY "NextAttemptAt", "CreatedAt", "AggregateSequence"
              FOR UPDATE SKIP LOCKED LIMIT {options.BatchSize}
            )
            UPDATE tracking."OutboxMessages" AS o SET "LeaseToken" = {token},
              "LeaseUntil" = clock_timestamp() + make_interval(secs => {options.LeaseDurationSeconds}),
              "Attempts" = o."Attempts" + 1
            FROM pending WHERE o."EventId" = pending."EventId" RETURNING o.*
            """).AsNoTracking().ToListAsync(ct);
    }

    public Task<int> CompleteAsync(OutboxMessage row, PublishResult result, OutboxOptions options, CancellationToken ct)
    {
        var delay = options.RetryDelay(row.Attempts, Random.Shared.NextDouble()).TotalSeconds;
        var error = result.Success ? null : EventBridgeTrackingEventPublisher.SafeCode(result.ErrorCode);
        return db.Database.ExecuteSqlInterpolatedAsync($"""
            UPDATE tracking."OutboxMessages" SET
              "PublishedAt" = CASE WHEN {result.Success} THEN clock_timestamp() ELSE NULL END,
              "FailedAt" = CASE WHEN {(!result.Success && row.Attempts >= options.MaxAttempts)} THEN clock_timestamp() ELSE NULL END,
              "NextAttemptAt" = clock_timestamp() + make_interval(secs => {delay}),
              "LastError" = {error}, "LeaseToken" = NULL, "LeaseUntil" = NULL
            WHERE "EventId" = {row.EventId} AND "LeaseToken" = {row.LeaseToken}
              AND "LeaseUntil" > clock_timestamp() AND "PublishedAt" IS NULL AND "FailedAt" IS NULL
            """, ct);
    }
}
