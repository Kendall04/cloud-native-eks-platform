using Microsoft.EntityFrameworkCore;
using TrackingService.Domain.Entities;

namespace TrackingService.Infrastructure.Persistence;

public sealed class TrackingDbContext(DbContextOptions<TrackingDbContext> options) : DbContext(options)
{
    public DbSet<TrackingEvent> TrackingEvents => Set<TrackingEvent>();
    public DbSet<OutboxMessage> OutboxMessages => Set<OutboxMessage>();

    protected override void OnModelCreating(ModelBuilder builder)
    {
        base.OnModelCreating(builder);
        builder.Entity<OutboxMessage>(entity =>
        {
            entity.ToTable("OutboxMessages", "tracking");
            entity.HasKey(x => x.EventId);
            entity.Property(x => x.Payload).HasColumnType("jsonb").IsRequired();
            entity.Property(x => x.LastError).HasMaxLength(256);
            entity.HasIndex(x => new { x.AggregateId, x.AggregateSequence }).IsUnique();
            entity.HasIndex(x => new { x.NextAttemptAt, x.LeaseUntil })
                .HasFilter("\"PublishedAt\" IS NULL AND \"FailedAt\" IS NULL");
        });

        builder.Entity<TrackingEvent>(entity =>
        {
            entity.ToTable("TrackingEvents");

            entity.HasKey(trackingEvent => trackingEvent.Id);

            entity.Property(trackingEvent => trackingEvent.Status)
                .HasConversion<string>()
                .HasMaxLength(32)
                .IsRequired();

            entity.Property(trackingEvent => trackingEvent.Location)
                .HasMaxLength(200)
                .IsRequired();

            entity.Property(trackingEvent => trackingEvent.Notes)
                .HasMaxLength(500);

            entity.Property(trackingEvent => trackingEvent.SourceType)
                .HasConversion<string>()
                .HasMaxLength(32)
                .IsRequired();

            entity.Property(trackingEvent => trackingEvent.CreatedBy)
                .HasMaxLength(100);

            entity.HasIndex(trackingEvent => trackingEvent.ShipmentId);
            entity.HasIndex(trackingEvent => trackingEvent.OccurredAt);
            entity.HasIndex(trackingEvent => new { trackingEvent.ShipmentId, trackingEvent.OccurredAt });
            entity.HasIndex(trackingEvent => new { trackingEvent.ShipmentId, trackingEvent.SequenceNumber })
                .IsUnique();
        });
    }
}
