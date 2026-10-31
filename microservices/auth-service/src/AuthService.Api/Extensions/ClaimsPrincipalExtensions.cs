using System.Security.Claims;
using AuthService.Application.Common.Authorization;
using AuthService.Application.Common.Exceptions;

namespace AuthService.Api.Extensions;

public static class ClaimsPrincipalExtensions
{
    public static Guid GetRequiredUserId(this ClaimsPrincipal principal)
    {
        var claimValue = principal.FindFirstValue(ClaimNames.UserId)
            ?? principal.FindFirstValue(ClaimTypes.NameIdentifier);

        if (!Guid.TryParse(claimValue, out var userId))
        {
            throw new UnauthorizedAppException("The access token does not contain a valid user identifier.");
        }

        return userId;
    }
}
