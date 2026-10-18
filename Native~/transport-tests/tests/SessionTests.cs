using System;
using System.Collections.Generic;
using System.Linq;
using Daliys.Analytics.Internal;
using Daliys.Analytics.Internal.Transport;
using Xunit;

namespace M7Transport.Tests
{
    public class SessionTests
    {
        private sealed class Rig : IDisposable
        {
            internal readonly FakeQueue Queue = new FakeQueue();
            internal readonly ScriptedHttp Http;
            internal readonly MemoryV7AssetStore Store = new MemoryV7AssetStore();
            internal readonly V7Session Session;
            internal DateTimeOffset Now = new DateTimeOffset(2026, 10, 18, 12, 0, 0, TimeSpan.Zero);
            internal readonly string Batch;

            internal Rig(bool dictionary = true, Func<byte[], IM7Compressor> compressor = null, string profile = "low")
            {
                var catalog = TestSupport.FixtureBytes("catalog-plain.json");
                Http = new ScriptedHttp(catalog, dictionary ? TestSupport.FixtureBytes("dictionary-plain.bin") : null);
                var settings = new V7Settings { ProjectId = "synth_indie_runner", SdkName = "mortris-unity", SdkVersion = "0.2.0", Clock = () => Now };
                if (compressor != null) settings.CompressorFactory = compressor;
                Session = new V7Session(settings, Http, Store);
                Batch = TestSupport.FixtureText("batch-" + profile + ".json");
                Queue.Enqueue(Batch);
                Http.Ack = () => 100;   // the healthy server settles everything it was sent
            }

            internal V7SendResult Send(int max = 100) => Session.Send(Queue, Queue.GetState(), () => Queue.ReadOldestBatch(max));
            public void Dispose() => Session.Dispose();
        }

        [Fact]
        public void FirstSendOpensTheStreamFetchesAssetsUploadsAliasesAndSettlesTheQueue()
        {
            using (var rig = new Rig())
            {
                var result = rig.Send();
                Assert.Equal(V7ResultKind.Delivered, result.Kind);
                Assert.Equal(100, result.Removed);
                Assert.Equal("active", result.PolicyMode);
                Assert.Equal(3600, result.NextCheckSeconds);
                Assert.Equal(0, rig.Queue.Pending);

                var order = rig.Http.Calls.Select(c => c.Method + " " + c.Path.Split('?')[0]).ToList();
                Assert.Equal(new[] { "POST /v2/streams/sync", "GET /v2/assets/catalog/" + rig.Http.CatalogId, "GET /v2/assets/dictionary/" + rig.Http.DictionaryId, "PUT /v2/streams/aliases", "POST /v2/events/packet" }, order);

                var sync = (Dictionary<string, object>)MiniJson.Parse(rig.Http.Calls[0].Body);
                Assert.Equal("2", ((JsonNumber)sync["schema_version"]).Lexeme);
                Assert.Equal("0", ((JsonNumber)sync["epoch"]).Lexeme);          // no stream yet
                Assert.Equal("1", ((JsonNumber)sync["stream_base"]).Lexeme);
                Assert.Equal("100", ((JsonNumber)sync["high_water"]).Lexeme);
                Assert.Empty((List<object>)sync["dropped"]);
                Assert.Equal(1, rig.Queue.StreamEpoch);                          // the issued epoch is persisted in the queue

                var packet = rig.Http.Calls.Last();
                Assert.Equal("synth_indie_runner", packet.Headers["X-Mortris-Project"]);
                Assert.Equal(rig.Queue.InstallId, packet.Headers["X-Mortris-Install"]);
                Assert.Equal("1", packet.Headers["X-Mortris-Epoch"]);
                Assert.Equal("mortris-unity/0.2.0", packet.Headers["X-Mortris-Sdk"]);
                Assert.Equal("2026-10-18T12:00:00.000Z", packet.Headers["X-Mortris-Sent-At"]);
                Assert.Equal("credential", packet.Credential);
                Assert.Equal((byte)'M', packet.Packet[0]);
                Assert.Equal(rig.Queue.GetState().InstallationCredential, rig.Http.Calls.Last().Credential);
            }
        }

