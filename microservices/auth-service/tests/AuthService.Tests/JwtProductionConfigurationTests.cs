using System.Security.Cryptography;
using AuthService.Infrastructure.Configuration;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Options;
using Xunit;

namespace AuthService.Tests;

public sealed class JwtProductionConfigurationTests
{
    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("short")]
    [InlineData("replace-with-a-32-byte-or-longer-secret")]
    [InlineData("CHANGE-ME-this-is-a-long-placeholder-key")]
    [InlineData("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")]
    [InlineData("                                    ")]
    public void ProductionRejectsUnsafeConfigurationAtStartup(string? secret)
    {
        using var factory = new WebApplicationFactory<Program>().WithWebHostBuilder(builder =>
        {
            builder.UseEnvironment("Production");
            builder.ConfigureAppConfiguration((_, config) => config.AddInMemoryCollection(
                new Dictionary<string, string?> { ["Jwt:Secret"] = secret }));
        });
        var exception = Assert.Throws<OptionsValidationException>(() => factory.CreateClient());
        if (!string.IsNullOrWhiteSpace(secret)) Assert.DoesNotContain(secret, exception.Message);
    }

    [Fact]
    public void ProductionAcceptsRandomSigningSecret()
    {
        JwtProductionValidation.Validate(new JwtOptions
        {
            Issuer = "test-issuer", Audience = "test-audience",
            Secret = Convert.ToBase64String(RandomNumberGenerator.GetBytes(48))
        }, true);
        using var factory = RuntimeContractTests.CreateFactory();
        using var client = factory.CreateClient();
    }
}
