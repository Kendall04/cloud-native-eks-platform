using AuthService.Application.Common.Exceptions;
using AuthService.Application.Contracts.Auth;
using AuthService.Application.Interfaces;
using AuthService.Domain.Entities;
using AuthService.Infrastructure.Configuration;
using AuthService.Infrastructure.Persistence;
using AuthService.Infrastructure.Security;
using AuthService.Infrastructure.Services;
using Microsoft.AspNetCore.Identity;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Npgsql;
using Xunit;

namespace EventReliability.Tests;

public sealed class RefreshRotationTests : PostgresFixture
{
    private const string Parent = "q2-test-only-refresh-token";

    private ServiceProvider Services(string name, IJwtTokenService? jwt = null, IRefreshTokenGenerator? generator = null)
    {
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddDbContext<AuthDbContext>(options => options.UseNpgsql(
            new NpgsqlConnectionStringBuilder(Connection) { SearchPath = "auth", ApplicationName = name }.ConnectionString,
            o => o.MigrationsHistoryTable("__EFMigrationsHistory", "auth")));
        services.AddIdentityCore<ApplicationUser>().AddRoles<IdentityRole<Guid>>().AddEntityFrameworkStores<AuthDbContext>();
        services.Configure<AuthTokenOptions>(o => o.RefreshTokenExpirationDays = 7);
        services.AddSingleton<IJwtTokenService>(jwt ?? new Tokens());
        services.AddSingleton<IRefreshTokenGenerator>(generator ?? new RefreshTokenGenerator());
        services.AddScoped<IAuthService, AuthenticationService>();
        return services.BuildServiceProvider();
    }

    private async Task Seed()
    {
        await Sql("CREATE SCHEMA auth");
        using var provider = Services("seed");
        await using var scope = provider.CreateAsyncScope();
        var db = scope.ServiceProvider.GetRequiredService<AuthDbContext>();
        await db.Database.MigrateAsync();
        var user = new ApplicationUser { Email = "q2@example.invalid", UserName = "q2", FirstName = "Q", LastName = "Two" };
        db.Users.Add(user);
        db.RefreshTokens.Add(new RefreshToken { UserId = user.Id, Token = new RefreshTokenGenerator().HashToken(Parent), ExpiresAt = DateTime.UtcNow.AddDays(1) });
        await db.SaveChangesAsync();
    }

    private static Task<AuthenticationResponse> Refresh(IServiceProvider services) =>
        services.GetRequiredService<IAuthService>().RefreshAsync(new RefreshTokenRequest { RefreshToken = Parent });

    [PostgresFact]
    public async Task DisabledAccountCommitsParentRevocationWithoutSuccessor()
    {
        await Seed();
        using var provider = Services("disabled-account");
        await using (var scope = provider.CreateAsyncScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<AuthDbContext>();
            Assert.True((await db.RefreshTokens.SingleAsync()).IsActive);
            (await db.Users.SingleAsync()).IsActive = false;
            await db.SaveChangesAsync();
        }
        await using (var scope = provider.CreateAsyncScope())
        {
            var error = await Assert.ThrowsAsync<ForbiddenAppException>(() => Refresh(scope.ServiceProvider));
            Assert.Equal("User account is disabled.", error.Message);
        }
        // A fresh context proves revocation was committed despite the exception.
        await using (var scope = provider.CreateAsyncScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<AuthDbContext>();
            var parent = Assert.Single(await db.RefreshTokens.AsNoTracking().ToListAsync());
            Assert.Equal(new RefreshTokenGenerator().HashToken(Parent), parent.Token);
            Assert.NotNull(parent.RevokedAt);
            Assert.False(parent.IsActive);
            Assert.False((await db.Users.AsNoTracking().SingleAsync()).IsActive);
            await Assert.ThrowsAsync<UnauthorizedAppException>(() => Refresh(scope.ServiceProvider));
            Assert.Equal(1, await db.RefreshTokens.CountAsync());
        }
    }

