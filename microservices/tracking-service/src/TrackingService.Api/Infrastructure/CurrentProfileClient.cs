using System.Net;
using System.Net.Http.Headers;
using System.Text.Json;

namespace TrackingService.Api.Infrastructure;

public enum ProfileStatus { Verified, Unauthorized, Forbidden, Unavailable }

public sealed record CurrentProfile(ProfileStatus Status, Guid UserId = default,
    string? Email = null, string[]? Roles = null);

// Kept within each service's independently built Docker context. No signing key,
// shared default Authorization header, result cache, retries or gateway recursion.
public sealed class CurrentProfileClient(HttpClient client)
{
    public const int MaximumResponseBytes = 16 * 1024;
    public static readonly TimeSpan Deadline = TimeSpan.FromSeconds(8);
    public const string ProductionBaseUrl = "http://auth-service.apps.svc.cluster.local:8080/";

    public static Uri ResolveBaseAddress(IHostEnvironment environment, IConfiguration configuration)
    {
        var configured = configuration["AuthProfile:BaseUrl"];
        var allowed = environment.IsDevelopment()
            ? new[] { "http://127.0.0.1:8080/", "http://localhost:8080/", "http://cnp-local-ui-auth:8080/" }
            : new[] { ProductionBaseUrl };
        var selected = configured ?? allowed[0];
        if (!allowed.Contains(selected.TrimEnd('/') + "/", StringComparer.Ordinal))
            throw new InvalidOperationException("Auth profile origin is not an approved service address.");
        return new Uri(selected.TrimEnd('/') + "/");
    }

    public async Task<CurrentProfile> VerifyAsync(string token, Guid expectedUserId, CancellationToken cancellationToken)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(Deadline);
        try
        {
            using var request = new HttpRequestMessage(HttpMethod.Get, "auth/me");
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
            request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
            request.Headers.CacheControl = new CacheControlHeaderValue { NoCache = true, NoStore = true };
            using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, deadline.Token);
            if (response.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.NotFound)
                return new(ProfileStatus.Unauthorized);
            if (response.StatusCode == HttpStatusCode.Forbidden) return new(ProfileStatus.Forbidden);
            if (response.StatusCode != HttpStatusCode.OK ||
                response.Content.Headers.ContentType?.MediaType != "application/json" ||
                response.Content.Headers.ContentLength > MaximumResponseBytes)
                return new(ProfileStatus.Unavailable);

            // Bound actual streamed bytes too: Content-Length can be absent or false.
            await using var stream = await response.Content.ReadAsStreamAsync(deadline.Token);
            var bytes = new byte[MaximumResponseBytes + 1];
            var count = 0;
            while (count < bytes.Length)
            {
                var read = await stream.ReadAsync(bytes.AsMemory(count), deadline.Token);
                if (read == 0) break;
                count += read;
            }
            if (count > MaximumResponseBytes) return new(ProfileStatus.Unavailable);
            using var document = JsonDocument.Parse(bytes.AsMemory(0, count), new JsonDocumentOptions { MaxDepth = 8 });
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object ||
                root.EnumerateObject().Select(p => p.Name).Distinct(StringComparer.Ordinal).Count() != root.EnumerateObject().Count() ||
                !root.TryGetProperty("userId", out var id) || id.ValueKind != JsonValueKind.String ||
                !Guid.TryParseExact(id.GetString(), "D", out var userId) || userId == Guid.Empty ||
                !root.TryGetProperty("email", out var email) || email.ValueKind != JsonValueKind.String ||
                string.IsNullOrWhiteSpace(email.GetString()) || email.GetString()!.Length > 320 || email.GetString()!.Any(char.IsControl) ||
                !root.TryGetProperty("isActive", out var active) || active.ValueKind is not (JsonValueKind.True or JsonValueKind.False) ||
                !root.TryGetProperty("roles", out var roles) || roles.ValueKind != JsonValueKind.Array || roles.GetArrayLength() > 16)
                return new(ProfileStatus.Unavailable);
            var currentRoles = new List<string>();
            foreach (var role in roles.EnumerateArray())
            {
                if (role.ValueKind != JsonValueKind.String) return new(ProfileStatus.Unavailable);
                var value = role.GetString()!;
                if (string.IsNullOrWhiteSpace(value) || value.Length > 64 || value != value.Trim() ||
                    value.Any(c => char.IsControl(c) || c == ',')) return new(ProfileStatus.Unavailable);
                currentRoles.Add(value);
            }
            if (userId != expectedUserId) return new(ProfileStatus.Unauthorized);
            if (!active.GetBoolean()) return new(ProfileStatus.Forbidden);
            return new(ProfileStatus.Verified, userId, email.GetString(), currentRoles.Distinct(StringComparer.OrdinalIgnoreCase).ToArray());
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            return new(ProfileStatus.Unavailable);
        }
        catch (Exception exception) when (exception is HttpRequestException or IOException or JsonException)
        {
            // Never include upstream bodies, URLs, exception messages or tokens in a response/log.
            return new(ProfileStatus.Unavailable);
        }
    }
}
