using AuthService.Application.Contracts.Admin;

namespace AuthService.Application.Interfaces;

public interface IAdminService
{
    Task<IReadOnlyCollection<AdminUserResponse>> GetUsersAsync(CancellationToken cancellationToken = default);

    Task<AdminUserResponse> DisableUserAsync(Guid userId, CancellationToken cancellationToken = default);
}

