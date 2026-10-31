using System.Security.Cryptography;
using ShipmentService.Application.Interfaces;

namespace ShipmentService.Infrastructure.Services;

public sealed class TrackingNumberGenerator : ITrackingNumberGenerator
{
    private const string Alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

    public string Generate()
    {
        Span<byte> bytes = stackalloc byte[12];
        RandomNumberGenerator.Fill(bytes);

        var chars = new char[12];

        for (var index = 0; index < chars.Length; index++)
        {
            chars[index] = Alphabet[bytes[index] % Alphabet.Length];
        }

        return $"SHP-{new string(chars)}";
    }
}
