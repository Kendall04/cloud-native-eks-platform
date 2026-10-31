namespace ShipmentService.Api.Infrastructure;

public sealed class PlatformAuthOptions
{
    public const string SectionName = "PlatformAuth";

    public string? TrustedProxySecret { get; set; }

    public string? InternalServiceSecret { get; set; }
}
