using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using Daliys.Analytics.Internal.Transport;
using Xunit;

namespace M7Transport.Tests
{
    /// <summary>
    /// The real thing: the C# session talks HTTP to MortrisServer (branch feat/v7-transport) on a throwaway PostgreSQL.
    /// Run through e2e/run-e2e.sh; without M7_E2E_URL these tests do nothing (and fail when M7_E2E_REQUIRED=1).
    /// </summary>
    public class E2ETests
    {
        private const string Project = "synth_indie_runner";

        private sealed class Rig : IDisposable
        {
            internal readonly string Url = Environment.GetEnvironmentVariable("M7_E2E_URL");
            internal readonly HttpClient Client = new HttpClient();
            internal readonly FakeQueue Queue = new FakeQueue();
            internal readonly MemoryV7AssetStore Store = new MemoryV7AssetStore();
            internal V7Session Session;
            internal IV7Http Http;

            internal Rig(Func<IV7Http, IV7Http> wrap = null)
            {
                var credential = new byte[32];
                using (var random = RandomNumberGenerator.Create()) random.GetBytes(credential);
                Queue.Credential = Convert.ToBase64String(credential).TrimEnd('=').Replace('+', '-').Replace('/', '_');
                var plain = new HttpV7Transport(Client, Url);
                Http = wrap != null ? wrap(plain) : plain;
                var register = plain.PostJson("/v1/installs/register", "{\"schema_version\":1,\"project_id\":\"" + Project + "\",\"install_id\":\"" + Queue.InstallId + "\",\"installation_credential\":\"" +
                    Queue.Credential + "\",\"sdk_name\":\"e2e\",\"sdk_version\":\"1\",\"app_version\":\"1\",\"build_number\":\"1\",\"platform\":\"android\"}", null);
                Assert.True(register.IsSuccess, register.Text);
                NewSession();
            }

            internal void NewSession()
            {
                Session?.Dispose();
                Session = new V7Session(new V7Settings { ProjectId = Project, SdkName = "mortris-unity", SdkVersion = "0.2.0" }, Http, Store);
            }

            internal V7SendResult Send(int max = 100) => Session.Send(Queue, Queue.GetState(), () => Queue.ReadOldestBatch(max));

            /// <summary>Sends until the queue is empty or the session stops delivering.</summary>
            internal List<V7SendResult> Drain(int guard = 20)
            {
                var results = new List<V7SendResult>();
                for (var i = 0; i < guard; i++)
                {
                    var r = Send();
                    results.Add(r);
                    if (r.Kind != V7ResultKind.Delivered) break;
                }
                return results;
            }

            internal string Sql(string sql)
            {
                var file = Path.GetTempFileName();
                File.WriteAllText(file, sql);
                try
                {
                    var start = new ProcessStartInfo("/bin/sh", "-c \"" + Environment.GetEnvironmentVariable("M7_E2E_PSQL") + " -f " + file + "\"") { RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false };
                    using (var process = Process.Start(start))
                    {
                        var output = process.StandardOutput.ReadToEnd();
                        var error = process.StandardError.ReadToEnd();
                        process.WaitForExit();
                        Assert.True(process.ExitCode == 0, error);
                        return output.Trim();
                    }
                }
                finally { File.Delete(file); }
            }

            internal long Count(string where = "true") => long.Parse(Sql("SELECT COUNT(*) FROM events WHERE project_id = '" + Project + "' AND install_id = '" + Queue.InstallId + "' AND " + where));

            internal Dictionary<string, object> Sync(long epoch, long high, string dropped = "")
            {
                var response = Http.PostJson("/v2/streams/sync", "{\"schema_version\":2,\"project_id\":\"" + Project + "\",\"install_id\":\"" + Queue.InstallId + "\",\"epoch\":" + epoch +
                    ",\"stream_base\":1,\"high_water\":" + high + ",\"dropped\":[" + dropped + "]}", Queue.Credential);
                Assert.True(response.IsSuccess, response.Text);
                return (Dictionary<string, object>)MiniJson.Parse(response.Text);
            }

            public void Dispose() { Session?.Dispose(); Client.Dispose(); }
        }

        private static bool Skip()
        {
            if (!string.IsNullOrEmpty(Environment.GetEnvironmentVariable("M7_E2E_URL"))) return false;
            Assert.True(Environment.GetEnvironmentVariable("M7_E2E_REQUIRED") != "1", "M7_E2E_URL is not set");
            return true;
        }

        private static double Num(object value) => double.Parse(((JsonNumber)value).Lexeme, CultureInfo.InvariantCulture);