    [PostgresFact]
    public async Task ConcurrentRefreshContendsInPostgresAndCreatesExactlyOneSuccessor()
    {
        await Seed();
        var gate = new GatedTokens();
        var secondName = "q2-contender-" + Guid.NewGuid().ToString("N");
        using var first = Services("q2-winner", gate);
        using var second = Services(secondName);
        await using var firstScope = first.CreateAsyncScope();
        await using var secondScope = second.CreateAsyncScope();
        var a = Refresh(firstScope.ServiceProvider);
        Task<AuthenticationResponse>? b = null;
        try
        {
            // A has consumed the row but not committed. Hold it at JWT creation.
            await gate.Entered.Task.WaitAsync(TimeSpan.FromSeconds(15));
            b = Refresh(secondScope.ServiceProvider);
            // Do not infer overlap from scheduling: observe B actually waiting
            // on PostgreSQL's lock held by A before allowing A to commit.
            await WaitForDatabaseContention(secondName);
        }
        finally { gate.Release.TrySetResult(); }
        var winner = await a.WaitAsync(TimeSpan.FromSeconds(15));
        Assert.NotNull(b);
        var loser = await Assert.ThrowsAsync<UnauthorizedAppException>(() => b!);
        Assert.Equal("Refresh token is invalid or expired.", loser.Message);

        using var verify = Services("verify");
        await using var scope = verify.CreateAsyncScope();
        var rows = await scope.ServiceProvider.GetRequiredService<AuthDbContext>().RefreshTokens.AsNoTracking().ToListAsync();
        Assert.Equal(2, rows.Count);
        var parent = Assert.Single(rows, t => t.Token == new RefreshTokenGenerator().HashToken(Parent));
        Assert.NotNull(parent.RevokedAt);
        var child = Assert.Single(rows, t => t.IsActive);
        Assert.Equal(new RefreshTokenGenerator().HashToken(winner.RefreshToken), child.Token);
        await Assert.ThrowsAsync<UnauthorizedAppException>(() => Refresh(scope.ServiceProvider));
    }

    private async Task WaitForDatabaseContention(string applicationName)
    {
        await using var connection = new NpgsqlConnection(Connection);
        await connection.OpenAsync();
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
        while (true)
        {
            await using var command = new NpgsqlCommand("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE application_name = @name AND wait_event_type = 'Lock' AND cardinality(pg_blocking_pids(pid)) > 0)", connection);
            command.Parameters.AddWithValue("name", applicationName);
            if ((bool)(await command.ExecuteScalarAsync(timeout.Token))!) return;
            await Task.Delay(20, timeout.Token);
        }
    }

    [PostgresFact]
    public async Task FailedSuccessorInsertRollsBackConsumptionAndAllowsRetry()
    {
        await Seed();
        // Force a real unique-index violation on the successor INSERT, after
        // the conditional parent UPDATE. No mocked SaveChanges or SQLite.
        using (var failing = Services("failure", generator: new DuplicateToken()))
        {
            await using var scope = failing.CreateAsyncScope();
            await Assert.ThrowsAsync<DbUpdateException>(() => Refresh(scope.ServiceProvider));
        }
        using var verify = Services("retry");
        await using var verifyScope = verify.CreateAsyncScope();
        var db = verifyScope.ServiceProvider.GetRequiredService<AuthDbContext>();
        var parent = Assert.Single(await db.RefreshTokens.AsNoTracking().ToListAsync());
        Assert.True(parent.IsActive);
        await Refresh(verifyScope.ServiceProvider);
        Assert.Equal(2, await db.RefreshTokens.CountAsync());
        Assert.Equal(1, await db.RefreshTokens.CountAsync(t => t.RevokedAt == null));
    }

    private sealed class DuplicateToken : IRefreshTokenGenerator
    {
        public string GenerateToken() => Parent;
        public string HashToken(string token) => new RefreshTokenGenerator().HashToken(token);
    }
    private sealed class Tokens : IJwtTokenService
    {
        public Task<(string Token, DateTime ExpiresAt)> GenerateAccessTokenAsync(ApplicationUser user, IReadOnlyCollection<string> roles, CancellationToken ct = default) =>
            Task.FromResult(("test-only-access-token", DateTime.UtcNow.AddMinutes(5)));
    }
    private sealed class GatedTokens : IJwtTokenService
    {
        public TaskCompletionSource Entered { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource Release { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public async Task<(string Token, DateTime ExpiresAt)> GenerateAccessTokenAsync(ApplicationUser user, IReadOnlyCollection<string> roles, CancellationToken ct = default)
        {
            Entered.TrySetResult();
            await Release.Task.WaitAsync(TimeSpan.FromSeconds(20), ct);
            return ("test-only-access-token", DateTime.UtcNow.AddMinutes(5));
        }
    }
}
