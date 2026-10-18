using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using Daliys.Analytics.Internal.Transport;
using NUnit.Framework;
using UnityEngine;

namespace Daliys.Analytics.Internal
{
    /// <summary>
    /// V7 pieces under Unity's own runtime (Editor Mono; the player run covers IL2CPP). The exhaustive protocol, parity and server
    /// end-to-end tests live in Native~/transport-tests (dotnet); these confirm the package compiles and works inside Unity,
    /// including the native zstd plugin the Editor loads.
    /// </summary>
    public sealed class V7TransportTests
    {
        private static string Fixtures => Path.Combine(Application.dataPath, "MortrisClient", "Native~", "transport-tests", "fixtures");
        private static string Fixture(string name) => Path.Combine(Fixtures, name);

        [Test]
        public void LoopbackHttpIsAcceptedForDevelopmentButNoOtherPlainHttp()
        {
            AnalyticsOptions Options(string url) => new AnalyticsOptions { ServerUrl = url, ProjectId = "p", Environment = "test" };

            Assert.DoesNotThrow(() => Options("https://analytics.example.com").Validate());
            Assert.DoesNotThrow(() => Options("http://localhost:8080").Validate());
            Assert.DoesNotThrow(() => Options("http://127.0.0.1:8080").Validate());
            Assert.DoesNotThrow(() => Options("http://10.0.2.2:8080").Validate());
            Assert.Throws<ArgumentException>(() => Options("http://analytics.example.com").Validate());
            Assert.Throws<ArgumentException>(() => Options("http://192.168.1.10:8080").Validate());
            Assert.Throws<ArgumentException>(() => Options("ftp://localhost").Validate());
        }

        [Test]
        public void TransportV7IsOffByDefault() => Assert.That(new AnalyticsOptions().UseTransportV7, Is.False);

        [Test]
        public void NativeZstdLoadsInTheEditorAndProducesAZstdFrame()
        {
            using (var compressor = new NativeZstdCompressor(null))
            {
                var data = Enumerable.Repeat((byte)'a', 4096).ToArray();
                var compressed = compressor.Compress(data, data.Length);
                Assert.That(compressed, Is.Not.Null);
                Assert.That(compressed.Length, Is.LessThan(100));
                Assert.That(compressed.Take(4).ToArray(), Is.EqualTo(new byte[] { 0x28, 0xb5, 0x2f, 0xfd }));   // zstd frame magic
            }
        }

        [Test]
        public void EncoderPacksAFixtureBatchUnderUnityMono()
        {
            var catalog = M7Catalog.Parse(File.ReadAllBytes(Fixture("catalog-plain.json")));
            var dictionary = File.ReadAllBytes(Fixture("dictionary-plain.bin"));
            var origin = (string)((Dictionary<string, object>)MiniJson.Parse(File.ReadAllText(Fixture("expected-low.json"))))["origin"];
            using (var encoder = new M7EventEncoder(catalog, new M7Aliases(), dictionary, origin, new NativeZstdCompressor(dictionary)))
            {
                var result = encoder.Encode(File.ReadAllText(Fixture("batch-low.json")));

                Assert.That(result.Ok, Is.True, result.Failure);
                Assert.That(result.Count, Is.EqualTo(100));
                Assert.That(result.Frame[0], Is.EqualTo((byte)'M'));
                Assert.That(result.Frame[1], Is.EqualTo((byte)'7'));
                Assert.That(result.Frame.Length, Is.LessThan(8000));
                Assert.That(result.Sequences[0], Is.EqualTo(1));
            }
        }

        // --- a full session flow with tiny fakes (the dotnet project holds the full matrix) ---------------------------------

