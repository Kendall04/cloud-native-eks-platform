using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using ShipmentService.Application.Common.Authorization;
using ShipmentService.Application.Contracts.Shipments;
using ShipmentService.Application.Interfaces;

namespace ShipmentService.Api.Controllers;

[ApiController]
[Authorize(Policy = PolicyNames.RequireAdminRole)]
[Route("admin/shipments")]
public sealed class AdminShipmentsController(IAdminShipmentService adminShipmentService) : ControllerBase
{
    [HttpPatch("{id:guid}")]
    [ProducesResponseType(typeof(ShipmentResponse), StatusCodes.Status200OK)]
    public async Task<ActionResult<ShipmentResponse>> Patch(
        [FromRoute] Guid id,
        [FromBody] UpdateShipmentMetadataRequest request,
        CancellationToken cancellationToken)
    {
        var response = await adminShipmentService.UpdateMetadataAsync(id, request, cancellationToken);
        return Ok(response);
    }
}
