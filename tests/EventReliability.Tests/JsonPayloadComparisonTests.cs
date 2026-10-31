using System.Text.Json.Nodes;
using Xunit;

namespace EventReliability.Tests;

public sealed class JsonPayloadComparisonTests
{
    private const string Original = """{"nested":{"value":1},"items":[true,null,"x"]}""";

    [Fact]
    public void PropertyOrderAndWhitespaceDoNotChangeSemanticPayload()
    {
        const string reordered = """
            { "items": [ true, null, "x" ], "nested": { "value": 1 } }
            """;
        Assert.NotEqual(Original, reordered);
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(Original), JsonNode.Parse(reordered)));
    }

    [Theory]
    [InlineData("""{"nested":{"value":2},"items":[true,null,"x"]}""")]
    [InlineData("""{"nested":{"value":"1"},"items":[true,null,"x"]}""")]
    [InlineData("""{"nested":{"value":1},"items":[null,true,"x"]}""")]
    [InlineData("""{"nested":{"value":1},"items":[false,null,"x"]}""")]
    [InlineData("""{"nested":{"value":1},"items":[true,"null","x"]}""")]
    [InlineData("""{"nested":{},"items":[true,null,"x"]}""")]
    [InlineData("""{"nested":{"value":1,"extra":null},"items":[true,null,"x"]}""")]
    public void MeaningfulPayloadChangesAreNotEquivalent(string changed)
    {
        Assert.False(JsonNode.DeepEquals(JsonNode.Parse(Original), JsonNode.Parse(changed)));
    }
}