        /// <summary>Compares stored rows with the fixture events they came from (order by sequence).</summary>
        private static void AssertStored(Rig rig, string profile, long firstSequence)
        {
            var expected = (List<object>)((Dictionary<string, object>)MiniJson.Parse(TestSupport.FixtureText("expected-" + profile + ".json")))["events"];
            var rows = rig.Sql("SELECT json_build_object('sequence', sequence, 'name', name, 'session_id', session_id, 'elapsed', session_elapsed_ms, 'app_version', app_version, 'props', properties)::text " +
                               "FROM events WHERE project_id = '" + Project + "' AND install_id = '" + rig.Queue.InstallId + "' AND sequence BETWEEN " + firstSequence + " AND " + (firstSequence + expected.Count - 1) + " ORDER BY sequence")
                .Split('\n', StringSplitOptions.RemoveEmptyEntries);
            Assert.Equal(expected.Count, rows.Length);
            for (var i = 0; i < rows.Length; i++)
            {
                var got = (Dictionary<string, object>)MiniJson.Parse(rows[i]);
                var want = (Dictionary<string, object>)expected[i];
                Assert.Equal(firstSequence + i, (long)Num(got["sequence"]));
                Assert.Equal((string)want["name"], (string)got["name"]);
                Assert.Equal((string)want["session_id"], (string)got["session_id"]);
                Assert.Equal(Num(want["session_elapsed_ms"]), Num(got["elapsed"]));
                var gp = (Dictionary<string, object>)got["props"];
                var wp = (Dictionary<string, object>)want["properties"];
                Assert.Equal(wp.Keys.OrderBy(k => k), gp.Keys.OrderBy(k => k));
                foreach (var key in wp.Keys)
                {
                    if (wp[key] is JsonNumber) Assert.Equal(Num(wp[key]), Num(gp[key]));
                    else Assert.Equal(wp[key], gp[key]);
                }
            }
        }

        [Fact]
        public void EveryProfileIsStoredExactlyAsSent()
        {
            if (Skip()) return;
            using (var rig = new Rig())
            {
                long offset = 0;
                foreach (var profile in new[] { "low", "high", "wide" })
                {
                    rig.Queue.Enqueue(TestSupport.FixtureText("batch-" + profile + ".json"));
                    var results = rig.Drain();
                    Assert.Equal(V7ResultKind.Delivered, results[0].Kind);
                    Assert.Equal(0, rig.Queue.Pending);
                    AssertStored(rig, profile, offset + 1);
                    offset += 100;
                }
                Assert.Equal(300, rig.Count());
                Assert.Equal(1, rig.Queue.StreamEpoch);
                var sync = rig.Sync(1, 300);
                Assert.Equal(300, (long)Num(sync["ack_through"]));
                Assert.Empty((List<object>)sync["missing"]);
            }
        }

        private sealed class DropsFirstPacketResponse : IV7Http
        {
            private readonly IV7Http _inner; private bool _dropped;
            internal DropsFirstPacketResponse(IV7Http inner) { _inner = inner; }
            public V7Response PostJson(string p, string j, string c) => _inner.PostJson(p, j, c);
            public V7Response PutJson(string p, string j, string c) => _inner.PutJson(p, j, c);
            public V7Response Get(string p, string c) => _inner.Get(p, c);
            public V7Response PostPacket(string path, byte[] packet, IReadOnlyDictionary<string, string> headers, string credential)
            {
                var real = _inner.PostPacket(path, packet, headers, credential);      // the server stored it...
                if (_dropped) return real;
                _dropped = true;
                return new V7Response(503, new byte[0], null);                          // ...but the acknowledgement never arrived
            }
        }

        [Fact]
        public void ALostAcknowledgementIsResentWithoutStoringTwice()
        {
            if (Skip()) return;
            using (var rig = new Rig(inner => new DropsFirstPacketResponse(inner)))
            {
                rig.Queue.Enqueue(TestSupport.FixtureText("batch-low.json"));
                Assert.Equal(V7ResultKind.Retry, rig.Send().Kind);
                Assert.Equal(100, rig.Queue.Pending);          // not acknowledged: the rows stay queued
                Assert.Equal(100, rig.Count());                // yet the server has them
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                Assert.Equal(0, rig.Queue.Pending);
                Assert.Equal(100, rig.Count());                // resend was recognised as duplicates
            }
        }

        [Fact]
        public void EvictedRowsAreAnnouncedSoTheAcknowledgementStillAdvances()
        {
            if (Skip()) return;
            using (var rig = new Rig())
            {
                rig.Queue.Enqueue(TestSupport.FixtureText("batch-low.json"));
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);                 // 1..100 delivered, stream open
                for (var i = 0; i < 3; i++) rig.Queue.Enqueue(TestSupport.FixtureText("batch-high.json"), 150);   // 101..400, oldest evicted down to 150 rows
                Assert.Equal(150, rig.Queue.Pending);
                var droppedBefore = rig.Queue.DroppedJson();
                Assert.NotEmpty(droppedBefore);
                var results = rig.Drain();
                Assert.All(results.Take(results.Count - 1), r => Assert.Equal(V7ResultKind.Delivered, r.Kind));
                Assert.Equal(V7ResultKind.Empty, results.Last().Kind);
                Assert.Equal(0, rig.Queue.Pending);
                Assert.Equal(250, rig.Count());                                        // 100 + the last 150
                var sync = rig.Sync(1, 400);
                Assert.Equal(400, (long)Num(sync["ack_through"]));                     // evicted 101..250 did not stall it
            }
        }