        [Fact]
        public void AssetsAreCachedAndVerifiedByContentId()
        {
            using (var rig = new Rig())
            {
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                Assert.NotNull(rig.Store.TryRead("catalog", rig.Http.CatalogId));
                // A second process (new session, same store) must not download again.
                rig.Queue.Enqueue(rig.Batch);
                rig.Http.Ack = () => 200;
                rig.Http.Calls.Clear();
                using (var second = new V7Session(new V7Settings { ProjectId = "synth_indie_runner", SdkName = "s", SdkVersion = "1", Clock = () => rig.Now }, rig.Http, rig.Store))
                {
                    Assert.Equal(V7ResultKind.Delivered, second.Send(rig.Queue, rig.Queue.GetState(), () => rig.Queue.ReadOldestBatch(100)).Kind);
                    Assert.Equal(0, rig.Http.Count("GET", "/v2/assets"));
                }
                // A tampered cache entry is refetched.
                rig.Store.Write("catalog", rig.Http.CatalogId, new byte[] { 1, 2, 3 });
                rig.Queue.Enqueue(rig.Batch);
                rig.Http.Ack = () => 300;
                rig.Http.Calls.Clear();
                using (var third = new V7Session(new V7Settings { ProjectId = "synth_indie_runner", SdkName = "s", SdkVersion = "1", Clock = () => rig.Now }, rig.Http, rig.Store))
                {
                    Assert.Equal(V7ResultKind.Delivered, third.Send(rig.Queue, rig.Queue.GetState(), () => rig.Queue.ReadOldestBatch(100)).Kind);
                    Assert.Equal(1, rig.Http.Count("GET", "/v2/assets/catalog"));
                }
            }
        }

        [Fact]
        public void AnAssetThatDoesNotMatchItsIdMakesV7UnavailableForAnHourThenRetries()
        {
            using (var rig = new Rig())
            {
                rig.Http.Catalog = new byte[] { 9, 9, 9 };      // the server hands out bytes that are not the advertised asset
                var result = rig.Send();
                Assert.Equal(V7ResultKind.Fallback, result.Kind);
                Assert.Contains("does not match", result.Detail);
                Assert.Equal(100, rig.Queue.Pending);            // nothing was removed

                var syncs = rig.Http.Count("POST", "/v2/streams/sync");
                Assert.Equal(V7ResultKind.Fallback, rig.Send().Kind);
                Assert.Equal(syncs, rig.Http.Count("POST", "/v2/streams/sync"));   // no traffic while unavailable

                rig.Now = rig.Now.AddMinutes(61);
                rig.Http.Catalog = TestSupport.FixtureBytes("catalog-plain.json");
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
            }
        }

        [Fact]
        public void AProjectWithoutAssetsKeepsUsingV1()
        {
            using (var rig = new Rig())
            {
                rig.Http.CatalogId = "";
                rig.Http.DictionaryId = "";
                var result = rig.Send();
                Assert.Equal(V7ResultKind.Fallback, result.Kind);
                Assert.Contains("no V7 catalog", result.Detail);
                Assert.Equal(100, rig.Queue.Pending);
            }
        }

        [Fact]
        public void AServerWithoutV7RoutesFallsBackAndRemembersFor()
        {
            using (var rig = new Rig())
            {
                rig.Http.Override = call => ScriptedHttp.Error(404, "not_found");
                Assert.Equal(V7ResultKind.Fallback, rig.Send().Kind);
                Assert.Equal(1, rig.Http.Calls.Count);
                Assert.Equal(V7ResultKind.Fallback, rig.Send().Kind);
                Assert.Equal(1, rig.Http.Calls.Count);           // still one: not asked again within the hour
                Assert.Equal(100, rig.Queue.Pending);
            }
        }

        [Theory]
        [InlineData(500)]
        [InlineData(503)]
        [InlineData(429)]
        [InlineData(408)]
        public void TransientFailuresAreRetriedByTheCallerWithRetryAfter(int status)
        {
            using (var rig = new Rig())
            {
                rig.Http.Override = call => call.Path == "/v2/events/packet" ? ScriptedHttp.Json(status, "{}", TimeSpan.FromSeconds(7)) : null;
                var result = rig.Send();
                Assert.Equal(V7ResultKind.Retry, result.Kind);
                Assert.Equal(TimeSpan.FromSeconds(7), result.RetryAfter);
                Assert.Equal(100, rig.Queue.Pending);
            }
        }

