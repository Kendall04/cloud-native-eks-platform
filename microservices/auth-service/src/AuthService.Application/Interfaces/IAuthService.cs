using AuthService.Application.Contracts.Auth;

namespace AuthService.Application.Interfaces;

public interface IAuthService
{
    Task<RegisterUserResponse> RegisterAsync(RegisterUserRequest request, CancellationToken cancellationToken = default);

    Task<AuthenticationResponse> LoginAsync(LoginRequest request, CancellationToken cancellationToken = default);

    Task<AuthenticationResponse> RefreshAsync(RefreshTokenRequest request, CancellationToken cancellationToken = default);

    Task<UserProfileResponse> GetUserProfileAsync(Guid userId, CancellationToken cancellationToken = default);

    Task<TokenValidationResponse> ValidateTokenAsync(Guid userId, CancellationToken cancellationToken = default);
}

