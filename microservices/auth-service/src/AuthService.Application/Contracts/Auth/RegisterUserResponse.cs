namespace AuthService.Application.Contracts.Auth;

public sealed record RegisterUserResponse(
    Guid UserId,
    string Email,
    string FirstName,
    string LastName,
    DateTime CreatedAt);

