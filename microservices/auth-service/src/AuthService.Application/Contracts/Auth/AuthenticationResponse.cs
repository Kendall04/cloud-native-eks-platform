namespace AuthService.Application.Contracts.Auth;

public sealed record AuthenticationResponse(
    string AccessToken,
    DateTime AccessTokenExpiresAt,
    string RefreshToken,
    DateTime RefreshTokenExpiresAt);

