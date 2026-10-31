using System.Text;
using Microsoft.Extensions.Options;

namespace AuthService.Infrastructure.Configuration;

public static class JwtProductionValidation
{
    // This is a misconfiguration guard, not an entropy estimator. Provision random secrets.
    public static void Validate(JwtOptions options, bool isProduction)
    {
        if (!isProduction) return;

        var secret = options.Secret ?? string.Empty;
        string[] markers = ["replace", "placeholder", "changeme", "change-me", "change_me", "example", "development", "your-secret"];
        if (string.IsNullOrWhiteSpace(options.Issuer) || string.IsNullOrWhiteSpace(options.Audience) ||
            Encoding.UTF8.GetByteCount(secret) < 32 || secret.Any(char.IsWhiteSpace) ||
            secret.Distinct().Count() < 10 || markers.Any(marker => secret.Contains(marker, StringComparison.OrdinalIgnoreCase)))
        {
            throw new OptionsValidationException(JwtOptions.SectionName, typeof(JwtOptions),
                ["Production JWT configuration requires issuer, audience and a non-placeholder signing secret of at least 32 bytes. Generate a cryptographically random secret."]);
        }
    }
}
