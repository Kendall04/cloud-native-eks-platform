using AuthService.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using ShipmentService.Domain.Entities;
using ShipmentService.Infrastructure.Persistence;
using TrackingService.Infrastructure.Persistence;
using Xunit;

namespace EventReliability.Tests;

public sealed class RuntimeMigrationTests : PostgresFixture
{
    [Theory]
    [InlineData("auth")]
    [InlineData("shipment")]
    [InlineData("tracking")]
    public void Net10ModelStillMatchesTheExistingMigrationSnapshot(string service)
    {
        // This comparison builds the provider's design-time model without a DB.
        // A runtime upgrade must not silently demand a new schema migration.
        const string connection = "Host=localhost;Database=model_only";
        using DbContext db = service switch
        {
            "auth" => new AuthDbContext(new DbContextOptionsBuilder<AuthDbContext>().UseNpgsql(connection).Options),
            "shipment" => new ShipmentDbContext(new DbContextOptionsBuilder<ShipmentDbContext>().UseNpgsql(connection).Options),
            _ => new TrackingDbContext(new DbContextOptionsBuilder<TrackingDbContext>().UseNpgsql(connection).Options)
        };
        Assert.False(db.Database.HasPendingModelChanges());
    }

    [PostgresFact]
    public async Task IncompatibleModelIsRejectedWithoutChangingMigrationHistory()
    {
        await using var original = Shipment();
        var before = (await original.Database.GetAppliedMigrationsAsync()).ToArray();
        Assert.NotEmpty(before);
        await using var drift = new ShipmentDbContext(new DbContextOptionsBuilder<ShipmentDbContext>()
            .UseNpgsql(Connection, o => o.MigrationsHistoryTable("__EFMigrationsHistory", "shipment"))
            .ReplaceService<IModelCustomizer, IncompatibleModelCustomizer>().Options);
        Assert.True(drift.Database.HasPendingModelChanges());
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => drift.Database.MigrateAsync());
        Assert.Contains("PendingModelChangesWarning", error.Message);
        Assert.Equal(before, (await original.Database.GetAppliedMigrationsAsync()).ToArray());
    }

    public sealed class IncompatibleModelCustomizer(ModelCustomizerDependencies dependencies)
        : RelationalModelCustomizer(dependencies)
    {
        public override void Customize(ModelBuilder builder, DbContext context)
        {
            base.Customize(builder, context);
            builder.Entity<Shipment>().Property(x => x.TrackingNumber).HasMaxLength(51);
        }
    }
}
