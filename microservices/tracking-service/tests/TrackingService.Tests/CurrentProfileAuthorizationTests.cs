using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Claims;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using TrackingService.Api.Infrastructure;
using TrackingService.Application.Common.Authorization;
using Xunit;

namespace TrackingService.Tests;

public sealed class CurrentProfileAuthorizationTests
{
    [Fact]
    public async Task CurrentProfileReplacesAttestedSnapshotAndIsNeverCached()
    {
        var stub = new ProfileStub();
        using var factory = Factory(stub);
        using var client = factory.CreateClient();
        ProfileStub.Attest(client, "ADMIN");
        using var first = await client.GetAsync("/__test/identity");
        Assert.Equal(HttpStatusCode.OK, first.StatusCode);
        var profile = JsonDocument.Parse(await first.Content.ReadAsStringAsync()).RootElement;
        Assert.Equal("current@example.test", profile.GetProperty("email").GetString());
        Assert.Equal(new[] { "USER" }, profile.GetProperty("roles").EnumerateArray().Select(v => v.GetString()));
        Assert.Equal("no-store", first.Headers.CacheControl!.ToString());
        Assert.Equal(CurrentProfileClient.ProductionBaseUrl + "auth/me", stub.LastUri);
        Assert.Equal("Bearer fixture-bearer", stub.LastAuthorization);
        Assert.False(stub.ForwardedIdentityOrCookie);
        stub.Active = false;
        using var second = await client.GetAsync("/__test/identity");
        Assert.Equal(HttpStatusCode.Forbidden, second.StatusCode);
        Assert.Equal(2, stub.Calls);
    }

    [Fact]
    public async Task ConcurrentUsersKeepTheirOwnBearerAndCurrentProfile()
    {
        var secondId = Guid.Parse("22222222-2222-4222-8222-222222222222");
        var stub = new ProfileStub { Reply = async (request, _) =>
        {
            await Task.Yield();
            var second = request.Headers.Authorization!.Parameter == "second-bearer";
            return new HttpResponseMessage(HttpStatusCode.OK) { Content = JsonContent.Create(new
            { userId = second ? secondId : ProfileStub.UserId, email = second ? "second@example.test" : "first@example.test", isActive = true, roles = new[] { "USER" } }) };
        } };
        using var factory = Factory(stub);
        using var first = factory.CreateClient();
        using var second = factory.CreateClient();
        ProfileStub.Attest(first);
        ProfileStub.Attest(second);
        second.DefaultRequestHeaders.Authorization = new("Bearer", "second-bearer");
        second.DefaultRequestHeaders.Remove("X-Platform-User-Id");
        second.DefaultRequestHeaders.Add("X-Platform-User-Id", secondId.ToString());
        var responses = await Task.WhenAll(first.GetAsync("/__test/identity"), second.GetAsync("/__test/identity"));
        using var firstResponse = responses[0];
        using var secondResponse = responses[1];
        Assert.Equal(HttpStatusCode.OK, firstResponse.StatusCode);
        Assert.Equal(HttpStatusCode.OK, secondResponse.StatusCode);
        Assert.Contains("first@example.test", await firstResponse.Content.ReadAsStringAsync());
        Assert.Contains("second@example.test", await secondResponse.Content.ReadAsStringAsync());
        Assert.Equal(2, stub.Calls);
    }

    [Fact]
    public async Task RemovedAdminRoleImmediatelyLosesAdminAccessWithSameBearer()
    {
        var stub = new ProfileStub { Roles = new[] { "USER", "ADMIN" } };
        using var factory = Factory(stub);
        using var client = factory.CreateClient();
        ProfileStub.Attest(client, "ADMIN");
        Assert.Equal(HttpStatusCode.OK, (await client.GetAsync("/__test/identity/admin")).StatusCode);
        stub.Roles = new[] { "USER" };
        Assert.Equal(HttpStatusCode.Forbidden, (await client.GetAsync("/__test/identity/admin")).StatusCode);
        stub.Roles = Array.Empty<string>();
        Assert.Equal(HttpStatusCode.Forbidden, (await client.GetAsync("/__test/identity/user")).StatusCode);
        Assert.Equal(3, stub.Calls);
    }

