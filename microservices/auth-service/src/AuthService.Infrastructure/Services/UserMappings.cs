using AuthService.Application.Contracts.Admin;
using AuthService.Application.Contracts.Auth;
using AuthService.Domain.Entities;

namespace AuthService.Infrastructure.Services;

internal static class UserMappings
{
    public static RegisterUserResponse ToRegisterResponse(ApplicationUser user) =>
        new(
            user.Id,
            user.Email ?? string.Empty,
            user.FirstName,
            user.LastName,
            user.CreatedAt);

    public static UserProfileResponse ToUserProfileResponse(ApplicationUser user, IReadOnlyCollection<string> roles) =>
        new(
            user.Id,
            user.Email ?? string.Empty,
            user.UserName ?? user.Email ?? string.Empty,
            user.FirstName,
            user.LastName,
            user.IsActive,
            user.CreatedAt,
            roles);

    public static AdminUserResponse ToAdminUserResponse(ApplicationUser user, IReadOnlyCollection<string> roles) =>
        new(
            user.Id,
            user.Email ?? string.Empty,
            user.UserName ?? user.Email ?? string.Empty,
            user.FirstName,
            user.LastName,
            user.IsActive,
            user.CreatedAt,
            roles);
}
