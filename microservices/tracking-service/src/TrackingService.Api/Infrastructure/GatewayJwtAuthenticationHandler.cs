using System.Net.Http.Headers;
using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using Microsoft.AspNetCore.Authentication;
using Microsoft.Extensions.Options;
using TrackingService.Application.Common.Authorization;
using TrackingService.Infrastructure.Configuration;

namespace TrackingService.Api.Infrastructure;

public sealed class GatewayJwtAuthenticationHandler(
    IOptionsMonitor<AuthenticationSchemeOptions> options,
    IOptions<PlatformAuthOptions> platformAuthOptions,
    CurrentProfileClient profiles,
    ILoggerFactory logger,
    UrlEncoder encoder)
    : AuthenticationHandler<AuthenticationSchemeOptions>(options, logger, encoder)
{
    private int _failureStatus = StatusCodes.Status401Unauthorized;

    protected override async Task<AuthenticateResult> HandleAuthenticateAsync()
    {
        var names = new[] { PlatformHeaderNames.UserId, PlatformHeaderNames.Email,
            PlatformHeaderNames.Roles, PlatformHeaderNames.TrustedProxySecret };
        if (!names.Any(Request.Headers.ContainsKey))
            return Request.Headers.ContainsKey("Authorization") ? Reject() : AuthenticateResult.NoResult();

        // Reject ambiguous headers and forged gateway envelopes before contacting Auth.
        if (names.Any(name => Request.Headers[name].Count > 1) ||
            Request.Headers[PlatformHeaderNames.TrustedProxySecret].Count != 1 ||
            Request.Headers[PlatformHeaderNames.UserId].Count != 1) return Reject();
        var expectedSecret = platformAuthOptions.Value.TrustedProxySecret;
        var secret = Request.Headers[PlatformHeaderNames.TrustedProxySecret].ToString();
        if (string.IsNullOrWhiteSpace(expectedSecret) || secret.Length > 512 || !SecretsEqual(secret, expectedSecret) ||
            !Guid.TryParseExact(Request.Headers[PlatformHeaderNames.UserId].ToString(), "D", out var userId) || userId == Guid.Empty)
            return Reject();
        var authorization = Request.Headers.Authorization;
        if (authorization.Count != 1 || authorization[0]!.Length > 8192 ||
            !AuthenticationHeaderValue.TryParse(authorization[0], out var bearer) ||
            !string.Equals(bearer.Scheme, "Bearer", StringComparison.OrdinalIgnoreCase) ||
            string.IsNullOrEmpty(bearer.Parameter) || bearer.Parameter.Any(c => char.IsWhiteSpace(c) || char.IsControl(c) || c == ','))
            return Reject();

        var profile = await profiles.VerifyAsync(bearer.Parameter, userId, Context.RequestAborted);
        if (profile.Status != ProfileStatus.Verified)
            return Reject(profile.Status switch
            {
                ProfileStatus.Forbidden => StatusCodes.Status403Forbidden,
                ProfileStatus.Unavailable => StatusCodes.Status503ServiceUnavailable,
                _ => StatusCodes.Status401Unauthorized
            });

        // Bind the current profile to the attested ID, then discard snapshot email/roles.
        var claims = new List<Claim>
        {
            new(ClaimTypes.NameIdentifier, profile.UserId.ToString()),
            new(ClaimNames.UserId, profile.UserId.ToString()),
            new(ClaimTypes.Email, profile.Email!),
            new(ClaimNames.Email, profile.Email!)
        };
        foreach (var role in profile.Roles!)
        {
            claims.Add(new Claim(ClaimTypes.Role, role));
            claims.Add(new Claim(ClaimNames.Roles, role));
        }
        var principal = new ClaimsPrincipal(new ClaimsIdentity(claims, Scheme.Name, ClaimTypes.NameIdentifier, ClaimTypes.Role));
        return AuthenticateResult.Success(new AuthenticationTicket(principal, Scheme.Name));
    }

    private AuthenticateResult Reject(int status = StatusCodes.Status401Unauthorized)
    {
        _failureStatus = status;
        return AuthenticateResult.Fail("Identity validation failed.");
    }

    protected override Task HandleChallengeAsync(AuthenticationProperties properties) => WriteFailure(_failureStatus);
    protected override Task HandleForbiddenAsync(AuthenticationProperties properties) => WriteFailure(StatusCodes.Status403Forbidden);

    private Task WriteFailure(int status)
    {
        Response.StatusCode = status;
        Response.Headers.CacheControl = "no-store";
        if (status == StatusCodes.Status401Unauthorized) Response.Headers.WWWAuthenticate = "Bearer";
        return Response.WriteAsJsonAsync(new { status, title = status == 503 ? "Identity service unavailable." : "Access denied." }, Context.RequestAborted);
    }

    private static bool SecretsEqual(string candidate, string expected)
    {
        var candidateBytes = Encoding.UTF8.GetBytes(candidate);
        var expectedBytes = Encoding.UTF8.GetBytes(expected);
        return candidateBytes.Length == expectedBytes.Length && CryptographicOperations.FixedTimeEquals(candidateBytes, expectedBytes);
    }
}
