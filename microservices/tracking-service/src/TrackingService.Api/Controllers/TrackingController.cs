using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using TrackingService.Api.Extensions;
using TrackingService.Application.Common.Authorization;
using TrackingService.Application.Contracts.Tracking;
using TrackingService.Application.Interfaces;

namespace TrackingService.Api.Controllers;

[ApiController]
[Route("tracking")]
public sealed class TrackingController(ITrackingEventsService trackingEventsService) : ControllerBase
{
    [Authorize(Policy = PolicyNames.RequireUserRole)]
    [HttpGet("by-shipment/{shipmentId:guid}")]
    [ProducesResponseType(typeof(IReadOnlyCollection<TrackingEventResponse>), StatusCodes.Status200OK)]
    public async Task<ActionResult<IReadOnlyCollection<TrackingEventResponse>>> GetByShipmentId(
        [FromRoute] Guid shipmentId,
        CancellationToken cancellationToken)
    {
        var response = await trackingEventsService.GetTimelineByShipmentIdAsync(
            shipmentId,
            User.GetRequiredUserContext(),
            cancellationToken);
        return Ok(response);
    }

    [Authorize(Policy = PolicyNames.RequireUserRole)]
    [HttpGet("by-tracking-number/{trackingNumber}")]
    [ProducesResponseType(typeof(IReadOnlyCollection<TrackingEventResponse>), StatusCodes.Status200OK)]
    public async Task<ActionResult<IReadOnlyCollection<TrackingEventResponse>>> GetByTrackingNumber(
        [FromRoute] string trackingNumber,
        CancellationToken cancellationToken)
    {
        var response = await trackingEventsService.GetTimelineByTrackingNumberAsync(
            trackingNumber,
            User.GetRequiredUserContext(),
            cancellationToken);
        return Ok(response);
    }
}
