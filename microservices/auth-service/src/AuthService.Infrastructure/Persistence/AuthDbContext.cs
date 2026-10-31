using AuthService.Domain.Entities;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Identity.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore;

namespace AuthService.Infrastructure.Persistence;

public sealed class AuthDbContext(DbContextOptions<AuthDbContext> options)
    : IdentityDbContext<ApplicationUser, IdentityRole<Guid>, Guid>(options)
{
    public DbSet<RefreshToken> RefreshTokens => Set<RefreshToken>();

    protected override void OnModelCreating(ModelBuilder builder)
    {
        base.OnModelCreating(builder);

        // Preserve InitialCreate's deliberate Identity schema instead of relying
        // on framework defaults. No current login/token-name use requires >128.
        builder.Entity<IdentityUserLogin<Guid>>(entity =>
        {
            entity.Property(login => login.LoginProvider).HasMaxLength(128);
            entity.Property(login => login.ProviderKey).HasMaxLength(128);
        });
        builder.Entity<IdentityUserToken<Guid>>(entity =>
        {
            entity.Property(token => token.LoginProvider).HasMaxLength(128);
            entity.Property(token => token.Name).HasMaxLength(128);
        });
        builder.Entity<IdentityRole<Guid>>()
            .HasIndex(role => role.NormalizedName).IsUnique()
            .HasDatabaseName("RoleNameIndex").HasFilter("\"NormalizedName\" IS NOT NULL");

        builder.Entity<ApplicationUser>(entity =>
        {
            entity.HasIndex(user => user.NormalizedUserName).IsUnique()
                .HasDatabaseName("UserNameIndex").HasFilter("\"NormalizedUserName\" IS NOT NULL");
            entity.Property(user => user.FirstName)
                .HasMaxLength(100)
                .IsRequired();

            entity.Property(user => user.LastName)
                .HasMaxLength(100)
                .IsRequired();

            entity.Property(user => user.CreatedAt)
                .HasDefaultValueSql("NOW()");

            entity.Property(user => user.IsActive)
                .HasDefaultValue(true);

            entity.HasMany(user => user.RefreshTokens)
                .WithOne(refreshToken => refreshToken.User)
                .HasForeignKey(refreshToken => refreshToken.UserId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        builder.Entity<RefreshToken>(entity =>
        {
            entity.ToTable("RefreshTokens");

            entity.HasKey(refreshToken => refreshToken.Id);

            entity.Property(refreshToken => refreshToken.Token)
                .HasMaxLength(512)
                .IsRequired();

            entity.Property(refreshToken => refreshToken.CreatedAt)
                .HasDefaultValueSql("NOW()");

            entity.HasIndex(refreshToken => refreshToken.Token)
                .IsUnique();

            entity.HasIndex(refreshToken => new { refreshToken.UserId, refreshToken.ExpiresAt });
        });
    }
}
