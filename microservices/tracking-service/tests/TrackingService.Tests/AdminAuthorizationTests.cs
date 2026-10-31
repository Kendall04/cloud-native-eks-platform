using System.Net;
using System.Net.Http.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using TrackingService.Application.Common.Authorization;
using TrackingService.Application.Contracts.Tracking;
using TrackingService.Application.Interfaces;
using TrackingService.Domain.Enums;
using Xunit;
using TrackingService.Api.Infrastructure;

namespace TrackingService.Tests;

public sealed class AdminAuthorizationTests
{
    [Theory]
    [InlineData("999")]
    [InlineData("0")]
    [InlineData("\"999\"")]
    [InlineData("\"0\"")]
    [InlineData("\"UNKNOWN\"")]
    [InlineData("\"PICKED_UP, IN_TRANSIT\"")]
    [InlineData("null")]
    public async Task InvalidStatusIsValidationErrorBeforeApplication(string status)
    {
        var application = new RecordingTrackingService();
        using var factory = RuntimeContractTests.CreateFactory().WithWebHostBuilder(builder =>
            builder.ConfigureServices(services =>
            {
                services.RemoveAll<ITrackingEventsService>();
                services.AddSingleton<ITrackingEventsService>(application);
                services.AddHttpClient<CurrentProfileClient>().ConfigurePrimaryHttpMessageHandler(() => new ProfileStub { Roles = new[] { "ADMIN" } });
            }));
        using var client = factory.CreateClient();
        client.DefaultRequestHeaders.Authorization = new("Bearer", "fixture-bearer");
        client.DefaultRequestHeaders.Add("X-Platform-User-Id", ProfileStub.UserId.ToString());
        client.DefaultRequestHeaders.Add("X-Platform-Roles", "ADMIN");
        client.DefaultRequestHeaders.Add("X-Platform-Proxy-Secret", "r1-test-only-proxy-secret-not-a-real-credential");
        var json = $$"""{"shipmentId":"{{Guid.NewGuid()}}","status":{{status}},"location":"hub","occurredAt":"2026-01-01T00:00:00Z"}""";
        using var response = await client.PostAsync("/admin/tracking-events", new StringContent(json, System.Text.Encoding.UTF8, "application/json"));
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.False(application.Called);
    }

    [Fact]
    public async Task ProductionDoesNotAcceptBearerPassthrough()
    {
        using var factory = RuntimeContractTests.CreateFactory();
        using var client = factory.CreateClient();
        client.DefaultRequestHeaders.Authorization = new("Bearer", "attacker-token");
        using var response = await client.PostAsJsonAsync("/admin/tracking-events", new { });
        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    [Theory]
    [InlineData(null, null, 401)]
    [InlineData("USER", "r1-test-only-proxy-secret-not-a-real-credential", 403)]
    [InlineData("ADMIN", null, 401)]
    [InlineData("ADMIN", "attacker-supplied-secret", 401)]
    [InlineData("ADMIN", "r1-test-only-proxy-secret-not-a-real-credential", 201)]
    public async Task AdminEndpointEnforcesTrustedIdentityAndRole(string? role, string? proxySecret, int expected)
    {
        var application = new RecordingTrackingService();
        using var factory = RuntimeContractTests.CreateFactory().WithWebHostBuilder(builder =>
            builder.ConfigureServices(services =>
            {
                services.RemoveAll<ITrackingEventsService>();
                services.AddSingleton<ITrackingEventsService>(application);
                services.AddHttpClient<CurrentProfileClient>().ConfigurePrimaryHttpMessageHandler(() => new ProfileStub { Roles = role == null ? Array.Empty<string>() : new[] { role } });
            }));
        using var client = factory.CreateClient();
        client.DefaultRequestHeaders.Authorization = new("Bearer", "fixture-bearer");
        if (role != null)
        {
            client.DefaultRequestHeaders.Add("X-Platform-User-Id", ProfileStub.UserId.ToString());
            client.DefaultRequestHeaders.Add("X-Platform-Roles", role);
        }
        if (proxySecret != null) client.DefaultRequestHeaders.Add("X-Platform-Proxy-Secret", proxySecret);
        using var response = await client.PostAsJsonAsync("/admin/tracking-events", new
        {
            shipmentId = Guid.NewGuid(), status = "PICKED_UP", location = "Test depot", occurredAt = DateTime.UtcNow
        });
        Assert.Equal((HttpStatusCode)expected, response.StatusCode);
        Assert.Equal(expected == 201, application.Called);
        if (expected == 201)
        {
            Assert.True(application.User!.IsAdmin);
            Assert.Contains("/tracking/by-shipment/", response.Headers.Location!.ToString());
        }
    }

    private sealed class RecordingTrackingService : ITrackingEventsService
    {
        public bool Called { get; private set; }
        public RequestUserContext? User { get; private set; }
        public Task<TrackingEventResponse> CreateAsync(CreateTrackingEventRequest request, RequestUserContext currentUser, CancellationToken cancellationToken = default)
        {
            Called = true;
            User = currentUser;
            return Task.FromResult(new TrackingEventResponse(Guid.NewGuid(), request.ShipmentId,
                request.Status!.Value, request.Location, request.Notes, TrackingSourceType.ADMIN,
                request.OccurredAt, DateTime.UtcNow, currentUser.UserId, 1));
        }
        public Task<IReadOnlyCollection<TrackingEventResponse>> GetTimelineByShipmentIdAsync(Guid shipmentId, RequestUserContext currentUser, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task<IReadOnlyCollection<TrackingEventResponse>> GetTimelineByTrackingNumberAsync(string trackingNumber, RequestUserContext currentUser, CancellationToken cancellationToken = default) => throw new NotSupportedException();
    }
}
