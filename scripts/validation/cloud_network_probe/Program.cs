using System.Net;
using System.Net.Sockets;
using System.Text.Json;

if (args.Length != 2 || !System.Text.RegularExpressions.Regex.IsMatch(args[0], "^[a-f0-9]{24}$") ||
    !new[] { "auth", "shipment", "tracking" }.Contains(args[1])) return 2;
var source = args[1];
var targets = new[] { "auth", "shipment", "tracking" }.Where(x => x != source).ToArray();
var samples = new List<object>();
// Standard CNI mode initially allows traffic while policies converge. The operator must
// additionally capture PolicyEndpoint bindings before accepting these observations.
await Task.Delay(TimeSpan.FromSeconds(60));
var pass = true;
for (var round = 0; round < 3; round++)
foreach (var target in targets)
{
    var expected = source == "tracking" || (source == "shipment" && target == "auth");
    var host = target + "-service.apps.svc.cluster.local";
    string outcome;
    string[] addresses = [];
    using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(3));
    try
    {
        addresses = (await Dns.GetHostAddressesAsync(host, deadline.Token)).Select(x => x.ToString()).ToArray();
        using var client = new TcpClient();
        await client.ConnectAsync(host, 8080, deadline.Token);
        outcome = "connected";
    }
    catch (OperationCanceledException) { outcome = addresses.Length == 0 ? "dns-timeout" : "timeout"; }
    catch (SocketException) { outcome = "socket-error"; }
    // DNS errors/refused connections never establish policy denial.
    pass &= expected ? outcome == "connected" : outcome == "timeout";
    samples.Add(new { round, target, port = 8080, outcome, addresses,
        observedAt = DateTimeOffset.UtcNow.ToString("O") });
}
Console.WriteLine(JsonSerializer.Serialize(new { schemaVersion = 1, runId = args[0], source, samples }));
return pass ? 0 : 1;
