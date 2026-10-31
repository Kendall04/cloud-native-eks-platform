using Microsoft.EntityFrameworkCore;
using ShipmentService.Domain.Entities;
using ShipmentService.Domain.Enums;

namespace ShipmentService.Infrastructure.Persistence;

public sealed class ShipmentDbContext(DbContextOptions<ShipmentDbContext> options) : DbContext(options)
{
    public DbSet<Shipment> Shipments => Set<Shipment>();

    public DbSet<ProcessedEvent> ProcessedEvents => Set<ProcessedEvent>();

    protected override void OnModelCreating(ModelBuilder builder)
    {
        base.OnModelCreating(builder);

        builder.Entity<Shipment>(entity =>
        {
            entity.ToTable("Shipments");

            entity.HasKey(shipment => shipment.Id);

            entity.Property(shipment => shipment.TrackingNumber)
                .HasMaxLength(50)
                .IsRequired();

            entity.Property(shipment => shipment.CustomerId)
                .HasMaxLength(100)
                .IsRequired();

            entity.Property(shipment => shipment.Origin)
                .HasMaxLength(200)
                .IsRequired();

            entity.Property(shipment => shipment.Destination)
                .HasMaxLength(200)
                .IsRequired();

            entity.Property(shipment => shipment.Weight)
                .HasColumnType("numeric(18,2)");

            entity.Property(shipment => shipment.Status)
                .HasConversion<string>()
                .HasMaxLength(32)
                .IsRequired();

            entity.Property(shipment => shipment.ReferenceNumber)
                .HasMaxLength(100);

            entity.Property(shipment => shipment.Priority)
                .HasMaxLength(50);

            entity.Property(shipment => shipment.Version)
                .IsConcurrencyToken();

            entity.HasIndex(shipment => shipment.TrackingNumber)
                .IsUnique();

            entity.HasIndex(shipment => shipment.CustomerId);

            entity.HasIndex(shipment => shipment.Status);

            entity.HasIndex(shipment => new { shipment.CustomerId, shipment.Status });
        });

        builder.Entity<ProcessedEvent>(entity =>
        {
            entity.ToTable("ProcessedEvents");

            entity.HasKey(processedEvent => processedEvent.EventId);

            entity.Property(processedEvent => processedEvent.EventId)
                .HasMaxLength(100)
                .IsRequired();

            entity.Property(processedEvent => processedEvent.EventType)
                .HasMaxLength(100)
                .IsRequired();
            entity.Property(x => x.Outcome).HasMaxLength(64);
            entity.HasIndex(x => new { x.ShipmentId, x.SequenceNumber });
        });
    }
}
