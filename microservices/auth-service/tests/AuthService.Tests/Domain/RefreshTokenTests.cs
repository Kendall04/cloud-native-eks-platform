using AuthService.Domain.Entities;

namespace AuthService.Tests.Domain;

public sealed class RefreshTokenTests
{
    [Fact]
    public void IsActive_ReturnsTrue_WhenTokenIsNotExpiredAndNotRevoked()
    {
        var refreshToken = new RefreshToken
        {
            ExpiresAt = DateTime.UtcNow.AddMinutes(5),
            RevokedAt = null
        };

        Assert.True(refreshToken.IsActive);
        Assert.False(refreshToken.IsExpired);
    }

    [Fact]
    public void IsActive_ReturnsFalse_WhenTokenIsRevoked()
    {
        var refreshToken = new RefreshToken
        {
            ExpiresAt = DateTime.UtcNow.AddMinutes(5),
            RevokedAt = DateTime.UtcNow
        };

        Assert.False(refreshToken.IsActive);
    }
}
