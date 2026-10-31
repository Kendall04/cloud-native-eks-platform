using ShipmentService.Domain.Constants;

namespace ShipmentService.Application.Common.Authorization;

public sealed record RequestUserContext(
    string UserId,
    string? Email,
    IReadOnlyCollection<string> Roles)
{
    public bool IsAdmin => Roles.Contains(ApplicationRoles.Admin, StringComparer.OrdinalIgnoreCase);
}
