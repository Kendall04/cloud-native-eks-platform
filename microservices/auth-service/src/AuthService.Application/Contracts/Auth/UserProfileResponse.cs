namespace AuthService.Application.Contracts.Auth;

public sealed record UserProfileResponse(
    Guid UserId,
    string Email,
    string UserName,
    string FirstName,
    string LastName,
    bool IsActive,
    DateTime CreatedAt,
    IReadOnlyCollection<string> Roles);

