using AuthService.Application.Common.Exceptions;
using AuthService.Application.Contracts.Admin;
using AuthService.Application.Interfaces;
using AuthService.Domain.Entities;
using AuthService.Infrastructure.Persistence;
using Microsoft.AspNetCore.Identity;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;

namespace AuthService.Infrastructure.Services;

public sealed class AdminService(
    UserManager<ApplicationUser> userManager,
    AuthDbContext dbContext,
    ILogger<AdminService> logger) : IAdminService
{
    public async Task<IReadOnlyCollection<AdminUserResponse>> GetUsersAsync(CancellationToken cancellationToken = default)
    {
        var users = await userManager.Users
            .OrderByDescending(user => user.CreatedAt)
            .ToListAsync(cancellationToken);

        var responses = new List<AdminUserResponse>(users.Count);

        foreach (var user in users)
        {
            var roles = (await userManager.GetRolesAsync(user)).ToArray();
            responses.Add(UserMappings.ToAdminUserResponse(user, roles));
        }

        return responses;
    }

    public async Task<AdminUserResponse> DisableUserAsync(Guid userId, CancellationToken cancellationToken = default)
    {
        var user = await userManager.Users.SingleOrDefaultAsync(candidate => candidate.Id == userId, cancellationToken)
            ?? throw new NotFoundException("User was not found.");

        if (!user.IsActive)
        {
            var existingRoles = (await userManager.GetRolesAsync(user)).ToArray();
            return UserMappings.ToAdminUserResponse(user, existingRoles);
        }

        user.IsActive = false;
        var updateResult = await userManager.UpdateAsync(user);

        if (!updateResult.Succeeded)
        {
            var errors = updateResult.Errors.Select(error => error.Description).ToArray();
            throw new ValidationException("Failed to disable user.", errors);
        }

        var activeTokens = await dbContext.RefreshTokens
            .Where(token => token.UserId == userId && token.RevokedAt == null && token.ExpiresAt > DateTime.UtcNow)
            .ToListAsync(cancellationToken);

        foreach (var token in activeTokens)
        {
            token.RevokedAt = DateTime.UtcNow;
        }

        await dbContext.SaveChangesAsync(cancellationToken);
        await userManager.UpdateSecurityStampAsync(user);

        logger.LogInformation("User {UserId} disabled by administrator", userId);

        var roles = (await userManager.GetRolesAsync(user)).ToArray();
        return UserMappings.ToAdminUserResponse(user, roles);
    }
}
