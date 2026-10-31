using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using ShipmentService.Api.Extensions;
using ShipmentService.Application.Common.Authorization;
using ShipmentService.Application.Contracts.Shipments;
using ShipmentService.Application.Interfaces;

namespace ShipmentService.Api.Controllers;

[ApiController]
[Route("shipments")]
public sealed class ShipmentsController(IShipmentService shipmentService) : ControllerBase
{
    [Authorize(Policy = PolicyNames.RequireUserRole)]
    [HttpPost]
    [ProducesResponseType(typeof(ShipmentResponse), StatusCodes.Status201Created)]
    public async Task<IActionResult> Create(
        [FromBody] CreateShipmentRequest request,
        CancellationToken cancellationToken)
    {
        var response = await shipmentService.CreateAsync(
            request,
            User.GetRequiredUserContext(),
            cancellationToken);

        return CreatedAtAction(nameof(GetById), new { id = response.Id }, response);
    }

    [Authorize(Policy = PolicyNames.RequireUserRole)]
    [HttpGet("by-id/{id:guid}")]
    [ProducesResponseType(typeof(ShipmentResponse), StatusCodes.Status200OK)]
    public async Task<ActionResult<ShipmentResponse>> GetById(
        [FromRoute] Guid id,
        CancellationToken cancellationToken)
    {
        var response = await shipmentService.GetByIdAsync(
            id,
            User.GetRequiredUserContext(),
            cancellationToken);

        return Ok(response);
    }

    [Authorize(Policy = PolicyNames.RequireUserRole)]
    [HttpGet]
    [ProducesResponseType(typeof(PagedResult<ShipmentResponse>), StatusCodes.Status200OK)]
    public async Task<ActionResult<PagedResult<ShipmentResponse>>> List(
        [FromQuery] ListShipmentsRequest request,
        CancellationToken cancellationToken)
    {
        var response = await shipmentService.ListAsync(
            request,
            User.GetRequiredUserContext(),
            cancellationToken);

        return Ok(response);
    }

    [Authorize(Policy = PolicyNames.RequireUserRole)]
    [HttpGet("by-tracking/{trackingNumber}")]
    [ProducesResponseType(typeof(ShipmentResponse), StatusCodes.Status200OK)]
    public async Task<ActionResult<ShipmentResponse>> GetByTracking(
        [FromRoute] string trackingNumber,
        CancellationToken cancellationToken)
    {
        var response = await shipmentService.GetByTrackingNumberAsync(
            trackingNumber,
            User.GetRequiredUserContext(),
            cancellationToken);

        return Ok(response);
    }
}
