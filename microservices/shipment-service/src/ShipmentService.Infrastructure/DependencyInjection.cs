using Amazon;
using Amazon.SQS;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Npgsql;
using ShipmentService.Application.Interfaces;
using ShipmentService.Infrastructure.Configuration;
using ShipmentService.Infrastructure.Messaging;
using ShipmentService.Infrastructure.Persistence;
using ShipmentService.Infrastructure.Services;

namespace ShipmentService.Infrastructure;

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
            .AddOptions<AwsOptions>()
            .Bind(configuration.GetSection(AwsOptions.SectionName))
            .ValidateDataAnnotations()
            .ValidateOnStart();

        services
            .AddOptions<ShipmentConsumerOptions>()
            .Bind(configuration.GetSection(ShipmentConsumerOptions.SectionName))
            .ValidateDataAnnotations()
            .ValidateOnStart();

        services.AddDbContext<ShipmentDbContext>(options =>
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
                    npgsql.MigrationsAssembly(typeof(ShipmentDbContext).Assembly.FullName);
                    npgsql.MigrationsHistoryTable("__EFMigrationsHistory", databaseOptions.Schema);
                });
        });

        services.AddHealthChecks().AddDbContextCheck<ShipmentDbContext>("postgres", tags: new[] { "ready" });

        services.AddSingleton<IAmazonSQS>(serviceProvider =>
        {
            var awsOptions = serviceProvider.GetRequiredService<
                Microsoft.Extensions.Options.IOptions<AwsOptions>>().Value;
            return new AmazonSQSClient(RegionEndpoint.GetBySystemName(awsOptions.Region));
        });

        services.AddScoped<IShipmentService, ShipmentApplicationService>();
        services.AddScoped<IAdminShipmentService, AdminShipmentService>();
        services.AddScoped<ITrackingEventProcessor, TrackingEventProcessor>();
        services.AddSingleton<ITrackingNumberGenerator, TrackingNumberGenerator>();
        services.AddSingleton(TimeProvider.System);
        services.AddScoped<DatabaseInitializer>();
        if (!migration) services.AddHostedService<SqsTrackingEventsConsumer>();

        return services;
    }
}
