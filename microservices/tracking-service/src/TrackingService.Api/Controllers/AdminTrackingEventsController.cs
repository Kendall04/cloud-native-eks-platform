using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using TrackingService.Api.Extensions;
using TrackingService.Application.Common.Authorization;
using TrackingService.Application.Contracts.Tracking;
using TrackingService.Application.Interfaces;

namespace TrackingService.Api.Controllers;

[ApiController]
[Authorize(Policy = PolicyNames.RequireAdminRole)]
[Route("admin/tracking-events")]
public sealed class AdminTrackingEventsController(ITrackingEventsService trackingEventsService) : ControllerBase
{
    [HttpPost]
    [ProducesResponseType(typeof(TrackingEventResponse), StatusCodes.Status201Created)]
    public async Task<IActionResult> Create(
        [FromBody] CreateTrackingEventRequest request,
        CancellationToken cancellationToken)
    {
        var response = await trackingEventsService.CreateAsync(
            request,
            User.GetRequiredUserContext(),
            cancellationToken);

        return CreatedAtAction(
            "GetByShipmentId",
            "Tracking",
            new { shipmentId = response.ShipmentId },
            response);
    }
}
