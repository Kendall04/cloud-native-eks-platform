using System.ComponentModel.DataAnnotations;

namespace AuthService.Application.Contracts.Auth;

public sealed class RefreshTokenRequest
{
    [Required]
    public string RefreshToken { get; set; } = string.Empty;
}

