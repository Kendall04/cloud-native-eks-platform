using System.Text.Json;
using System.Text.Json.Serialization;

namespace ShipmentService.Infrastructure.Messaging;

internal static class ShipmentEventJson
{
    public static JsonSerializerOptions Options { get; } = CreateOptions();

    private static JsonSerializerOptions CreateOptions()
    {
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web);
        options.Converters.Add(new JsonStringEnumConverter());
        return options;
    }
}
