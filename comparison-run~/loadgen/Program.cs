using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Globalization;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Daliys.Analytics.Internal.Transport;
using M7Transport.Tests;

// Sends real events to the local server through V1 (gzip JSON batches) or V7 (the real V7Session), N installs in parallel.
internal static class Program
{
    static long _next; static readonly object Gate = new object();
    static int Rps = int.Parse(Environment.GetEnvironmentVariable("LOADGEN_RPS") ?? "25");
    static void Throttle() { if (Rps <= 0) return; long wait; lock (Gate) { var now = Stopwatch.GetTimestamp(); var slot = Math.Max(now, _next); _next = slot + Stopwatch.Frequency / Rps; wait = slot - now; } if (wait > 0) Thread.Sleep((int)(wait * 1000 / Stopwatch.Frequency)); } // project limit is 30 req/s
    static int Main(string[] a)
    {
        string mode = a[0], url = a[1], file = a[2]; int installs = int.Parse(a[3]); long maxEvents = long.Parse(a[4]); int parallel = int.Parse(a[5]); string outFile = a[6];
        const string Project = "puzzle_gravity_test";
        var plan = new List<List<string>>(); var order = new List<string>(); var map = new Dictionary<string, List<string>>(); long total = 0;
        foreach (var line in File.ReadLines(Path.Combine(file)))
        {
            int s = line.IndexOf("\"split\":\"", StringComparison.Ordinal) + 9; if (line.Substring(s, 7) != "holdout") continue;
            int o = line.IndexOf("\"origin\":\"", StringComparison.Ordinal) + 10; var origin = line.Substring(o, line.IndexOf('"', o) - o);
            int ev = line.IndexOf("\"events\":", StringComparison.Ordinal) + 9; var events = line.Substring(ev, line.Length - ev - 1);
            if (!map.TryGetValue(origin, out var list)) { if (map.Count >= installs) continue; list = new List<string>(); map[origin] = list; order.Add(origin); }
            if (list.Count >= 25) continue; // the server allows an installation a burst of 30 requests, then 12 per minute
            list.Add(events); total += 100;
            if (total >= maxEvents) break;
        }
        foreach (var o in order) plan.Add(map[o]);
        var client = new HttpClient(new HttpClientHandler { MaxConnectionsPerServer = 64 });
        long sent = 0, requests = 0, failures = 0; var sw = Stopwatch.StartNew(); var errors = new System.Collections.Concurrent.ConcurrentBag<string>();
        Parallel.ForEach(plan, new ParallelOptions { MaxDegreeOfParallelism = parallel }, batches =>
        {
            var queue = new FakeQueue(); var cred = new byte[32]; RandomNumberGenerator.Create().GetBytes(cred);
            queue.Credential = Convert.ToBase64String(cred).TrimEnd('=').Replace('+', '-').Replace('/', '_');
            var http = new HttpV7Transport(client, url);
            var reg = mode == "v8" ? new V7Response(200, new byte[0], null) : http.PostJson("/v1/installs/register", "{\"schema_version\":1,\"project_id\":\"" + Project + "\",\"install_id\":\"" + queue.InstallId + "\",\"installation_credential\":\"" + queue.Credential + "\",\"sdk_name\":\"load\",\"sdk_version\":\"1\",\"app_version\":\"1.1.14\",\"build_number\":\"1\",\"platform\":\"android\"}", null);
            if (!reg.IsSuccess) { errors.Add("register " + reg.Text); return; }
            V8Session s8 = mode == "v8" ? new V8Session(new V8Settings { ProjectId = Project, SdkName = "mortris-unity", SdkVersion = "0.2.0", AppVersion = "1.1.14", BuildNumber = "214", Platform = "android" }, http, new MemoryV7AssetStore()) : null;
            V7Session session = mode == "v7" ? new V7Session(new V7Settings { ProjectId = Project, SdkName = "mortris-unity", SdkVersion = "0.2.0" }, http, new MemoryV7AssetStore()) : null;
            foreach (var batch in batches)
            {
                queue.Enqueue(batch, 100000);
                while (queue.Pending > 0)
                {
                    if (mode == "v8")
                    {
                        Throttle(); var r8 = s8.Send(queue, () => queue.ReadOldest(100));
                        if (r8.Kind != V7ResultKind.Delivered) { errors.Add("v8 " + r8.Kind + " " + r8.Status); return; }
                        Interlocked.Increment(ref requests);
                    }
                    else if (mode == "v7")
                    {
                        Throttle(); var r = session.Send(queue, queue.GetState(), () => queue.ReadOldest(100));
                        if (r.Kind != V7ResultKind.Delivered) { errors.Add("v7 " + r.Kind); return; }
                        Interlocked.Increment(ref requests);
                    }
                    else
                    {
                        Throttle(); var json = queue.ReadOldestBatch(100); var ids = new List<KeyValuePair<string, string>>();
                        var body = "{\"schema_version\":1,\"project_id\":\"" + Project + "\",\"install_id\":\"" + queue.InstallId + "\",\"sdk\":{\"name\":\"load\",\"version\":\"1\"},\"sent_at_client\":\"" + DateTimeOffset.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'", CultureInfo.InvariantCulture) + "\",\"events\":" + json + "}";
                        using (var ms = new MemoryStream())
                        {
                            using (var gz = new GZipStream(ms, CompressionLevel.Fastest, true)) { var b = Encoding.UTF8.GetBytes(body); gz.Write(b, 0, b.Length); }
                            var content = new ByteArrayContent(ms.ToArray()); content.Headers.ContentType = new MediaTypeHeaderValue("application/json"); content.Headers.ContentEncoding.Add("gzip");
                            var req = new HttpRequestMessage(HttpMethod.Post, url + "/v1/events/batch") { Content = content }; req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", queue.Credential);
                            var resp = client.SendAsync(req).GetAwaiter().GetResult(); var text = resp.Content.ReadAsStringAsync().GetAwaiter().GetResult();
                            if (!resp.IsSuccessStatusCode) { errors.Add("v1 " + (int)resp.StatusCode + " " + text.Substring(0, Math.Min(200, text.Length))); return; }
                            var parsed = (Dictionary<string, object>)MiniJson.Parse(text);
                            var acked = new List<object>();
                            foreach (var key in new[] { "accepted", "duplicates", "rejected" }) if (parsed.TryGetValue(key, out var v) && v is List<object> l) foreach (var x in l) acked.Add(x is string xs ? xs : (x as Dictionary<string, object>)?["event_id"]);
                            queue.DeleteAcknowledged(MiniJson.Serialize(acked));
                            Interlocked.Increment(ref requests);
                        }
                    }
                }
                Interlocked.Add(ref sent, 100);
            }
        });
        File.WriteAllText(outFile, "{\"mode\":\"" + mode + "\",\"events\":" + sent + ",\"requests\":" + requests + ",\"wall_s\":" + sw.Elapsed.TotalSeconds.ToString("F2", CultureInfo.InvariantCulture) + ",\"errors\":" + errors.Count + ",\"first_error\":\"" + (errors.TryPeek(out var e1) ? e1.Replace("\"", "'") : "") + "\"}");
        return errors.Count == 0 ? 0 : 2;
    }
}
