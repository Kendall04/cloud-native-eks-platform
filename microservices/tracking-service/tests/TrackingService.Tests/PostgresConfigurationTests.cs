using Microsoft.Extensions.Configuration;
using TrackingService.Infrastructure.Configuration;
using Npgsql;
using Xunit;
namespace TrackingService.Tests;
public sealed class PostgresConfigurationTests
{
    private static Dictionary<string,string?> Valid() => new() {
        ["Database:Host"] = "db.example.invalid", ["Database:Name"] = "platform",
        ["Database:Schema"] = "tracking", ["Database:Username"] = "tracking_runtime",
        ["Database:Password"] = new string('x', 48), ["Database:SslMode"] = "VerifyFull",
        ["Database:RootCertificate"] = Path.Combine(AppContext.BaseDirectory, "rds-global-bundle.pem")
    };
    [Theory]
    [InlineData("Database:SslMode", "Require")]
    [InlineData("Database:SslMode", "Disable")]
    [InlineData("Database:Password", "")]
    [InlineData("Database:Username", "platform_admin")]
    [InlineData("Database:Username", "")]
    [InlineData("Database:RootCertificate", "missing.pem")]
    [InlineData("Database:Host", "")]
    public void InvalidProductionConfigurationFailsWithoutLeakingValues(string key, string value)
    {
        var data=Valid(); data[key]=value;
        var error=Assert.Throws<InvalidOperationException>(() => PostgresConfiguration.Resolve(new ConfigurationBuilder().AddInMemoryCollection(data).Build(), true, false));
        Assert.DoesNotContain(new string('x',48), error.Message);
    }
    [Fact]
    public void VerifiedConfigurationUsesServiceRuntimeIdentity()
    {
        var config=new ConfigurationBuilder().AddInMemoryCollection(Valid()).Build();
        var connection=new NpgsqlConnectionStringBuilder(PostgresConfiguration.Resolve(config,true,false));
        Assert.Equal(SslMode.VerifyFull, connection.SslMode);
        Assert.Equal("tracking_runtime",connection.Username);
        Assert.Throws<InvalidOperationException>(() => PostgresConfiguration.Resolve(config,true,true));
    }
    [Fact]
    public void MigratorIsAcceptedOnlyForMigration()
    {
        var data=Valid(); data["Database:Username"]="tracking_migrator";
        var config=new ConfigurationBuilder().AddInMemoryCollection(data).Build();
        Assert.NotEmpty(PostgresConfiguration.Resolve(config,true,true));
        Assert.Throws<InvalidOperationException>(() => PostgresConfiguration.Resolve(config,true,false));
    }
}
