using Microsoft.EntityFrameworkCore;
using AuthService.Infrastructure.Persistence;
using System.Net;
using System.Security.Cryptography;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Extensions.Options;
using Microsoft.Extensions.Logging;
using Xunit;

namespace AuthService.Tests;

public sealed class RuntimeContractTests
{
    [Fact]
    public async Task ResponseIdentifiesActualAssemblyBuildWithoutReadingConfiguration()
    {
        using var factory = CreateFactory();
        using var client = factory.CreateClient();
        using var response = await client.GetAsync("/health/live");
        var version = typeof(Program).Assembly
            .GetCustomAttributes(typeof(System.Reflection.AssemblyInformationalVersionAttribute), false)
            .Cast<System.Reflection.AssemblyInformationalVersionAttribute>().Single().InformationalVersion;
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal(version, Assert.Single(response.Headers.GetValues("X-Build-Version")));
        Assert.False(response.Headers.Contains("Database__Password"));
    }

    [Fact]
    public async Task EmptyRefreshProvidesBackendSmokeEvidenceWithoutDatabaseAccess()
    {
        using var factory = CreateFactory(); // Database deliberately unavailable.
        using var client = factory.CreateClient();
        using var response = await client.PostAsync("/auth/refresh",
            new StringContent("{}", System.Text.Encoding.UTF8, "application/json"));
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal("application/problem+json", response.Content.Headers.ContentType?.MediaType);
        Assert.True(response.Headers.Contains("X-Request-Id"));
        using var body = System.Text.Json.JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        Assert.Equal(400, body.RootElement.GetProperty("status").GetInt32());
        Assert.NotEmpty(body.RootElement.GetProperty("errors").GetProperty("RefreshToken").EnumerateArray());
    }

    [Fact]
    public async Task DatabaseOutageRemovesReadinessButDoesNotKillProcess()
    {
        using var factory = CreateFactory();
        using var client = factory.CreateClient();
        using var scope = factory.Services.CreateScope();
        Assert.Contains("Port=1", scope.ServiceProvider.GetRequiredService<AuthDbContext>().Database.GetConnectionString());
        var registrations = factory.Services.GetRequiredService<IOptions<HealthCheckServiceOptions>>().Value.Registrations;
        Assert.Contains(registrations, check => check.Name == "postgres" && check.Tags.Contains("ready"));
        Assert.Equal(HttpStatusCode.OK, (await client.GetAsync("/health/live")).StatusCode);
        Assert.Equal(HttpStatusCode.ServiceUnavailable, (await client.GetAsync("/health/ready")).StatusCode);
        Assert.Equal(HttpStatusCode.ServiceUnavailable, (await client.GetAsync("/health")).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await client.GetAsync("/health/live")).StatusCode);
    }

    [Theory]
    [InlineData("/swagger")]
    [InlineData("/swagger/v1/swagger.json")]
    [InlineData("/auth/swagger")]
    [InlineData("/auth/swagger/index.html")]
    [InlineData("/auth/swagger/v1/swagger.json")]
    public async Task ProductionNeverServesSwaggerEvenWhenLegacyFlagIsTrue(string path)
    {
        using var factory = CreateFactory();
        using var client = factory.CreateClient();
        Assert.Equal(HttpStatusCode.NotFound, (await client.GetAsync(path)).StatusCode);
    }

    internal static WebApplicationFactory<Program> CreateFactory() => new WebApplicationFactory<Program>()
        .WithWebHostBuilder(builder =>
        {
            builder.UseEnvironment("Production");
            builder.ConfigureLogging(logging => logging.ClearProviders().AddConsole());
            builder.ConfigureAppConfiguration((_, config) => config.AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["ConnectionStrings:Postgres"] = "Host=127.0.0.1;Port=1;Database=unavailable;Username=test;Password=test;Timeout=1;Command Timeout=1;Pooling=false",
                ["Swagger:Enabled"] = "true",
                ["Database:Host"] = "localhost",
                ["Database:Name"] = "platform",
                ["Database:Schema"] = "auth",
                ["Database:Username"] = "auth_runtime",
                ["Database:Password"] = new string('x', 48),
                ["Database:SslMode"] = "VerifyFull",
                ["Database:RootCertificate"] = Path.Combine(AppContext.BaseDirectory, "rds-global-bundle.pem"),
                ["PlatformAuth:InternalServiceSecret"] = new string('y', 48),
                ["Jwt:Secret"] = Convert.ToBase64String(RandomNumberGenerator.GetBytes(48)),
                ["PlatformAuth:TrustedProxySecret"] = "r1-test-only-proxy-secret-not-a-real-credential"
            }));
            builder.ConfigureServices(services =>
            {
                // Replace only DB connection options: exercise the actual Npgsql/EF health check.
                services.RemoveAll<DbContextOptions<AuthDbContext>>();
                services.AddDbContext<AuthDbContext>(options =>
                    options.UseNpgsql("Host=127.0.0.1;Port=1;Database=unavailable;Username=test;Password=test;Timeout=1;Command Timeout=1;Pooling=false"));
            });
        });
}
