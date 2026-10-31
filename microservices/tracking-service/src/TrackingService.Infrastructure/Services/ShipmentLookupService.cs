using System.Net;
using System.Net.Http.Json;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using TrackingService.Application.Common.Exceptions;
using TrackingService.Application.Contracts.Shipments;
using TrackingService.Application.Interfaces;
using TrackingService.Infrastructure.Configuration;

namespace TrackingService.Infrastructure.Services;

public sealed class ShipmentLookupService(
    HttpClient httpClient,
    IOptions<PlatformAuthOptions> platformAuthOptions,
    IHostEnvironment hostEnvironment,
    ILogger<ShipmentLookupService> logger) : IShipmentLookupService
{
    private readonly PlatformAuthOptions _platformAuthOptions = platformAuthOptions.Value;
    private readonly IHostEnvironment _hostEnvironment = hostEnvironment;

    public async Task<bool> ShipmentExistsAsync(Guid shipmentId, CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, $"internal/shipments/{shipmentId}/exists");
        ApplyInternalServiceSecret(request);

        try
        {
            using var response = await httpClient.SendAsync(request, cancellationToken);

            if (!response.IsSuccessStatusCode)
            {
                logger.LogError(
                    "shipment-service returned {StatusCode} while checking existence of shipment {ShipmentId}",
                    (int)response.StatusCode,
                    shipmentId);
                throw new ServiceUnavailableAppException("shipment-service validation failed.");
            }

            var payload = await response.Content.ReadFromJsonAsync<ShipmentExistsResponse>(cancellationToken: cancellationToken)
                ?? throw new ServiceUnavailableAppException("shipment-service returned an invalid response.");

            logger.LogInformation(
                "shipment-service existence check for shipment {ShipmentId} returned {Exists}",
                shipmentId,
                payload.Exists);

            return payload.Exists;
        }
        catch (HttpRequestException exception)
        {
            logger.LogError(exception, "Failed to reach shipment-service while checking shipment {ShipmentId}", shipmentId);
            throw new ServiceUnavailableAppException("shipment-service is unavailable.");
        }
    }

    public Task<ShipmentSummary?> GetShipmentByIdAsync(Guid shipmentId, CancellationToken cancellationToken = default) =>
        SendAsync($"internal/shipments/{shipmentId}", $"shipment {shipmentId}", cancellationToken);

    public Task<ShipmentSummary?> GetShipmentByTrackingNumberAsync(
        string trackingNumber,
        CancellationToken cancellationToken = default) =>
        SendAsync(
            $"internal/shipments/by-tracking/{Uri.EscapeDataString(trackingNumber.Trim())}",
            $"tracking number {trackingNumber}",
            cancellationToken);

    private async Task<ShipmentSummary?> SendAsync(
        string path,
        string targetDescription,
        CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, path);
        ApplyInternalServiceSecret(request);

        try
        {
            using var response = await httpClient.SendAsync(request, cancellationToken);

            if (response.StatusCode == HttpStatusCode.NotFound)
            {
                logger.LogInformation("shipment-service reported {TargetDescription} as missing or inaccessible", targetDescription);
                return null;
            }

            if (response.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden)
            {
                logger.LogError(
                    "shipment-service rejected the internal validation call for {TargetDescription} with status {StatusCode}",
                    targetDescription,
                    (int)response.StatusCode);
                throw new ServiceUnavailableAppException("shipment-service internal validation failed.");
            }

            if (!response.IsSuccessStatusCode)
            {
                logger.LogError(
                    "shipment-service returned {StatusCode} while validating {TargetDescription}",
                    (int)response.StatusCode,
                    targetDescription);
                throw new ServiceUnavailableAppException("shipment-service validation failed.");
            }

            var shipment = await response.Content.ReadFromJsonAsync<ShipmentSummary>(cancellationToken: cancellationToken)
                ?? throw new ServiceUnavailableAppException("shipment-service returned an invalid response.");

            logger.LogInformation(
                "shipment-service validated {TargetDescription} as shipment {ShipmentId}",
                targetDescription,
                shipment.Id);

            return shipment;
        }
        catch (HttpRequestException exception)
        {
            logger.LogError(exception, "Failed to reach shipment-service while validating {TargetDescription}", targetDescription);
            throw new ServiceUnavailableAppException("shipment-service is unavailable.");
        }
    }

    private void ApplyInternalServiceSecret(HttpRequestMessage request)
    {
        if (string.IsNullOrWhiteSpace(_platformAuthOptions.InternalServiceSecret))
        {
            if (_hostEnvironment.IsDevelopment())
            {
                logger.LogWarning(
                    "Calling shipment-service internal endpoints in Development without PlatformAuth:InternalServiceSecret.");
            }

            return;
        }

        request.Headers.TryAddWithoutValidation(
            PlatformHeaderNames.InternalServiceSecret,
            _platformAuthOptions.InternalServiceSecret);
    }

    private sealed record ShipmentExistsResponse(bool Exists);
}
