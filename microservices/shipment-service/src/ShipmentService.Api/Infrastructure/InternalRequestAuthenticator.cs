using System.Security.Cryptography;
using System.Text;
using Microsoft.Extensions.Options;

namespace ShipmentService.Api.Infrastructure;

public sealed class InternalRequestAuthenticator(
    IOptions<PlatformAuthOptions> options,
    IHostEnvironment hostEnvironment,
    ILogger<InternalRequestAuthenticator> logger)
{
    private readonly PlatformAuthOptions _options = options.Value;

    public bool IsAuthorized(HttpRequest request)
    {
        if (string.IsNullOrWhiteSpace(_options.InternalServiceSecret))
        {
            if (hostEnvironment.IsDevelopment())
            {
                logger.LogWarning(
                    "Allowing internal shipment request in Development because PlatformAuth:InternalServiceSecret is not configured.");
                return true;
            }

            logger.LogError("Rejected internal shipment request because PlatformAuth:InternalServiceSecret is not configured.");
            return false;
        }

        if (!request.Headers.TryGetValue(PlatformHeaderNames.InternalServiceSecret, out var headerValues))
        {
            logger.LogWarning("Rejected internal shipment request because the internal service secret header was missing.");
            return false;
        }

        return SecretsEqual(headerValues.ToString(), _options.InternalServiceSecret);
    }

    private static bool SecretsEqual(string candidate, string expected)
    {
        var candidateBytes = Encoding.UTF8.GetBytes(candidate);
        var expectedBytes = Encoding.UTF8.GetBytes(expected);

        return candidateBytes.Length == expectedBytes.Length &&
               CryptographicOperations.FixedTimeEquals(candidateBytes, expectedBytes);
    }
}
