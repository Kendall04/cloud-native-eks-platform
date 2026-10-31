namespace ShipmentService.Api.Infrastructure;

public static class PlatformHeaderNames
{
    public const string UserId = "X-Platform-User-Id";
    public const string Email = "X-Platform-Email";
    public const string Roles = "X-Platform-Roles";
    public const string TrustedProxySecret = "X-Platform-Proxy-Secret";
    public const string InternalServiceSecret = "X-Platform-Internal-Secret";
}
