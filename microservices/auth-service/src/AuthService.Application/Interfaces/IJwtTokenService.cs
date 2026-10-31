using AuthService.Domain.Entities;

namespace AuthService.Application.Interfaces;

public interface IJwtTokenService
{
    Task<(string Token, DateTime ExpiresAt)> GenerateAccessTokenAsync(
        ApplicationUser user,
        IReadOnlyCollection<string> roles,
        CancellationToken cancellationToken = default);
}

