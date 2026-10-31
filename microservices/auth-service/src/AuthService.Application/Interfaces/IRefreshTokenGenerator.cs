namespace AuthService.Application.Interfaces;

public interface IRefreshTokenGenerator
{
    string GenerateToken();

    string HashToken(string token);
}
