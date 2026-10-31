using System.ComponentModel.DataAnnotations;

namespace AuthService.Infrastructure.Configuration;

public sealed class AuthTokenOptions
{
    public const string SectionName = "Auth";

    [Range(1, 365)]
    public int RefreshTokenExpirationDays { get; set; } = 30;
}
