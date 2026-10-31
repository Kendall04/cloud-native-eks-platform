using Microsoft.Extensions.Options;
using Microsoft.EntityFrameworkCore;
using TrackingService.Infrastructure.Configuration;

namespace TrackingService.Infrastructure.Persistence;

public sealed class DatabaseInitializer(
    TrackingDbContext dbContext,
    IOptions<DatabaseOptions> databaseOptions)
{
    private readonly DatabaseOptions _databaseOptions = databaseOptions.Value;

    public async Task InitializeAsync(CancellationToken cancellationToken = default)
    {
        await dbContext.Database.MigrateAsync(cancellationToken);
    }
}
