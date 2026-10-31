using Microsoft.Extensions.Configuration;
using Npgsql;

namespace TrackingService.Infrastructure.Configuration;

public static class PostgresConfiguration
{
    public static string Resolve(IConfiguration configuration, bool production, bool migration)
    {
        if (!production)
            return configuration.GetConnectionString("Postgres")
                ?? throw new InvalidOperationException("PostgreSQL configuration is required.");
        try
        {
            var username = configuration["Database:Username"];
            var password = configuration["Database:Password"];
            var host = configuration["Database:Host"];
            var database = configuration["Database:Name"];
            var ca = configuration["Database:RootCertificate"];
            var expected = "tracking_" + (migration ? "migrator" : "runtime");
            if (username != expected || string.IsNullOrWhiteSpace(password)
                || password.Length < 32 || string.IsNullOrWhiteSpace(host)
                || Uri.CheckHostName(host) != UriHostNameType.Dns || database != "platform"
                || configuration["Database:Schema"] != "tracking"
                || configuration["Database:SslMode"] != "VerifyFull"
                || string.IsNullOrWhiteSpace(ca) || !File.Exists(ca))
                throw new InvalidOperationException();
            var certificates = new System.Security.Cryptography.X509Certificates.X509Certificate2Collection();
            certificates.ImportFromPemFile(ca);
            if (certificates.Count == 0) throw new InvalidOperationException();
            return new NpgsqlConnectionStringBuilder {
                Host = host, Database = database, Username = username, Password = password,
                SslMode = SslMode.VerifyFull, RootCertificate = ca,
                SearchPath = "tracking", IncludeErrorDetail = false, LogParameters = false
            }.ConnectionString;
        }
        catch
        {
            // Never propagate parser errors, connection strings or supplied secret values.
            throw new InvalidOperationException("Invalid production PostgreSQL identity or verified TLS configuration.");
        }
    }
}
