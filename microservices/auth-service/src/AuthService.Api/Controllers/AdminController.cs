using AuthService.Application.Common.Authorization;
using AuthService.Application.Contracts.Admin;
using AuthService.Application.Interfaces;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace AuthService.Api.Controllers;

[ApiController]
[Authorize(Policy = PolicyNames.RequireAdminRole)]
[Route("admin")]
public sealed class AdminController(IAdminService adminService) : ControllerBase
{
    [HttpGet("users")]
    [ProducesResponseType(typeof(IReadOnlyCollection<AdminUserResponse>), StatusCodes.Status200OK)]
    public async Task<ActionResult<IReadOnlyCollection<AdminUserResponse>>> GetUsers(
        CancellationToken cancellationToken)
    {
        var response = await adminService.GetUsersAsync(cancellationToken);
        return Ok(response);
    }

    [HttpPost("users/{id:guid}/disable")]
    [ProducesResponseType(typeof(AdminUserResponse), StatusCodes.Status200OK)]
    public async Task<ActionResult<AdminUserResponse>> DisableUser(
        [FromRoute] Guid id,
        CancellationToken cancellationToken)
    {
        var response = await adminService.DisableUserAsync(id, cancellationToken);
        return Ok(response);
    }
}