    [Theory]
    [InlineData(401, 401)] // Expired, forged, deleted or disabled account rejected by Auth.
    [InlineData(403, 403)]
    [InlineData(404, 401)] // Deletion between Auth's authentication and profile read.
    [InlineData(302, 503)]
    [InlineData(429, 503)]
    [InlineData(500, 503)]
    [InlineData(503, 503)]
    [InlineData(204, 503)]
    public async Task AuthDenialOrOutageNeverFallsBackToSnapshot(int upstream, int expected)
    {
        var stub = new ProfileStub { Reply = (_, _) => Task.FromResult(new HttpResponseMessage((HttpStatusCode)upstream)
        { Content = new StringContent("private-origin fixture-bearer database-detail"), Headers = { Location = new Uri("https://redirect.invalid/") } }) };
        using var factory = Factory(stub);
        using var client = factory.CreateClient();
        ProfileStub.Attest(client, "ADMIN");
        using var response = await client.GetAsync("/__test/identity/admin");
        Assert.Equal((HttpStatusCode)expected, response.StatusCode);
        Assert.Equal("no-store", response.Headers.CacheControl!.ToString());
        var body = await response.Content.ReadAsStringAsync();
        Assert.DoesNotContain("private-origin", body);
        Assert.DoesNotContain("fixture-bearer", body);
        Assert.DoesNotContain("database-detail", body);
        Assert.Equal(1, stub.Calls);
    }

    [Fact]
    public async Task DifferentUserFromAuthCannotReplaceAttestedIdentity()
    {
        var stub = new ProfileStub { ProfileUserId = Guid.NewGuid() };
        using var factory = Factory(stub);
        using var client = factory.CreateClient();
        ProfileStub.Attest(client);
        Assert.Equal(HttpStatusCode.Unauthorized, (await client.GetAsync("/__test/identity")).StatusCode);
    }

    [Theory]
    [InlineData("not-json")]
    [InlineData("null")]
    [InlineData("{}")]
    [InlineData("{\"userId\":\"bad\",\"email\":\"e@x.test\",\"isActive\":true,\"roles\":[\"ADMIN\"]}")]
    [InlineData("{\"userId\":\"00000000-0000-0000-0000-000000000000\",\"email\":\"e@x.test\",\"isActive\":true,\"roles\":[]}")]
    [InlineData("{\"userId\":\"11111111-1111-4111-8111-111111111111\",\"email\":null,\"isActive\":true,\"roles\":[\"ADMIN\"]}")]
    [InlineData("{\"userId\":\"11111111-1111-4111-8111-111111111111\",\"email\":\"e@x.test\",\"isActive\":\"true\",\"roles\":[\"ADMIN\"]}")]
    [InlineData("{\"userId\":\"11111111-1111-4111-8111-111111111111\",\"email\":\"e@x.test\",\"isActive\":true,\"roles\":[null]}")]
    [InlineData("{\"userId\":\"11111111-1111-4111-8111-111111111111\",\"email\":\"e@x.test\",\"isActive\":true,\"roles\":[\" ADMIN\"]}")]
    [InlineData("{\"userId\":\"11111111-1111-4111-8111-111111111111\",\"email\":\"e@x.test\",\"isActive\":true,\"roles\":[\"USER,ADMIN\"]}")]
    [InlineData("{\"userId\":\"11111111-1111-4111-8111-111111111111\",\"email\":\"e@x.test\",\"isActive\":true,\"roles\":[],\"roles\":[\"ADMIN\"]}")]
    public async Task MalformedProfilesFailClosed(string json)
    {
        var stub = new ProfileStub { Reply = (_, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
        { Content = new StringContent(json, Encoding.UTF8, "application/json") }) };
        using var factory = Factory(stub);
        using var client = factory.CreateClient();
        ProfileStub.Attest(client);
        Assert.Equal(HttpStatusCode.ServiceUnavailable, (await client.GetAsync("/__test/identity")).StatusCode);
    }