        [Fact]
        public void TransientSyncAndAssetFailuresAreRetriesNotFallbacks()
        {
            using (var rig = new Rig())
            {
                rig.Http.Override = call => call.Path == "/v2/streams/sync" ? ScriptedHttp.Json(503, "{}") : null;
                Assert.Equal(V7ResultKind.Retry, rig.Send().Kind);
            }
            using (var rig = new Rig())
            {
                rig.Http.Override = call => call.Path.StartsWith("/v2/assets") ? ScriptedHttp.Json(502, "{}") : null;
                Assert.Equal(V7ResultKind.Retry, rig.Send().Kind);
            }
        }

        [Fact]
        public void UnauthorizedIsReportedSoTheCallerCanReRegister()
        {
            foreach (var path in new[] { "/v2/streams/sync", "/v2/assets", "/v2/streams/aliases", "/v2/events/packet" })
                using (var rig = new Rig())
                {
                    rig.Http.Override = call => call.Path.StartsWith(path) ? ScriptedHttp.Error(401, "unauthorized") : null;
                    Assert.Equal(V7ResultKind.Unauthorized, rig.Send().Kind);
                    Assert.Equal(100, rig.Queue.Pending);
                }
        }

        [Fact]
        public void APacketTooLargeIsReportedForBatchHalving()
        {
            using (var rig = new Rig())
            {
                rig.Http.Override = call => call.Path == "/v2/events/packet" ? ScriptedHttp.Error(413, "payload_too_large") : null;
                Assert.Equal(V7ResultKind.PayloadTooLarge, rig.Send().Kind);
            }
        }

        [Fact]
        public void ARolledBackCounterOpensANewStreamAndContinues()
        {
            using (var rig = new Rig())
            {
                var syncs = 0;
                rig.Http.Override = call =>
                {
                    if (call.Path != "/v2/streams/sync") return null;
                    return ++syncs == 1 ? ScriptedHttp.Error(409, "stream_rollback", "client high_water 100 is below the server's 500") : null;
                };
                var result = rig.Send();
                Assert.Equal(V7ResultKind.Delivered, result.Kind);
                Assert.Equal(2, rig.Http.Count("POST", "/v2/streams/sync"));
                Assert.Contains("BeginNewStream", rig.Queue.Calls);
                var second = (Dictionary<string, object>)MiniJson.Parse(rig.Http.Where("POST", "/v2/streams/sync").Last().Body);
                Assert.Equal("0", ((JsonNumber)second["epoch"]).Lexeme);
            }
        }

        [Fact]
        public void AStreamTheServerForgotIsReopened()
        {
            using (var rig = new Rig())
            {
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                rig.Queue.Enqueue(rig.Batch);
                rig.Http.Ack = () => 200;
                var failed = false;
                rig.Http.Override = call =>
                {
                    if (call.Path == "/v2/events/packet" && !failed) { failed = true; return ScriptedHttp.Error(404, "unknown_stream"); }
                    return null;
                };
                rig.Http.Epoch = 2;
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                Assert.Equal(2, rig.Queue.StreamEpoch);
            }
        }

        [Fact]
        public void AnAliasEpochMismatchRestartsTheAliasUpload()
        {
            using (var rig = new Rig())
            {
                var rejected = false;
                rig.Http.Override = call =>
                {
                    if (call.Path == "/v2/events/packet" && !rejected) { rejected = true; return ScriptedHttp.Error(409, "alias_epoch_mismatch"); }
                    return null;
                };
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                var puts = rig.Http.Where("PUT", "/v2/streams/aliases").ToList();
                Assert.Equal(2, puts.Count);
                Assert.Equal("0", ((JsonNumber)((Dictionary<string, object>)MiniJson.Parse(puts[1].Body))["start"]).Lexeme);
            }
        }

        [Fact]
        public void AnAliasGapResumesFromWhatTheServerHolds()
        {
            using (var rig = new Rig(profile: "high"))
            {
                var gapped = false;
                rig.Http.Override = call =>
                {
                    if (call.Path == "/v2/streams/aliases" && !gapped) { gapped = true; return ScriptedHttp.Error(409, "alias_gap", "server holds 0 records; resend from there"); }
                    return null;
                };
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                Assert.True(rig.Http.Count("PUT", "/v2/streams/aliases") >= 2);
            }
        }

