namespace AuthService.Application.Contracts.Admin;

public sealed record AdminUserResponse(
    Guid UserId,
    string Email,
    string UserName,
    string FirstName,
    string LastName,
    bool IsActive,
    DateTime CreatedAt,
    IReadOnlyCollection<string> Roles);

