using TrackingService.Domain.Constants;

namespace TrackingService.Application.Common.Authorization;

public sealed record RequestUserContext(
    string UserId,
    string? Email,
    IReadOnlyCollection<string> Roles)
{
    public bool IsAdmin => Roles.Contains(ApplicationRoles.Admin, StringComparer.OrdinalIgnoreCase);
}
