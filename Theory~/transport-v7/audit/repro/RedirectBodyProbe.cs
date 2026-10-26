using System.Net;
using System.Net.Sockets;
using System.Text;

static async Task<string> ReadRequest(TcpClient client)
{
    var stream = client.GetStream();
    using var memory = new MemoryStream();
    var buffer = new byte[1024];
    var headerEnd = -1;
    while (headerEnd < 0)
    {
        var n = await stream.ReadAsync(buffer);
        if (n == 0) break;
        memory.Write(buffer, 0, n);
        var text = Encoding.ASCII.GetString(memory.ToArray());
        headerEnd = text.IndexOf("\r\n\r\n", StringComparison.Ordinal);
    }
    var request = Encoding.ASCII.GetString(memory.ToArray());
    var length = 0;
    foreach (var line in request.Split("\r\n"))
        if (line.StartsWith("Content-Length:", StringComparison.OrdinalIgnoreCase)) int.TryParse(line[15..].Trim(), out length);
    while (memory.Length < headerEnd + 4 + length)
    {
        var n = await stream.ReadAsync(buffer);
        if (n == 0) break;
        memory.Write(buffer, 0, n);
    }
    return Encoding.UTF8.GetString(memory.ToArray());
}

var first = new TcpListener(IPAddress.Loopback, 0); first.Start();
var second = new TcpListener(IPAddress.Loopback, 0); second.Start();
var p1 = ((IPEndPoint)first.LocalEndpoint).Port; var p2 = ((IPEndPoint)second.LocalEndpoint).Port;
var firstTask = Task.Run(async () => { using var c = await first.AcceptTcpClientAsync(); var req = await ReadRequest(c); using var w = new StreamWriter(c.GetStream(), Encoding.ASCII, leaveOpen:true); var response = Encoding.ASCII.GetBytes($"HTTP/1.1 307 Temporary Redirect\r\nLocation: http://127.0.0.1:{p2}/sink\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"); await c.GetStream().WriteAsync(response); return req; });
var secondTask = Task.Run(async () => { using var c = await second.AcceptTcpClientAsync(); var req = await ReadRequest(c); await c.GetStream().WriteAsync(Encoding.ASCII.GetBytes("HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")); return req; });
using var handler = new HttpClientHandler();
using var client = new HttpClient(handler);
using var req = new HttpRequestMessage(HttpMethod.Post, $"http://127.0.0.1:{p1}/v1/events/batch") { Content = new StringContent("SYNTHETIC_EVENT_BODY", Encoding.UTF8, "application/json") };
req.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", "SYNTHETIC_CREDENTIAL");
try { using var response = await client.SendAsync(req); Console.WriteLine($"status={response.StatusCode}; first_seen={await firstTask}; redirected_request={await secondTask}"); } catch (Exception e) { Console.WriteLine(e.ToString()); Console.WriteLine("first_seen=" + await firstTask); Console.WriteLine("second_seen=" + await secondTask); }
