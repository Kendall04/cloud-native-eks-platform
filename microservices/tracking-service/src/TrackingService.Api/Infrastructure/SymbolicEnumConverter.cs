using System.Text.Json;
using System.Text.Json.Serialization;

namespace TrackingService.Api.Infrastructure;

/// <summary>HTTP enums accept defined symbolic names only, never numeric strings or numbers.</summary>
public sealed class SymbolicEnumConverter<T> : JsonConverter<T> where T : struct, Enum
{
    public override T Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        if (reader.TokenType == JsonTokenType.String)
        {
            var text = reader.GetString();
            foreach (var name in Enum.GetNames<T>())
                if (string.Equals(name, text, StringComparison.OrdinalIgnoreCase))
                    return Enum.Parse<T>(name);
        }
        throw new JsonException($"Expected a defined symbolic {typeof(T).Name} value.");
    }

    public override void Write(Utf8JsonWriter writer, T value, JsonSerializerOptions options)
    {
        if (!Enum.IsDefined(value)) throw new JsonException("Undefined enum value.");
        writer.WriteStringValue(value.ToString());
    }
}
