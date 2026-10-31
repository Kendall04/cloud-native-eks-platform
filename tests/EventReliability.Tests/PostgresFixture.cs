using Microsoft.EntityFrameworkCore;
using Npgsql;
using ShipmentService.Infrastructure.Persistence;
using TrackingService.Infrastructure.Persistence;
using Xunit;

namespace EventReliability.Tests;

public sealed class PostgresFactAttribute : FactAttribute
{
    public PostgresFactAttribute()
    {
        if (string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("R5_POSTGRES_DSN")))
            Skip = "Requires a disposable local PostgreSQL server; no SQLite substitute.";
    }
}

public abstract class PostgresFixture : IAsyncLifetime
{
    private string? admin;
    private string? database;
    protected string Connection = "";

    public async Task InitializeAsync()
    {
        admin = Environment.GetEnvironmentVariable("R5_POSTGRES_DSN");
        if (string.IsNullOrWhiteSpace(admin)) return;
        var builder = new NpgsqlConnectionStringBuilder(admin);
        if (builder.Host is not ("127.0.0.1" or "localhost")) throw new InvalidOperationException("Tests require localhost, never a cloud DB.");
        database = "r5_test_" + Guid.NewGuid().ToString("N");
        await using var connection = new NpgsqlConnection(admin);
        await connection.OpenAsync();
        await new NpgsqlCommand($"CREATE DATABASE {database}", connection).ExecuteNonQueryAsync();
        builder.Database = database; Connection = builder.ConnectionString;
        await Sql("CREATE SCHEMA tracking; CREATE SCHEMA shipment;");
        await using var tracking = Tracking(); await tracking.Database.MigrateAsync();
        await using var shipment = Shipment(); await shipment.Database.MigrateAsync();
    }

    protected TrackingDbContext Tracking() => new(new DbContextOptionsBuilder<TrackingDbContext>()
        .UseNpgsql(new NpgsqlConnectionStringBuilder(Connection) { SearchPath = "tracking" }.ConnectionString,
            o => o.MigrationsHistoryTable("__EFMigrationsHistory", "tracking")).Options);
    protected ShipmentDbContext Shipment() => new(new DbContextOptionsBuilder<ShipmentDbContext>()
        .UseNpgsql(new NpgsqlConnectionStringBuilder(Connection) { SearchPath = "shipment" }.ConnectionString,
            o => o.MigrationsHistoryTable("__EFMigrationsHistory", "shipment")).Options);
    protected async Task Sql(string sql)
    {
        await using var connection = new NpgsqlConnection(Connection); await connection.OpenAsync();
        await new NpgsqlCommand(sql, connection).ExecuteNonQueryAsync();
    }
    public async Task DisposeAsync()
    {
        if (admin is null || database is null) return;
        NpgsqlConnection.ClearAllPools();
        await using var connection = new NpgsqlConnection(admin); await connection.OpenAsync();
        await new NpgsqlCommand($"DROP DATABASE {database} WITH (FORCE)", connection).ExecuteNonQueryAsync();
    }
}
