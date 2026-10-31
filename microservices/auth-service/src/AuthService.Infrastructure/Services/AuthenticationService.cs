using AuthService.Application.Common.Exceptions;
using AuthService.Application.Contracts.Auth;
using AuthService.Application.Interfaces;
using AuthService.Domain.Constants;
using AuthService.Domain.Entities;
using AuthService.Infrastructure.Configuration;
using AuthService.Infrastructure.Persistence;
using Microsoft.AspNetCore.Identity;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace AuthService.Infrastructure.Services;

public sealed class AuthenticationService(
    UserManager<ApplicationUser> userManager,
    AuthDbContext dbContext,
    IJwtTokenService jwtTokenService,
    IRefreshTokenGenerator refreshTokenGenerator,
    IOptions<AuthTokenOptions> authTokenOptions,
    ILogger<AuthenticationService> logger) : IAuthService
{
    private readonly AuthTokenOptions _authTokenOptions = authTokenOptions.Value;

    public async Task<RegisterUserResponse> RegisterAsync(
        RegisterUserRequest request,
        CancellationToken cancellationToken = default)
    {
        var email = request.Email.Trim().ToLowerInvariant();
        var existingUser = await userManager.FindByEmailAsync(email);

        if (existingUser is not null)
        {
            logger.LogWarning("Registration failed because email {Email} already exists", email);
            throw new ConflictException("A user with that email address already exists.");
        }

        var user = new ApplicationUser
        {
            Id = Guid.NewGuid(),
            Email = email,
            UserName = email,
            FirstName = request.FirstName.Trim(),
            LastName = request.LastName.Trim(),
            CreatedAt = DateTime.UtcNow,
            IsActive = true,
            EmailConfirmed = true
        };

        var createResult = await userManager.CreateAsync(user, request.Password);

        if (!createResult.Succeeded)
        {
            var errors = createResult.Errors.Select(error => error.Description).ToArray();
            logger.LogWarning("Registration failed for email {Email}: {Errors}", email, string.Join("; ", errors));
            throw new ValidationException("User registration failed.", errors);
        }

        var roleResult = await userManager.AddToRoleAsync(user, ApplicationRoles.User);

        if (!roleResult.Succeeded)
        {
            var errors = roleResult.Errors.Select(error => error.Description).ToArray();
            logger.LogError("Role assignment failed for user {UserId}: {Errors}", user.Id, string.Join("; ", errors));
            throw new ValidationException("User registration completed but role assignment failed.", errors);
        }

        logger.LogInformation("User {UserId} registered successfully", user.Id);
        return UserMappings.ToRegisterResponse(user);
    }

    public async Task<AuthenticationResponse> LoginAsync(
        LoginRequest request,
        CancellationToken cancellationToken = default)
    {
        var email = request.Email.Trim().ToLowerInvariant();
        var user = await userManager.Users.SingleOrDefaultAsync(
            candidate => candidate.NormalizedEmail == userManager.NormalizeEmail(email),
            cancellationToken);

        if (user is null)
        {
            logger.LogWarning("Login failed for unknown email {Email}", email);
            throw new UnauthorizedAppException("Invalid email or password.");
        }

        if (!user.IsActive)
        {
            logger.LogWarning("Login blocked for disabled user {UserId}", user.Id);
            throw new ForbiddenAppException("User account is disabled.");
        }

        var passwordValid = await userManager.CheckPasswordAsync(user, request.Password);

        if (!passwordValid)
        {
            logger.LogWarning("Login failed for user {UserId} because of invalid credentials", user.Id);
            throw new UnauthorizedAppException("Invalid email or password.");
        }

        var roles = (await userManager.GetRolesAsync(user)).ToArray();
        var response = await IssueTokensAsync(user, roles, revokeActiveTokens: true, cancellationToken);

        logger.LogInformation("User {UserId} authenticated successfully", user.Id);
        return response;
    }

    public async Task<AuthenticationResponse> RefreshAsync(
        RefreshTokenRequest request,
        CancellationToken cancellationToken = default)
    {
        var refreshTokenHash = refreshTokenGenerator.HashToken(request.RefreshToken.Trim());
        await using var transaction = await dbContext.Database.BeginTransactionAsync(System.Data.IsolationLevel.ReadCommitted, cancellationToken);
        // PostgreSQL serializes competing UPDATEs on this row and rechecks the
        // predicate after waiting. Only the winner can create a successor.
        // ExecuteUpdate bypasses the change tracker; read the consumed row fresh.
        var consumed = await dbContext.RefreshTokens
            .Where(token => token.Token == refreshTokenHash && token.RevokedAt == null && token.ExpiresAt > DateTime.UtcNow)
            .ExecuteUpdateAsync(setters => setters.SetProperty(token => token.RevokedAt, DateTime.UtcNow), cancellationToken);
        if (consumed != 1)
        {
            logger.LogWarning("Refresh token exchange failed because token was missing, expired, or revoked");
            throw new UnauthorizedAppException("Refresh token is invalid or expired.");
        }

        var refreshToken = await dbContext.RefreshTokens.AsNoTracking()
            .Include(token => token.User)
            .SingleAsync(token => token.Token == refreshTokenHash, cancellationToken);

        if (!refreshToken.User!.IsActive)
        {
            // Preserve existing disabled-account revocation semantics.
            await transaction.CommitAsync(cancellationToken);

            logger.LogWarning("Refresh token exchange blocked for disabled user {UserId}", refreshToken.UserId);
            throw new ForbiddenAppException("User account is disabled.");
        }

        var roles = (await userManager.GetRolesAsync(refreshToken.User)).ToArray();
        var response = await IssueTokensAsync(refreshToken.User, roles, revokeActiveTokens: false, cancellationToken);
        await transaction.CommitAsync(cancellationToken);

        logger.LogInformation("Refresh token rotated for user {UserId}", refreshToken.UserId);
        return response;
    }

    public async Task<UserProfileResponse> GetUserProfileAsync(
        Guid userId,
        CancellationToken cancellationToken = default)
    {
        var user = await userManager.Users.SingleOrDefaultAsync(candidate => candidate.Id == userId, cancellationToken)
            ?? throw new NotFoundException("User was not found.");

        if (!user.IsActive)
        {
            throw new ForbiddenAppException("User account is disabled.");
        }

        var roles = (await userManager.GetRolesAsync(user)).ToArray();
        return UserMappings.ToUserProfileResponse(user, roles);
    }

    public async Task<TokenValidationResponse> ValidateTokenAsync(
        Guid userId,
        CancellationToken cancellationToken = default)
    {
        var user = await userManager.Users.SingleOrDefaultAsync(candidate => candidate.Id == userId, cancellationToken);

        if (user is null || !user.IsActive)
        {
            logger.LogWarning("Token validation failed for user {UserId}", userId);
            return new TokenValidationResponse(false, userId, string.Empty, Array.Empty<string>());
        }

        var roles = (await userManager.GetRolesAsync(user)).ToArray();
        return new TokenValidationResponse(true, user.Id, user.Email ?? string.Empty, roles);
    }

    private async Task<AuthenticationResponse> IssueTokensAsync(
        ApplicationUser user,
        IReadOnlyCollection<string> roles,
        bool revokeActiveTokens,
        CancellationToken cancellationToken)
    {
        var issuedAt = DateTime.UtcNow;

        if (revokeActiveTokens)
        {
            var activeTokens = await dbContext.RefreshTokens
                .Where(token =>
                    token.UserId == user.Id &&
                    token.RevokedAt == null &&
                    token.ExpiresAt > issuedAt)
                .ToListAsync(cancellationToken);

            foreach (var token in activeTokens)
            {
                token.RevokedAt = issuedAt;
            }
        }

        var (accessToken, accessTokenExpiresAt) = await jwtTokenService.GenerateAccessTokenAsync(
            user,
            roles,
            cancellationToken);

        var plainRefreshToken = refreshTokenGenerator.GenerateToken();
        var refreshTokenEntity = new RefreshToken
        {
            Id = Guid.NewGuid(),
            UserId = user.Id,
            Token = refreshTokenGenerator.HashToken(plainRefreshToken),
            CreatedAt = issuedAt,
            ExpiresAt = issuedAt.AddDays(_authTokenOptions.RefreshTokenExpirationDays)
        };

        dbContext.RefreshTokens.Add(refreshTokenEntity);
        await dbContext.SaveChangesAsync(cancellationToken);

        return new AuthenticationResponse(
            accessToken,
            accessTokenExpiresAt,
            plainRefreshToken,
            refreshTokenEntity.ExpiresAt);
    }
}
