using AuthService.Infrastructure.Security;

namespace AuthService.Tests.Security;

public sealed class RefreshTokenGeneratorTests
{
    private readonly RefreshTokenGenerator _generator = new();

    [Fact]
    public void GenerateToken_ReturnsDifferentValues()
    {
        var first = _generator.GenerateToken();
        var second = _generator.GenerateToken();

        Assert.NotEqual(first, second);
        Assert.NotEmpty(first);
        Assert.NotEmpty(second);
    }

    [Fact]
    public void HashToken_ReturnsDeterministicHash()
    {
        const string token = "sample-refresh-token";

        var firstHash = _generator.HashToken(token);
        var secondHash = _generator.HashToken(token);

        Assert.Equal(firstHash, secondHash);
        Assert.NotEqual(token, firstHash);
    }
}
