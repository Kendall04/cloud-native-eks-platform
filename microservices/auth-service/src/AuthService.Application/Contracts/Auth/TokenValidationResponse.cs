namespace AuthService.Application.Contracts.Auth;

public sealed record TokenValidationResponse(
    bool IsValid,
    Guid UserId,
    string Email,
    IReadOnlyCollection<string> Roles);