        [Fact]
        public void ACounterThatWentBackwardsContinuesUnderANewEpoch()
        {
            if (Skip()) return;
            using (var rig = new Rig())
            {
                rig.Queue.Enqueue(TestSupport.FixtureText("batch-low.json"));
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                rig.Sql("UPDATE transport_streams SET high_water = high_water + 1000 WHERE project_id = '" + Project + "'");   // the server has seen far more than this client now claims
                rig.NewSession();                                                        // a rollback is noticed when the process (re)starts and syncs
                rig.Queue.Enqueue(TestSupport.FixtureText("batch-high.json"));
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                Assert.Equal(2, rig.Queue.StreamEpoch);
                Assert.Equal(200, rig.Count());
                Assert.Equal("2", rig.Sql("SELECT COUNT(*) FROM transport_streams WHERE project_id = '" + Project + "' AND install_id = '" + rig.Queue.InstallId + "'"));
            }
        }

        [Fact]
        public void ARestartedProcessResumesTheSameStreamWithANewAliasTable()
        {
            if (Skip()) return;
            using (var rig = new Rig())
            {
                rig.Queue.Enqueue(TestSupport.FixtureText("batch-high.json"));
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                var firstAliasEpoch = rig.Sql("SELECT alias_epoch FROM transport_streams WHERE project_id = '" + Project + "'");
                rig.NewSession();                                                        // the app restarted: aliases are per process
                rig.Queue.Enqueue(TestSupport.FixtureText("batch-low.json"));
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                Assert.Equal(1, rig.Queue.StreamEpoch);
                Assert.Equal(200, rig.Count());
                Assert.NotEqual(firstAliasEpoch, rig.Sql("SELECT alias_epoch FROM transport_streams WHERE project_id = '" + Project + "'"));
                AssertStored(rig, "low", 101);
            }
        }

        [Fact]
        public void BatchesDeliveredThroughV1InTheMiddleDoNotStallTheStream()
        {
            if (Skip()) return;
            using (var rig = new Rig())
            {
                rig.Queue.Enqueue(TestSupport.FixtureText("batch-low.json"));
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);                 // 1..100 through V7
                // 101..200 carry a shape the catalog does not know: V7 declines, V1 delivers (like the uploader's fallback path).
                rig.Queue.Enqueue(TestSupport.FixtureText("batch-low.json").Replace("\"coins\"", "\"coinz\""));
                Assert.Equal(V7ResultKind.Fallback, rig.Send().Kind);
                var batch = rig.Queue.ReadOldestBatch(100);
                var v1 = "{\"schema_version\":1,\"project_id\":\"" + Project + "\",\"install_id\":\"" + rig.Queue.InstallId + "\",\"sdk\":{\"name\":\"e2e\",\"version\":\"1\"}," +
                         "\"sent_at_client\":\"" + DateTimeOffset.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'", CultureInfo.InvariantCulture) + "\",\"events\":" + batch + "}";
                using (var bytes = new MemoryStream())
                {
                    using (var gzip = new GZipStream(bytes, CompressionLevel.Fastest, true)) gzip.Write(Encoding.UTF8.GetBytes(v1), 0, Encoding.UTF8.GetByteCount(v1));
                    var content = new ByteArrayContent(bytes.ToArray());
                    content.Headers.ContentType = new MediaTypeHeaderValue("application/json");
                    content.Headers.ContentEncoding.Add("gzip");
                    var request = new HttpRequestMessage(HttpMethod.Post, rig.Url + "/v1/events/batch") { Content = content };
                    request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", rig.Queue.Credential);
                    var response = rig.Client.SendAsync(request).GetAwaiter().GetResult();
                    Assert.True(response.IsSuccessStatusCode, response.Content.ReadAsStringAsync().GetAwaiter().GetResult());
                }
                var ids = string.Join(",", MiniJson.ParseArray(batch).Cast<Dictionary<string, object>>().Select(e => "\"" + (string)e["event_id"] + "\""));
                rig.Queue.DeleteAcknowledged("[" + ids + "]");
                Assert.Equal("[101,200]", rig.Queue.DroppedJson());
                Assert.Equal(200, rig.Count());                                          // V1 stored them too

                rig.Queue.Enqueue(TestSupport.FixtureText("batch-high.json"));            // 201..300 through V7 again
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                Assert.Equal(0, rig.Queue.Pending);
                var sync = rig.Sync(1, 300);
                Assert.Equal(300, (long)Num(sync["ack_through"]));                       // the V1-delivered range was skipped, not awaited
                Assert.Equal(300, rig.Count());
            }
        }

        [Fact]
        public void AnInstallationThatWasNeverRegisteredIsRefused()
        {
            if (Skip()) return;
            using (var rig = new Rig())
            {
                rig.Queue.Credential = "A" + rig.Queue.Credential.Substring(1);           // a credential the server does not know
                rig.Queue.Enqueue(TestSupport.FixtureText("batch-low.json"));
                Assert.Equal(V7ResultKind.Unauthorized, rig.Send().Kind);
                Assert.Equal(0, rig.Count());
            }
        }
    }
}
