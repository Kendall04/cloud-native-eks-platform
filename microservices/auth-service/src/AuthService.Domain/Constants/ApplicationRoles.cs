namespace AuthService.Domain.Constants;

public static class ApplicationRoles
{
    public const string User = "USER";
    public const string Admin = "ADMIN";

    public static IReadOnlyCollection<string> All { get; } = new[] { User, Admin };
}