        private sealed class OneRowQueue : IAnalyticsQueueBridge
        {
            internal readonly string Payload; internal long Epoch, DroppedVersion; internal bool Settled; internal readonly string Install = Guid.NewGuid().ToString("D");
            internal OneRowQueue(string payload) { Payload = payload; }
            public void EnqueueBatch(string e, int a, long b, long c) { }
            public AnalyticsQueueState GetState() => new AnalyticsQueueState(Install, "cred", Settled ? 0 : 1);
            public AnalyticsQueueState ResetIdentity() => GetState();
            public string ReadOldestBatch(int max) => Settled ? "[]" : Payload;
            public int DeleteAcknowledged(string ids) => 0;
            public void ClearAllPendingEvents() { }
            public string GetSequenceState() => "{\"install_id\":\"" + Install + "\",\"stream_base\":1,\"next_sequence\":101,\"stream_epoch\":" + Epoch + ",\"dropped_version\":" + DroppedVersion + ",\"dropped\":[]}";
            public void SetStreamEpoch(long epoch) => Epoch = epoch;
            public int DeleteThroughSequence(long ack) { var had = Settled ? 0 : 100; Settled = ack >= 100; return Settled ? had : 0; }
            public void BeginNewStream() { Epoch = 0; DroppedVersion++; }
            public void Dispose() { }
        }

        private sealed class HealthyServer : IV7Http
        {
            private readonly byte[] _catalog, _dictionary; internal readonly List<string> Seen = new List<string>();
            internal HealthyServer(byte[] catalog, byte[] dictionary) { _catalog = catalog; _dictionary = dictionary; }
            private static string Id(byte[] d) { using (var s = SHA256.Create()) return string.Concat(s.ComputeHash(d).Take(8).Select(b => b.ToString("x2"))); }
            private static V7Response Json(string body) => new V7Response(200, Encoding.UTF8.GetBytes(body), null);
            public V7Response PostJson(string path, string json, string credential)
            {
                Seen.Add("POST " + path);
                return Json("{\"server_time\":\"t\",\"epoch\":1,\"ack_through\":0,\"missing\":[],\"alias_epoch\":\"\",\"alias_count\":0,\"assets\":{\"catalog_id\":\"" + Id(_catalog) + "\",\"dictionary_id\":\"" + Id(_dictionary) + "\"}}");
            }
            public V7Response PutJson(string path, string json, string credential) { Seen.Add("PUT " + path); return Json("{\"server_time\":\"t\",\"alias_epoch\":\"x\",\"alias_count\":1}"); }
            public V7Response PostPacket(string path, byte[] packet, IReadOnlyDictionary<string, string> headers, string credential)
            {
                Seen.Add("POST " + path);
                return Json("{\"server_time\":\"t\",\"accepted_count\":100,\"duplicate_count\":0,\"rejected\":[],\"ack_through\":100,\"missing\":[],\"client_policy\":{\"mode\":\"active\",\"next_check_seconds\":3600,\"discard_pending\":false}}");
            }
            public V7Response Get(string pathAndQuery, string credential) { Seen.Add("GET " + pathAndQuery.Split('?')[0]); return new V7Response(200, pathAndQuery.Contains("/catalog/") ? _catalog : _dictionary, null); }
        }

        [Test]
        public void SessionOpensTheStreamFetchesAssetsUploadsAliasesAndSettlesTheQueue()
        {
            var catalog = File.ReadAllBytes(Fixture("catalog-plain.json"));
            var dictionary = File.ReadAllBytes(Fixture("dictionary-plain.bin"));
            var queue = new OneRowQueue(File.ReadAllText(Fixture("batch-low.json")));
            var server = new HealthyServer(catalog, dictionary);
            using (var session = new V7Session(new V7Settings { ProjectId = "synth_indie_runner", SdkName = "mortris-unity", SdkVersion = "0.2.0" }, server, new MemoryV7AssetStore()))
            {
                var result = session.Send(queue, queue.GetState(), () => queue.ReadOldestBatch(100));

                Assert.That(result.Kind, Is.EqualTo(V7ResultKind.Delivered), result.Detail);
                Assert.That(result.Removed, Is.EqualTo(100));
                Assert.That(queue.Epoch, Is.EqualTo(1));
                Assert.That(server.Seen, Is.EqualTo(new[] { "POST /v2/streams/sync", "GET /v2/assets/catalog/" + HealthyId(catalog), "GET /v2/assets/dictionary/" + HealthyId(dictionary), "PUT /v2/streams/aliases", "POST /v2/events/packet" }));
            }
        }

        private static string HealthyId(byte[] data) { using (var sha = SHA256.Create()) return string.Concat(sha.ComputeHash(data).Take(8).Select(b => b.ToString("x2"))); }
    }
}
