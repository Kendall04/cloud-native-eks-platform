namespace AuthService.Infrastructure.Configuration;

public sealed class BootstrapAdminOptions
{
    public const string SectionName = "BootstrapAdmin";

    public string? Email { get; set; }

    public string? Password { get; set; }

    public string FirstName { get; set; } = "Platform";

    public string LastName { get; set; } = "Admin";

    public bool IsConfigured =>
        !string.IsNullOrWhiteSpace(Email) &&
        !string.IsNullOrWhiteSpace(Password);
}
