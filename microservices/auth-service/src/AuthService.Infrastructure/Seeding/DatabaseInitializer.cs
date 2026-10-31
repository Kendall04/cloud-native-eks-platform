using AuthService.Domain.Constants;
using AuthService.Domain.Entities;
using AuthService.Infrastructure.Configuration;
using Microsoft.AspNetCore.Identity;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace AuthService.Infrastructure.Seeding;

public sealed class DatabaseInitializer(
    Persistence.AuthDbContext dbContext,
    RoleManager<IdentityRole<Guid>> roleManager,
    UserManager<ApplicationUser> userManager,
    IOptions<DatabaseOptions> databaseOptions,
    IOptions<BootstrapAdminOptions> bootstrapAdminOptions,
    ILogger<DatabaseInitializer> logger)
{
    private readonly DatabaseOptions _databaseOptions = databaseOptions.Value;

    public async Task InitializeAsync(CancellationToken cancellationToken = default)
    {
        await dbContext.Database.MigrateAsync(cancellationToken);

        foreach (var roleName in new[] { ApplicationRoles.User, ApplicationRoles.Admin })
        {
            var exists = await roleManager.RoleExistsAsync(roleName);

            if (exists)
            {
                continue;
            }

            var result = await roleManager.CreateAsync(new IdentityRole<Guid>(roleName));

            if (!result.Succeeded)
            {
                var errors = string.Join("; ", result.Errors.Select(error => error.Description));
                throw new InvalidOperationException($"Failed to seed role '{roleName}': {errors}");
            }

            logger.LogInformation("Seeded role {RoleName}", roleName);
        }

        await SeedBootstrapAdminAsync(userManager, bootstrapAdminOptions.Value, logger);
    }

    private static async Task SeedBootstrapAdminAsync(
        UserManager<ApplicationUser> userManager,
        BootstrapAdminOptions options,
        ILogger logger)
    {
        if (!options.IsConfigured)
        {
            return;
        }

        var email = options.Email!.Trim().ToLowerInvariant();
        var existingUser = await userManager.FindByEmailAsync(email);

        if (existingUser is null)
        {
            var adminUser = new ApplicationUser
            {
                Email = email,
                UserName = email,
                FirstName = options.FirstName.Trim(),
                LastName = options.LastName.Trim(),
                CreatedAt = DateTime.UtcNow,
                IsActive = true,
                EmailConfirmed = true
            };

            var createResult = await userManager.CreateAsync(adminUser, options.Password!);

            if (!createResult.Succeeded)
            {
                var errors = string.Join("; ", createResult.Errors.Select(error => error.Description));
                throw new InvalidOperationException($"Failed to create bootstrap admin user: {errors}");
            }

            existingUser = adminUser;
            logger.LogInformation("Seeded bootstrap admin user {Email}", email);
        }

        foreach (var roleName in new[] { ApplicationRoles.Admin, ApplicationRoles.User })
        {
            if (await userManager.IsInRoleAsync(existingUser, roleName))
            {
                continue;
            }

            var addRoleResult = await userManager.AddToRoleAsync(existingUser, roleName);

            if (!addRoleResult.Succeeded)
            {
                var errors = string.Join("; ", addRoleResult.Errors.Select(error => error.Description));
                throw new InvalidOperationException(
                    $"Failed to assign role '{roleName}' to bootstrap admin user: {errors}");
            }
        }
    }
}
