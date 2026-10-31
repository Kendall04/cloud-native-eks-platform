using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using ShipmentService.Application.Common.Authorization;
using ShipmentService.Application.Common.Exceptions;

namespace ShipmentService.Api.Extensions;

public static class ClaimsPrincipalExtensions
{
    public static RequestUserContext GetRequiredUserContext(this ClaimsPrincipal principal)
    {
        var userId = principal.FindFirstValue(ClaimNames.UserId)
            ?? principal.FindFirstValue(ClaimTypes.NameIdentifier)
            ?? principal.FindFirstValue(JwtRegisteredClaimNames.Sub);

        if (string.IsNullOrWhiteSpace(userId))
        {
            throw new UnauthorizedAppException("The upstream token did not include a user identifier.");
        }

        var email = principal.FindFirstValue(ClaimNames.Email)
            ?? principal.FindFirstValue(ClaimTypes.Email);

        var roles = principal.Claims
            .Where(claim => claim.Type == ClaimTypes.Role || claim.Type == ClaimNames.Roles)
            .Select(claim => claim.Value)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();

        return new RequestUserContext(userId, email, roles);
    }
}
