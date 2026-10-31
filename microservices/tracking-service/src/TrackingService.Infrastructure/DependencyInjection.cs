using Amazon;
using Amazon.EventBridge;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using Npgsql;
using TrackingService.Application.Interfaces;
using TrackingService.Infrastructure.Configuration;
using TrackingService.Infrastructure.Messaging;
using TrackingService.Infrastructure.Persistence;
using TrackingService.Infrastructure.Services;

namespace TrackingService.Infrastructure;

public static class DependencyInjection
{
    public static IServiceCollection AddInfrastructure(this IServiceCollection services, IConfiguration configuration, bool production = false, bool migration = false)
    {
        services
            .AddOptions<DatabaseOptions>()
            .Bind(configuration.GetSection(DatabaseOptions.SectionName))
            .ValidateDataAnnotations()
            .ValidateOnStart();

        services
            .AddOptions<PlatformAuthOptions>()
            .Bind(configuration.GetSection(PlatformAuthOptions.SectionName))
            .ValidateOnStart();

        services
            .AddOptions<AwsOptions>()
            .Bind(configuration.GetSection(AwsOptions.SectionName))
            .ValidateDataAnnotations()
            .ValidateOnStart();

        services
            .AddOptions<OutboxOptions>()
            .Bind(configuration.GetSection(OutboxOptions.SectionName))
            .ValidateDataAnnotations()
            .Validate(o => o.MaxRetryDelaySeconds >= o.BaseRetryDelaySeconds, "Invalid retry delay bounds")
            .ValidateOnStart();

        services
            .AddOptions<ShipmentServiceOptions>()
            .Bind(configuration.GetSection(ShipmentServiceOptions.SectionName))
            .ValidateDataAnnotations()
            .ValidateOnStart();

        services.AddDbContext<TrackingDbContext>(options =>
        {
            var connectionString = PostgresConfiguration.Resolve(configuration, production, migration);
            var databaseOptions = configuration.GetSection(DatabaseOptions.SectionName).Get<DatabaseOptions>()
                ?? throw new InvalidOperationException("Database configuration was not found.");
            var npgsqlConnectionStringBuilder = new NpgsqlConnectionStringBuilder(connectionString)
            {
                SearchPath = databaseOptions.Schema
            };

            options.UseNpgsql(
                npgsqlConnectionStringBuilder.ConnectionString,
                npgsql =>
                {
                    npgsql.MigrationsAssembly(typeof(TrackingDbContext).Assembly.FullName);
                    npgsql.MigrationsHistoryTable("__EFMigrationsHistory", databaseOptions.Schema);
                });
        });

        services.AddHealthChecks().AddDbContextCheck<TrackingDbContext>("postgres", tags: new[] { "ready" });

        services.AddSingleton<IAmazonEventBridge>(serviceProvider =>
        {
            var awsOptions = serviceProvider.GetRequiredService<IOptions<AwsOptions>>().Value;
            return new AmazonEventBridgeClient(RegionEndpoint.GetBySystemName(awsOptions.Region));
        });

        services.AddHttpClient<IShipmentLookupService, ShipmentLookupService>((serviceProvider, client) =>
        {
            var options = serviceProvider.GetRequiredService<IOptions<ShipmentServiceOptions>>().Value;
            client.BaseAddress = new Uri(options.BaseUrl.TrimEnd('/') + "/");
            client.Timeout = TimeSpan.FromSeconds(10);
        });

        services.AddScoped<ITrackingEventsService, TrackingEventsService>();
        services.AddSingleton(TimeProvider.System);
        services.AddSingleton<EventBridgeTrackingEventPublisher>();
        services.AddScoped<OutboxStore>();
        if (!migration)
        {
            services.AddHostedService<OutboxDispatcher>();
            services.AddHostedService<Observability.OutboxMetricsService>();
        }
        services.AddScoped<DatabaseInitializer>();

        return services;
    }
}
