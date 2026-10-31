using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;
using Microsoft.Extensions.Configuration;
using Npgsql;
using TrackingService.Infrastructure.Configuration;

namespace TrackingService.Infrastructure.Persistence;

public sealed class TrackingDbContextFactory : IDesignTimeDbContextFactory<TrackingDbContext>
{
    public TrackingDbContext CreateDbContext(string[] args)
    {
        var currentDirectory = Directory.GetCurrentDirectory();
        var apiDirectory = Path.GetFullPath(Path.Combine(currentDirectory, "../TrackingService.Api"));
        var basePath = Directory.Exists(apiDirectory) ? apiDirectory : currentDirectory;

        var configuration = new ConfigurationBuilder()
            .SetBasePath(basePath)
            .AddJsonFile("appsettings.json", optional: true)
            .AddJsonFile("appsettings.Development.json", optional: true)
            .AddEnvironmentVariables()
            .Build();

        var production = !string.Equals(Environment.GetEnvironmentVariable("ASPNETCORE_ENVIRONMENT"), "Development", StringComparison.OrdinalIgnoreCase);
        var connectionString = PostgresConfiguration.Resolve(configuration, production, migration: true);
        var databaseOptions = configuration.GetSection(DatabaseOptions.SectionName).Get<DatabaseOptions>()
            ?? new DatabaseOptions();
        var npgsqlConnectionStringBuilder = new NpgsqlConnectionStringBuilder(connectionString)
        {
            SearchPath = databaseOptions.Schema
        };

        var optionsBuilder = new DbContextOptionsBuilder<TrackingDbContext>();
        optionsBuilder.UseNpgsql(
            npgsqlConnectionStringBuilder.ConnectionString,
            npgsql =>
            {
                npgsql.MigrationsAssembly(typeof(TrackingDbContext).Assembly.FullName);
                npgsql.MigrationsHistoryTable("__EFMigrationsHistory", databaseOptions.Schema);
            });

        return new TrackingDbContext(optionsBuilder.Options);
    }
}