        [Fact]
        public void AnAliasConflictRebuildsTheTableUnderANewEpoch()
        {
            using (var rig = new Rig())
            {
                string first = null, second = null;
                rig.Http.Override = call =>
                {
                    if (call.Path != "/v2/streams/aliases") return null;
                    var epoch = (string)((Dictionary<string, object>)MiniJson.Parse(call.Body))["alias_epoch"];
                    if (first == null) { first = epoch; return ScriptedHttp.Error(409, "alias_conflict"); }
                    second = epoch;
                    return null;
                };
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                Assert.NotNull(second);
                Assert.NotEqual(first, second);
            }
        }

        [Fact]
        public void UnknownAssetsOnTheServerForceARefreshOfCatalogAndDictionary()
        {
            using (var rig = new Rig())
            {
                var failed = false;
                rig.Http.Override = call =>
                {
                    if (call.Path == "/v2/events/packet" && !failed) { failed = true; return ScriptedHttp.Error(409, "transport_assets_unknown"); }
                    return null;
                };
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                Assert.Equal(2, rig.Http.Count("GET", "/v2/assets/catalog"));   // the cached copy was dropped and fetched again
                Assert.Equal(2, rig.Http.Count("POST", "/v2/streams/sync"));
            }
        }

        [Fact]
        public void RowsDeliveredThroughV1AreAnnouncedAsDroppedBeforeTheNextPacket()
        {
            using (var rig = new Rig())
            {
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);          // stream open (epoch 1)
                rig.Queue.Enqueue(rig.Batch);                                    // sequences 101..200
                // V1 fallback delivers the first 10 by id; with a stream open they are journaled as dropped.
                var ids = MiniJson.ParseArray(rig.Queue.ReadOldestBatch(10)).Cast<Dictionary<string, object>>().Select(e => "\"" + (string)e["event_id"] + "\"");
                rig.Queue.DeleteAcknowledged("[" + string.Join(",", ids) + "]");
                Assert.Equal("[101,110]", rig.Queue.DroppedJson());

                rig.Http.Ack = () => 200;
                rig.Http.Calls.Clear();
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                var sync = (Dictionary<string, object>)MiniJson.Parse(rig.Http.Calls[0].Body);
                Assert.Equal("1", ((JsonNumber)sync["epoch"]).Lexeme);
                var dropped = (List<object>)sync["dropped"];
                Assert.Single(dropped);
                Assert.Equal("101", ((JsonNumber)((List<object>)dropped[0])[0]).Lexeme);
                Assert.Equal("110", ((JsonNumber)((List<object>)dropped[0])[1]).Lexeme);
                Assert.Equal(0, rig.Queue.Pending);
            }
        }

        [Fact]
        public void ASyncThatSettlesRowsMeansTheBatchIsReadAfterwards()
        {
            using (var rig = new Rig())
            {
                var readAfterSync = -1;
                rig.Http.SyncAck = () => 60;                                      // the server already holds 1..60 (a lost acknowledgement earlier)
                rig.Http.Ack = () => 100;
                var sequence = 0;
                rig.Http.Override = call =>
                {
                    if (call.Path == "/v2/events/packet") { sequence = rig.Queue.Pending; return null; }
                    return null;
                };
                var result = rig.Session.Send(rig.Queue, rig.Queue.GetState(), () => { readAfterSync = rig.Queue.Pending; return rig.Queue.ReadOldestBatch(100); });
                Assert.Equal(40, readAfterSync);                                   // 60 rows were settled by the sync before the read
                Assert.Equal(V7ResultKind.Delivered, result.Kind);
            }
        }

        [Fact]
        public void NoProgressForThreeRoundsGivesV7ARestAndLetsV1Deliver()
        {
            using (var rig = new Rig())
            {
                rig.Http.Ack = () => 0;                                            // the server keeps waiting for an earlier number
                Assert.Equal(V7ResultKind.Retry, rig.Send().Kind);
                Assert.Equal(V7ResultKind.Retry, rig.Send().Kind);
                var third = rig.Send();
                Assert.Equal(V7ResultKind.Fallback, third.Kind);
                Assert.Contains("without settling", third.Detail);
                Assert.Equal(100, rig.Queue.Pending);
            }
        }