    [Theory]
    [InlineData("http")]
    [InlineData("timeout")]
    public async Task TransportFailuresAreGeneric503(string kind)
    {
        var stub = new ProfileStub { Reply = (_, _) =>
        {
            if (kind == "http") throw new HttpRequestException("private-origin fixture-bearer");
            throw new TaskCanceledException("private-origin fixture-bearer");
        } };
        using var factory = Factory(stub);
        using var client = factory.CreateClient();
        ProfileStub.Attest(client);
        using var response = await client.GetAsync("/__test/identity");
        Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);
        Assert.DoesNotContain("fixture-bearer", await response.Content.ReadAsStringAsync());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task BoundActualProfileBytesEvenWithoutContentLength(bool includeLength)
    {
        var content = UnknownLengthContent.Json(new string('x', CurrentProfileClient.MaximumResponseBytes + 1));
        if (includeLength) content.Headers.ContentLength = CurrentProfileClient.MaximumResponseBytes + 1;
        var stub = new ProfileStub { Reply = (_, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = content }) };
        using var factory = Factory(stub);
        using var client = factory.CreateClient();
        ProfileStub.Attest(client);
        Assert.Equal(HttpStatusCode.ServiceUnavailable, (await client.GetAsync("/__test/identity")).StatusCode);
    }

    [Fact]
    public async Task DeadlineIncludesSlowResponseBodyAndCallerCancellationIsPreserved()
    {
        using var http = new HttpClient(new ProfileStub { Reply = (_, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
        { Content = new SlowContent() }) }) { BaseAddress = new Uri(CurrentProfileClient.ProductionBaseUrl), Timeout = Timeout.InfiniteTimeSpan };
        var profiles = new CurrentProfileClient(http);
        var watch = System.Diagnostics.Stopwatch.StartNew();
        Assert.Equal(ProfileStatus.Unavailable, (await profiles.VerifyAsync("fixture-bearer", ProfileStub.UserId, CancellationToken.None)).Status);
        Assert.True(watch.Elapsed < CurrentProfileClient.Deadline + TimeSpan.FromSeconds(4));
        using var cancellation = new CancellationTokenSource(TimeSpan.FromMilliseconds(30));
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => profiles.VerifyAsync("fixture-bearer", ProfileStub.UserId, cancellation.Token));
    }

    [Theory]
    [InlineData("missing-secret")]
    [InlineData("wrong-secret")]
    [InlineData("missing-id")]
    [InlineData("invalid-id")]
    [InlineData("duplicate-id")]
    [InlineData("duplicate-secret")]
    [InlineData("duplicate-role")]
    [InlineData("missing-bearer")]
    [InlineData("basic")]
    [InlineData("duplicate-bearer")]
    [InlineData("huge-bearer")]
    public async Task ForgedOrAmbiguousEnvelopesNeverReachAuth(string failure)
    {
        var stub = new ProfileStub();
        using var factory = Factory(stub);
        using var client = factory.CreateClient();
        ProfileStub.Attest(client, "ADMIN");
        if (failure.EndsWith("secret"))
        {
            client.DefaultRequestHeaders.Remove("X-Platform-Proxy-Secret");
            if (failure == "wrong-secret") client.DefaultRequestHeaders.Add("X-Platform-Proxy-Secret", "forged");
            if (failure == "duplicate-secret") client.DefaultRequestHeaders.Add("X-Platform-Proxy-Secret", new[] { ProfileStub.Secret, ProfileStub.Secret });
        }
        if (failure.EndsWith("id"))
        {
            client.DefaultRequestHeaders.Remove("X-Platform-User-Id");
            if (failure == "invalid-id") client.DefaultRequestHeaders.Add("X-Platform-User-Id", "forged");
            if (failure == "duplicate-id") client.DefaultRequestHeaders.Add("X-Platform-User-Id", new[] { ProfileStub.UserId.ToString(), ProfileStub.UserId.ToString() });
        }
        if (failure == "duplicate-role") client.DefaultRequestHeaders.Add("X-Platform-Roles", "ADMIN");
        if (failure == "missing-bearer") client.DefaultRequestHeaders.Authorization = null;
        if (failure == "basic") client.DefaultRequestHeaders.Authorization = new("Basic", "fixture");
        if (failure == "duplicate-bearer") client.DefaultRequestHeaders.TryAddWithoutValidation("Authorization", "Bearer second");
        if (failure == "huge-bearer") client.DefaultRequestHeaders.Authorization = new("Bearer", new string('x', 8193));
        Assert.Equal(HttpStatusCode.Unauthorized, (await client.GetAsync("/__test/identity/admin")).StatusCode);
        Assert.Equal(0, stub.Calls);
    }

    [Fact]
    public async Task BearerAloneAndLegacyDevelopmentFlagCannotBypassAttestation()
    {
        var stub = new ProfileStub();
        using var factory = Factory(stub).WithWebHostBuilder(builder =>
        {
            builder.UseEnvironment("Development");
            builder.ConfigureAppConfiguration((_, config) => config.AddInMemoryCollection(new Dictionary<string, string?>
            { ["PlatformAuth:AllowDevelopmentJwtPassthrough"] = "true" }));
        });
        using var client = factory.CreateClient();
        client.DefaultRequestHeaders.Authorization = new("Bearer", "fixture-bearer");
        client.DefaultRequestHeaders.Add("X-Platform-Internal-Secret", "forged");
        Assert.Equal(HttpStatusCode.Unauthorized, (await client.GetAsync("/__test/identity/admin")).StatusCode);
        Assert.Equal(0, stub.Calls);
        Assert.Equal(HttpStatusCode.OK, (await client.GetAsync("/health/live")).StatusCode);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task JsonBodyLimitRejectsKnownAndUnknownLengthsBeforeAuth(bool knownLength)
    {
        var stub = new ProfileStub();
        using var factory = Factory(stub);
        using var client = factory.CreateClient();
        ProfileStub.Attest(client);
        HttpContent content = knownLength ? new StringContent(new string('x', 16385)) : new UnknownLengthContent(new string('x', 16385));
        using var response = await client.PostAsync("/__test/identity", content);
        Assert.Equal(HttpStatusCode.RequestEntityTooLarge, response.StatusCode);
        Assert.Equal(0, stub.Calls);
        Assert.Equal("no-store", response.Headers.CacheControl!.ToString());
        using var exact = await client.PostAsync("/__test/identity", new StringContent(new string('x', 16384)));
        Assert.Equal(HttpStatusCode.OK, exact.StatusCode);
        Assert.Equal("16384", await exact.Content.ReadAsStringAsync());
    }

    [Theory]
    [InlineData("Production", "https://attacker.invalid")]
    [InlineData("Production", "http://127.0.0.1:8080")]
    [InlineData("Development", "http://169.254.169.254")]
    [InlineData("Development", "http://127.0.0.1:8080/auth/me?x=1")]
    public void ProfileOriginCannotBeArbitraryOrBrowserSupplied(string environment, string origin)
    {
        var config = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?> { ["AuthProfile:BaseUrl"] = origin }).Build();
        Assert.Throws<InvalidOperationException>(() => CurrentProfileClient.ResolveBaseAddress(new TestEnvironment(environment), config));
    }

    private static WebApplicationFactory<Program> Factory(ProfileStub stub) => RuntimeContractTests.CreateFactory().WithWebHostBuilder(builder =>
        builder.ConfigureServices(services =>
        {
            services.AddHttpClient<CurrentProfileClient>().ConfigurePrimaryHttpMessageHandler(() => stub);
            services.AddControllers().AddApplicationPart(typeof(IdentityProbeController).Assembly);
        }));

    private sealed class TestEnvironment(string name) : Microsoft.Extensions.Hosting.IHostEnvironment
    {
        public string EnvironmentName { get; set; } = name;
        public string ApplicationName { get; set; } = "tests";
        public string ContentRootPath { get; set; } = ".";
        public Microsoft.Extensions.FileProviders.IFileProvider ContentRootFileProvider { get; set; } = new Microsoft.Extensions.FileProviders.NullFileProvider();
    }

    private class UnknownLengthContent(string value) : HttpContent
    {
        private readonly byte[] _bytes = Encoding.UTF8.GetBytes(value);
        public UnknownLengthContent() : this("") { }
        protected override bool TryComputeLength(out long length) { length = 0; return false; }
        protected override Task SerializeToStreamAsync(Stream stream, TransportContext? context) => stream.WriteAsync(_bytes).AsTask();
        protected override Task<Stream> CreateContentReadStreamAsync() => Task.FromResult<Stream>(new MemoryStream(_bytes));
        protected override Task<Stream> CreateContentReadStreamAsync(CancellationToken cancellationToken) => CreateContentReadStreamAsync();
        protected override void Dispose(bool disposing) { base.Dispose(disposing); }
        // JSON MIME is explicit even when the payload is deliberately malformed.
        public static UnknownLengthContent Json(string value) => new(value) { Headers = { ContentType = new MediaTypeHeaderValue("application/json") } };
    }

    private sealed class SlowContent : HttpContent
    {
        public SlowContent() { Headers.ContentType = new("application/json"); }
        protected override bool TryComputeLength(out long length) { length = 0; return false; }
        protected override Task SerializeToStreamAsync(Stream stream, TransportContext? context) => throw new NotSupportedException();
        protected override Task<Stream> CreateContentReadStreamAsync(CancellationToken cancellationToken) => Task.FromResult<Stream>(new SlowStream());
        private sealed class SlowStream : Stream
        {
            public override bool CanRead => true;
            public override bool CanSeek => false;
            public override bool CanWrite => false;
            public override long Length => throw new NotSupportedException();
            public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
            public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default)
            { await Task.Delay(Timeout.Infinite, cancellationToken); return 0; }
            public override int Read(byte[] buffer, int offset, int count) => throw new NotSupportedException();
            public override void Flush() => throw new NotSupportedException();
            public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
            public override void SetLength(long value) => throw new NotSupportedException();
            public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        }
    }
}

