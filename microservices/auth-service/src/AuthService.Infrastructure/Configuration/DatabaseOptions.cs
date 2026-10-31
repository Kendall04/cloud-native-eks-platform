using System.ComponentModel.DataAnnotations;

namespace AuthService.Infrastructure.Configuration;

public sealed class DatabaseOptions
{
    public const string SectionName = "Database";

    [Required]
    [RegularExpression("^[a-z][a-z0-9_]*$", ErrorMessage = "Database schema must be lowercase snake_case.")]
    public string Schema { get; set; } = "auth";
}