        [Fact]
        public void RepeatedInvalidPacketsDisableV7ForTheProcess()
        {
            using (var rig = new Rig())
            {
                rig.Http.Override = call => call.Path == "/v2/events/packet" ? ScriptedHttp.Error(400, "invalid_packet", "bad") : null;
                for (var i = 0; i < 3; i++) Assert.Equal(V7ResultKind.Fallback, rig.Send().Kind);
                Assert.True(rig.Session.Disabled);
                var packets = rig.Http.Count("POST", "/v2/events/packet");
                Assert.Equal(V7ResultKind.Fallback, rig.Send().Kind);
                Assert.Equal(packets, rig.Http.Count("POST", "/v2/events/packet"));
            }
        }

        private sealed class MissingNative : IM7Compressor
        {
            public byte[] Compress(byte[] source, int length) => throw new DllNotFoundException("daliys_zstd");
            public void Dispose() { }
        }

        [Fact]
        public void AMissingNativeLibraryDisablesV7InsteadOfFailingDelivery()
        {
            using (var rig = new Rig(compressor: d => new MissingNative()))
            {
                var result = rig.Send();
                Assert.Equal(V7ResultKind.Fallback, result.Kind);
                Assert.True(rig.Session.Disabled);
                Assert.Contains("native zstd", result.Detail);
                Assert.Equal(100, rig.Queue.Pending);
            }
        }

        [Fact]
        public void AnEventShapeTheCatalogDoesNotKnowIsSentThroughV1()
        {
            using (var rig = new Rig())
            {
                rig.Queue.Enqueue(rig.Batch.Replace("\"coins\"", "\"coinz\""));      // rows 101..200 carry an unknown property
                rig.Http.Ack = () => 100;
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);              // the first 100 are fine
                var result = rig.Send();                                             // the next batch has an unknown shape
                Assert.Equal(V7ResultKind.Fallback, result.Kind);
                Assert.Contains("unknown shape", result.Detail);
                Assert.Equal(100, rig.Queue.Pending);
            }
        }

        [Fact]
        public void ACredentialResetStartsOverWithANewStreamAndAliasTable()
        {
            using (var rig = new Rig())
            {
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                var oldInstall = rig.Queue.InstallId;
                rig.Queue.Enqueue(rig.Batch);
                rig.Queue.ResetIdentity();
                Assert.NotEqual(oldInstall, rig.Queue.InstallId);
                Assert.Equal(0, rig.Queue.StreamEpoch);
                rig.Http.Calls.Clear();
                rig.Http.Ack = () => 200;
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                var sync = (Dictionary<string, object>)MiniJson.Parse(rig.Http.Calls[0].Body);
                Assert.Equal(rig.Queue.InstallId, (string)sync["install_id"]);
                Assert.Equal("0", ((JsonNumber)sync["epoch"]).Lexeme);
                var alias = (Dictionary<string, object>)MiniJson.Parse(rig.Http.Where("PUT", "/v2/streams/aliases").First().Body);
                Assert.Equal("0", ((JsonNumber)alias["start"]).Lexeme);
                Assert.Equal(rig.Queue.InstallId, (string)((List<object>)((List<object>)alias["records"])[0])[0]);   // origin is the new installation
            }
        }

        [Fact]
        public void AnEmptyQueueIsReportedAsEmpty()
        {
            using (var rig = new Rig())
            {
                rig.Queue.DeleteThroughSequence(1000);
                Assert.Equal(V7ResultKind.Empty, rig.Send().Kind);
            }
        }

        [Fact]
        public void AMalformedServerAnswerIsAnErrorNotACorruptedQueue()
        {
            using (var rig = new Rig())
            {
                rig.Http.Override = call => call.Path == "/v2/events/packet" ? ScriptedHttp.Json(200, "{\"ack_through\":\"x\"}") : null;
                Assert.ThrowsAny<Exception>(() => rig.Send());
                Assert.Equal(100, rig.Queue.Pending);
            }
        }
    }
}
