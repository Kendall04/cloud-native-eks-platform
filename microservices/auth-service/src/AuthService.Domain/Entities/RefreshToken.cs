namespace AuthService.Domain.Entities;

public sealed class RefreshToken
{
    public Guid Id { get; set; } = Guid.NewGuid();

    public Guid UserId { get; set; }

    public string Token { get; set; } = string.Empty;

    public DateTime ExpiresAt { get; set; }

    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    public DateTime? RevokedAt { get; set; }

    public bool IsExpired => ExpiresAt <= DateTime.UtcNow;

    public bool IsActive => RevokedAt is null && !IsExpired;

    public ApplicationUser? User { get; set; }
}