public sealed class ProfileStub : HttpMessageHandler
{
    public static readonly Guid UserId = Guid.Parse("11111111-1111-4111-8111-111111111111");
    public const string Secret = "r1-test-only-proxy-secret-not-a-real-credential";
    public Guid ProfileUserId { get; set; } = UserId;
    public string[] Roles { get; set; } = new[] { "USER" };
    public bool Active { get; set; } = true;
    private int _calls;
    public int Calls => _calls;
    public string? LastUri { get; private set; }
    public string? LastAuthorization { get; private set; }
    public bool ForwardedIdentityOrCookie { get; private set; }
    public Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>>? Reply { get; set; }
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        Interlocked.Increment(ref _calls);
        LastUri = request.RequestUri!.ToString();
        LastAuthorization = request.Headers.Authorization?.ToString();
        ForwardedIdentityOrCookie = request.Headers.Any(h => h.Key.StartsWith("X-Platform-", StringComparison.OrdinalIgnoreCase) || h.Key == "Cookie");
        return Reply?.Invoke(request, cancellationToken) ?? Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
        { Content = JsonContent.Create(new { userId = ProfileUserId, email = "current@example.test", isActive = Active, roles = Roles }) });
    }
    public static void Attest(HttpClient client, string role = "USER")
    {
        client.DefaultRequestHeaders.Authorization = new("Bearer", "fixture-bearer");
        client.DefaultRequestHeaders.Add("X-Platform-User-Id", UserId.ToString());
        client.DefaultRequestHeaders.Add("X-Platform-Email", "stale@example.test");
        client.DefaultRequestHeaders.Add("X-Platform-Roles", role);
        client.DefaultRequestHeaders.Add("X-Platform-Proxy-Secret", Secret);
        client.DefaultRequestHeaders.Add("Cookie", "untrusted=fixture");
    }
}

[ApiController]
[Route("__test/identity")]
public sealed class IdentityProbeController : ControllerBase
{
    [HttpGet, Authorize]
    public object Get() => new { userId = User.FindFirstValue(ClaimTypes.NameIdentifier), email = User.FindFirstValue(ClaimTypes.Email), roles = User.FindAll(ClaimTypes.Role).Select(c => c.Value).ToArray() };
    [HttpGet("admin"), Authorize(Policy = PolicyNames.RequireAdminRole)]
    public object Admin() => Get();
    [HttpGet("user"), Authorize(Policy = PolicyNames.RequireUserRole)]
    public object CurrentUser() => Get();
    [HttpPost, Authorize]
    public async Task<IActionResult> BodyLength()
    {
        using var reader = new StreamReader(Request.Body);
        return Content((await reader.ReadToEndAsync()).Length.ToString());
    }
}
