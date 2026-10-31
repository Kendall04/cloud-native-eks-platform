using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using ShipmentService.Api.Infrastructure;
using ShipmentService.Application.Contracts.Shipments;
using ShipmentService.Application.Interfaces;

namespace ShipmentService.Api.Controllers;

[ApiController]
[ApiExplorerSettings(IgnoreApi = true)]
[Route("internal/shipments")]
public sealed class InternalShipmentsController(
    IShipmentService shipmentService,
    InternalRequestAuthenticator internalRequestAuthenticator) : ControllerBase
{
    [AllowAnonymous]
    [HttpGet("{id:guid}/exists")]
    [ProducesResponseType(typeof(ShipmentExistsResponse), StatusCodes.Status200OK)]
    public async Task<ActionResult<ShipmentExistsResponse>> Exists(
        [FromRoute] Guid id,
        CancellationToken cancellationToken)
    {
        if (!internalRequestAuthenticator.IsAuthorized(Request))
        {
            return Unauthorized();
        }

        var exists = await shipmentService.ExistsAsync(id, cancellationToken);
        return Ok(new ShipmentExistsResponse(exists));
    }

    [AllowAnonymous]
    [HttpGet("{id:guid}")]
    [ProducesResponseType(typeof(ShipmentSummaryResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<ShipmentSummaryResponse>> GetById(
        [FromRoute] Guid id,
        CancellationToken cancellationToken)
    {
        if (!internalRequestAuthenticator.IsAuthorized(Request))
        {
            return Unauthorized();
        }

        var shipment = await shipmentService.GetSummaryByIdAsync(id, cancellationToken);
        return shipment is null ? NotFound() : Ok(shipment);
    }

    [AllowAnonymous]
    [HttpGet("by-tracking/{trackingNumber}")]
    [ProducesResponseType(typeof(ShipmentSummaryResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<ShipmentSummaryResponse>> GetByTrackingNumber(
        [FromRoute] string trackingNumber,
        CancellationToken cancellationToken)
    {
        if (!internalRequestAuthenticator.IsAuthorized(Request))
        {
            return Unauthorized();
        }

        var shipment = await shipmentService.GetSummaryByTrackingNumberAsync(trackingNumber, cancellationToken);
        return shipment is null ? NotFound() : Ok(shipment);
    }

    public sealed record ShipmentExistsResponse(bool Exists);
}
