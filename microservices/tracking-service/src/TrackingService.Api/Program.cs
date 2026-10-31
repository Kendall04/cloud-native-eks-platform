using TrackingService.Infrastructure.Observability;
using Microsoft.AspNetCore.Diagnostics.HealthChecks;
using AuthSchemeOptions = Microsoft.AspNetCore.Authentication.AuthenticationSchemeOptions;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.OpenApi.Models;
using TrackingService.Api.Infrastructure;
using TrackingService.Application.Common.Authorization;
using TrackingService.Domain.Constants;
using TrackingService.Infrastructure;
using TrackingService.Infrastructure.Persistence;

var builder = WebApplication.CreateBuilder(args);
if (builder.Environment.IsProduction())
{
    builder.Logging.ClearProviders();
    builder.Logging.AddJsonConsole(o => { o.IncludeScopes = true; o.UseUtcTimestamp = true; o.TimestampFormat = "O"; });
}
OperationalMetrics.Configure(builder.Environment.IsProduction(), builder.Configuration["Telemetry:Environment"] ?? "dev");
if (!args.Contains("--migrate", StringComparer.OrdinalIgnoreCase)) builder.Services.AddHostedService<MetricsFlushService>();
var swaggerEnabled = builder.Environment.IsDevelopment();
const string swaggerRoutePrefix = "tracking/swagger";

builder.Services.Configure<ForwardedHeadersOptions>(options =>
{
    options.ForwardedHeaders = ForwardedHeaders.XForwardedFor | ForwardedHeaders.XForwardedProto;
    options.KnownIPNetworks.Clear();
    options.KnownProxies.Clear();
});

builder.Services.AddExceptionHandler<GlobalExceptionHandler>();
builder.Services.AddProblemDetails();
builder.Services.AddInfrastructure(builder.Configuration, builder.Environment.IsProduction(), args.Contains("--migrate", StringComparer.OrdinalIgnoreCase));

var authProfileBaseAddress = CurrentProfileClient.ResolveBaseAddress(builder.Environment, builder.Configuration);
builder.Services.AddHttpClient<CurrentProfileClient>(client =>
{
    client.BaseAddress = authProfileBaseAddress;
    client.Timeout = Timeout.InfiniteTimeSpan; // One linked deadline includes body reads.
}).ConfigurePrimaryHttpMessageHandler(() => new SocketsHttpHandler
{
    AllowAutoRedirect = false,
    UseCookies = false,
    UseProxy = false,
    ConnectTimeout = TimeSpan.FromSeconds(2)
}).RedactLoggedHeaders(_ => true);

builder.Services.AddControllers()
    .AddJsonOptions(options =>
    {
        options.JsonSerializerOptions.Converters.Add(new SymbolicEnumConverter<TrackingService.Domain.Enums.TrackingStatus>());
        options.JsonSerializerOptions.Converters.Add(new SymbolicEnumConverter<TrackingService.Domain.Enums.TrackingSourceType>());
    });
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen(options =>
{
    options.SwaggerDoc("v1", new OpenApiInfo
    {
        Title = "tracking-service API",
        Version = "v1",
        Description = "Tracking timeline owner service for the logistics platform."
    });

    options.AddSecurityDefinition("Bearer", new OpenApiSecurityScheme
    {
        In = ParameterLocation.Header,
        Name = "Authorization",
        Type = SecuritySchemeType.Http,
        Scheme = "bearer",
        BearerFormat = "JWT",
        Description = "Bearer token presented to API Gateway. In production the service trusts only API-Gateway-verified identity headers."
    });

    options.AddSecurityRequirement(new OpenApiSecurityRequirement
    {
        {
            new OpenApiSecurityScheme
            {
                Reference = new OpenApiReference
                {
                    Type = ReferenceType.SecurityScheme,
                    Id = "Bearer"
                }
            },
            Array.Empty<string>()
        }
    });
});

builder.Services
    .AddAuthentication("GatewayJwt")
    .AddScheme<AuthSchemeOptions, GatewayJwtAuthenticationHandler>("GatewayJwt", _ => { });

builder.Services.AddAuthorization(options =>
{
    options.AddPolicy(
        PolicyNames.RequireUserRole,
        policy => policy.RequireRole(ApplicationRoles.User, ApplicationRoles.Admin));

    options.AddPolicy(
        PolicyNames.RequireAdminRole,
        policy => policy.RequireRole(ApplicationRoles.Admin));
});

var app = builder.Build();
if (app.Environment.IsProduction())
{
    foreach (var key in new[] { "PlatformAuth:TrustedProxySecret", "PlatformAuth:InternalServiceSecret" })
    {
        var value = app.Configuration[key];
        if (string.IsNullOrWhiteSpace(value) || value.Length < 32 || value.Contains("replace", StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Required production trust configuration is invalid.");
    }
}

TrackingService.Infrastructure.Configuration.PostgresConfiguration.Resolve(app.Configuration, app.Environment.IsProduction(), args.Contains("--migrate", StringComparer.OrdinalIgnoreCase));

if (args.Contains("--migrate", StringComparer.OrdinalIgnoreCase))
{
    using var scope = app.Services.CreateScope();
    var initializer = scope.ServiceProvider.GetRequiredService<DatabaseInitializer>();
    await initializer.InitializeAsync();
    return;
}

app.UseForwardedHeaders();
app.Use(async (context, next) =>
{
    // Server-generated request identity. Never trust a client supplied correlation header.
    var requestId = context.TraceIdentifier;
    context.Response.Headers["X-Request-Id"] = requestId;
    using var scope = app.Logger.BeginScope(new Dictionary<string, object> { ["Service"] = "tracking", ["RequestId"] = requestId });
    var start = System.Diagnostics.Stopwatch.GetTimestamp();
    try { await next(context); }
    finally
    {
        if (!context.Request.Path.StartsWithSegments("/health"))
        {
            var elapsed = System.Diagnostics.Stopwatch.GetElapsedTime(start).TotalMilliseconds;
            OperationalMetrics.Http(elapsed, context.Response.StatusCode);
            app.Logger.LogInformation("HTTP completed StatusCode={StatusCode} DurationMs={DurationMs}", context.Response.StatusCode, elapsed);
        }
    }
});
app.UseExceptionHandler();

if (swaggerEnabled)
{
    app.UseSwagger(options =>
    {
        options.RouteTemplate = $"{swaggerRoutePrefix}/{{documentName}}/swagger.json";
    });
    app.UseSwaggerUI(options =>
    {
        options.RoutePrefix = swaggerRoutePrefix;
        options.SwaggerEndpoint("v1/swagger.json", "tracking-service API v1");
    });
}

app.UseMiddleware<RequestBoundaryMiddleware>();
app.UseAuthentication();
app.UseAuthorization();

app.MapControllers();
// Liveness/startup prove the HTTP process is running, without probing dependencies.
app.MapHealthChecks("/health/live", new HealthCheckOptions { Predicate = _ => false });
app.MapHealthChecks("/health/ready", new HealthCheckOptions { Predicate = check => check.Tags.Contains("ready") });
// Compatibility alias: /health has readiness semantics.
app.MapHealthChecks("/health", new HealthCheckOptions { Predicate = check => check.Tags.Contains("ready") });

app.Run();

public partial class Program { }
