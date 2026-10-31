using AuthService.Application.Interfaces;
using AuthService.Domain.Entities;
using AuthService.Infrastructure.Configuration;
using AuthService.Infrastructure.Persistence;
using AuthService.Infrastructure.Security;
using AuthService.Infrastructure.Seeding;
using AuthService.Infrastructure.Services;
using Microsoft.AspNetCore.Identity;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Npgsql;

namespace AuthService.Infrastructure;

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
            .AddOptions<JwtOptions>()
            .Bind(configuration.GetSection(JwtOptions.SectionName))
            .ValidateDataAnnotations()
            .ValidateOnStart();

        services
            .AddOptions<AuthTokenOptions>()
            .Bind(configuration.GetSection(AuthTokenOptions.SectionName))
            .ValidateDataAnnotations()
            .ValidateOnStart();

        services
            .AddOptions<BootstrapAdminOptions>()
            .Bind(configuration.GetSection(BootstrapAdminOptions.SectionName));

        services.AddDbContext<AuthDbContext>(options =>
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
                    npgsql.MigrationsAssembly(typeof(AuthDbContext).Assembly.FullName);
                    npgsql.MigrationsHistoryTable("__EFMigrationsHistory", databaseOptions.Schema);
                });
        });

        services
            .AddIdentityCore<ApplicationUser>(options =>
            {
                options.Password.RequiredLength = 8;
                options.Password.RequireDigit = true;
                options.Password.RequireLowercase = true;
                options.Password.RequireUppercase = true;
                options.Password.RequireNonAlphanumeric = true;
                options.User.RequireUniqueEmail = true;
                options.SignIn.RequireConfirmedEmail = false;
            })
            .AddRoles<IdentityRole<Guid>>()
            .AddEntityFrameworkStores<AuthDbContext>()
            .AddDefaultTokenProviders();

        services.AddHealthChecks().AddDbContextCheck<AuthDbContext>("postgres", tags: new[] { "ready" });

        services.AddScoped<IAuthService, AuthenticationService>();
        services.AddScoped<IAdminService, AdminService>();
        services.AddScoped<IJwtTokenService, JwtTokenService>();
        services.AddSingleton<IRefreshTokenGenerator, RefreshTokenGenerator>();
        services.AddScoped<DatabaseInitializer>();

        return services;
    }
}
