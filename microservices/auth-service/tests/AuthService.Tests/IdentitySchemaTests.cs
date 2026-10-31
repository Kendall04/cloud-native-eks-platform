using AuthService.Domain.Entities;
using AuthService.Infrastructure.Persistence;
using Microsoft.AspNetCore.Identity;
using Microsoft.EntityFrameworkCore;

namespace AuthService.Tests;

public sealed class IdentitySchemaTests
{
    [Fact]
    public void PostgreSqlModelMatchesCommittedMigrationsAndIdentityConstraints()
    {
        using var db = new AuthDbContext(new DbContextOptionsBuilder<AuthDbContext>()
            .UseNpgsql("Host=localhost;Database=model_only").Options);
        Assert.False(db.Database.HasPendingModelChanges());
        foreach (var (type, properties) in new[]
        {
            (typeof(IdentityUserLogin<Guid>), new[] { "LoginProvider", "ProviderKey" }),
            (typeof(IdentityUserToken<Guid>), new[] { "LoginProvider", "Name" })
        })
            foreach (var property in properties)
            {
                var metadata = db.Model.FindEntityType(type)!.FindProperty(property)!;
                Assert.Equal(128, metadata.GetMaxLength());
                Assert.Equal("character varying(128)", metadata.GetColumnType());
            }
        foreach (var (type, property, name) in new[]
        {
            (typeof(ApplicationUser), "NormalizedUserName", "UserNameIndex"),
            (typeof(IdentityRole<Guid>), "NormalizedName", "RoleNameIndex")
        })
        {
            var index = Assert.Single(db.Model.FindEntityType(type)!.GetIndexes(), i => i.GetDatabaseName() == name);
            Assert.True(index.IsUnique);
            Assert.Equal($"\"{property}\" IS NOT NULL", index.GetFilter());
        }
    }
}
