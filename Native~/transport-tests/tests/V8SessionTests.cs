using System;
using System.Collections.Generic;
using System.Linq;
using Daliys.Analytics.Internal.Transport;
using Xunit;

namespace M7Transport.Tests
{
    public class V8SessionTests
    {
        private static readonly byte[] Context = EventContext.Build("1.1.14", "214", "android", "Android 15", "Pixel 8", "en-US", 60);
        private static readonly Guid Session = Guid.Parse("7b1f3c52-9a44-4e0e-8d61-2f5c0a9e1b77");

        private sealed class NoCompressor : IM7Compressor { public byte[] Compress(byte[] s, int n) => null; public void Dispose() { } }

        internal sealed class Rig : IDisposable
        {
            internal readonly FakeQueue Queue = new FakeQueue();
            internal readonly FakeV8Server Server = new FakeV8Server("p");
            internal V8Session V8;
            internal DateTimeOffset Now = new DateTimeOffset(2026, 10, 26, 12, 0, 0, TimeSpan.Zero);
            private int _random;

            internal Rig() { NewProcess(); }

            internal V8Settings Settings() => new V8Settings
            {
                ProjectId = "p", SdkName = "mortris-unity", SdkVersion = "0.2.0", AppVersion = "1.1.14", BuildNumber = "214", Platform = "android",
                Clock = () => Now, CompressorFactory = d => new NoCompressor(), RandomBytes = () => { var b = new byte[16]; b[0] = (byte)(++_random); return b; },
            };

            /// <summary>A new process of the app: a new session object over the same durable queue.</summary>
            internal void NewProcess() { V8?.Dispose(); V8 = new V8Session(Settings(), Server, new MemoryV7AssetStore()); }

            internal void Enqueue(int count, Func<int, (string name, Dictionary<string, object> props)> make = null, int limit = 1000000)
            {
                var writer = new EventRecordWriter { TypedNumbers = true };
                var frames = new List<byte>();
                var start = (int)Server.StoredSequences.Count + Queue.Pending;
                for (var i = 0; i < count; i++)
                {
                    var (name, props) = make != null ? make(i) : ("tick", new Dictionary<string, object> { ["n"] = (long)i, ["x"] = 0.5f * i });
                    writer.Begin(Guid.NewGuid(), Session, 1790000000000 + (start + i) * 40, 10 + (start + i) * 40, Context, name, props.Count);
                    foreach (var p in props) writer.AddClr(p.Key, p.Value);
                    var length = writer.Finish();
                    frames.AddRange(new[] { (byte)(length >> 24), (byte)(length >> 16), (byte)(length >> 8), (byte)length });
                    frames.AddRange(writer.Buffer.Take(length));
                }
                Queue.EnqueueRecords(frames.ToArray(), count, limit, 1L << 40, 1L << 40);
            }

            internal V7SendResult Send(int batch = 100) => V8.Send(Queue, () => Queue.ReadOldest(batch));
            internal int Calls(string path) => Server.Calls.Count(c => c.Path == path);
            public void Dispose() => V8.Dispose();
        }

        [Fact]
        public void TheFirstSendRegistersAndDeliversInOneConversation()
        {
            using (var rig = new Rig())
            {
                rig.Enqueue(30);
                var result = rig.Send();
                Assert.Equal(V7ResultKind.Delivered, result.Kind);
                Assert.Equal(30, result.Removed);
                Assert.Equal(0, rig.Queue.Pending);
                Assert.Equal(1, rig.Calls("/v3/hello"));
                Assert.Equal(1, rig.Calls("/v3/packet"));
                Assert.Equal(1, rig.Calls("/v3/policy"));        // the policy is fetched once, then only when its version changes
                Assert.Equal(0, rig.Calls("/v2/streams/sync"));
                Assert.StartsWith("1.", rig.V8.Token);
                Assert.Equal(1, rig.V8.Epoch);
                Assert.Equal(Enumerable.Range(1, 30).Select(i => (long)i), rig.Server.StoredSequences);
                Assert.Equal("active", result.PolicyMode);
                var hello = rig.Server.Calls.First(c => c.Path == "/v3/hello");
                Assert.Null(hello.Credential);                      // the first call carries no token, only the nonce
                Assert.Contains("\"nonce\":", hello.Body);
                Assert.Contains("\"sdk\":\"mortris-unity/0.2.0\"", hello.Body);
            }
        }

        [Fact]
        public void ANormalLaunchSendsItsFirstPacketWithoutSayingHello()
        {
            using (var rig = new Rig())
            {
                rig.Enqueue(20);
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                rig.NewProcess();
                rig.Server.Calls.Clear();
                rig.Enqueue(15);
                var result = rig.Send();
                Assert.Equal(V7ResultKind.Delivered, result.Kind);
                Assert.Equal(0, rig.Calls("/v3/hello"));
                Assert.Equal(0, rig.Calls("/v3/policy"));
                Assert.Equal(1, rig.Calls("/v3/packet"));
                Assert.Equal(35, rig.Server.StoredSequences.Count);
                Assert.Equal(0, rig.Server.ShapeSectionSizes.Last());       // the shape table came back from durable storage
                Assert.Equal(1, rig.Server.AliasSectionSizes.Last());       // this process's session is a new alias record
            }
        }

        [Fact]
        public void ANewEventShapeIsRegisteredByThePacketThatFirstUsesIt()
        {
            using (var rig = new Rig())
            {
                rig.Enqueue(10);
                rig.Send();
                var before = rig.Server.ShapeSignatures.Count;
                rig.Enqueue(5, i => ("brand_new", new Dictionary<string, object> { ["level"] = (long)i, ["speed"] = 0f }));
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                Assert.Equal(before + 1, rig.Server.ShapeSignatures.Count);
                Assert.Equal(1, rig.Server.ShapeSectionSizes.Last());
                Assert.Contains("brand_new|level:0|speed:3", rig.Server.ShapeSignatures);   // speed 0f is a float32, not an int
            }
        }

        [Fact]
        public void ALostAcknowledgementIsResentAndStoredOnce()
        {
            using (var rig = new Rig())
            {
                rig.Enqueue(12);
                rig.Send();
                rig.Enqueue(8);
                var drop = true;
                rig.Server.Override = call =>
                {
                    if (call.Path != "/v3/packet" || !drop) return null;
                    drop = false;
                    var real = rig.Server.PostBinary("/v3/packet", call.Packet, "x", call.Credential);     // the server stores it...
                    rig.Server.Calls.RemoveAt(rig.Server.Calls.Count - 1);
                    return FakeV8Server.Json(503, "{}");                                                    // ...but the answer is lost
                };
                Assert.Equal(V7ResultKind.Retry, rig.Send().Kind);
                Assert.Equal(8, rig.Queue.Pending);
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                Assert.Equal(0, rig.Queue.Pending);
                Assert.Equal(20, rig.Server.StoredSequences.Distinct().Count());
            }
        }

        [Fact]
        public void ARefusedTokenIsReplacedByAHelloWithoutLosingTheStream()
        {
            using (var rig = new Rig())
            {
                rig.Enqueue(10);
                rig.Send();
                var epochBefore = rig.V8.Epoch;
                rig.Server.KeyVersion = "j";           // the key that issued the old token was retired: the server now issues "j" tokens
                rig.Enqueue(10);
                var result = rig.Send();
                Assert.Equal(V7ResultKind.Delivered, result.Kind);
                Assert.Equal(2, rig.Calls("/v3/hello"));
                Assert.Contains(".j", rig.V8.Token);
                Assert.Equal(epochBefore, rig.V8.Epoch);           // same installation (the nonce is known), same stream
                Assert.Equal(20, rig.Server.StoredSequences.Distinct().Count());
            }
        }

        [Fact]
        public void AServerThatForgotTheShapesIsToldAgain()
        {
            using (var rig = new Rig())
            {
                rig.Enqueue(10);
                rig.Send();
                rig.Server.ShapeSignatures.Clear(); rig.Server.ShapeJson.Clear();     // e.g. a restored database
                rig.Enqueue(10);
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                Assert.True(rig.Server.ShapeSignatures.Count >= 1);
                Assert.Equal(20, rig.Server.StoredSequences.Distinct().Count());
            }
        }

        [Fact]
        public void AnotherClientRegisteringADifferentShapeFirstMakesThisOneAdoptTheCatalog()
        {
            using (var rig = new Rig())
            {
                rig.Enqueue(5);
                rig.Send();                                                            // the shape table holds "tick" at 0
                rig.NewProcess();
                // somebody else got position 1 before we did
                rig.Server.ShapeSignatures.Add("rival|a:0"); rig.Server.ShapeJson.Add("[\"rival\",[[\"a\",0]]]");
                rig.Enqueue(5, i => ("mine", new Dictionary<string, object> { ["b"] = (long)i }));
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                Assert.Equal(1, rig.Calls("/v3/catalog"));
                Assert.Contains("mine|b:0", rig.Server.ShapeSignatures);
                Assert.Equal(2, rig.Server.ShapeSignatures.IndexOf("mine|b:0"));
            }
        }

        [Fact]
        public void AStreamTheServerDoesNotKnowOpensANewEpoch()
        {
            using (var rig = new Rig())
            {
                rig.Enqueue(10);
                rig.Send();
                rig.Server.Streams.Values.First().Clear();                              // the server lost the stream
                rig.Enqueue(10);
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                Assert.Equal(2, rig.Calls("/v3/hello"));
                Assert.Equal(20, rig.Server.StoredSequences.Distinct().Count());
            }
        }

        [Fact]
        public void ALostAliasTableMeansANewEpochNotAGap()
        {
            using (var rig = new Rig())
            {
                rig.Enqueue(10);
                rig.Send();
                rig.NewProcess();
                rig.Server.Streams.Values.First().Values.First().Aliases.Clear();      // the server holds fewer alias records than this process builds on
                rig.Enqueue(10);
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                Assert.Equal(20, rig.Server.StoredSequences.Distinct().Count());
            }
        }

        [Fact]
        public void AStrictProjectSendsEventsWithKnownShapesAndLeavesTheRestToV1()
        {
            using (var rig = new Rig())
            {
                rig.Enqueue(10);
                rig.Send();                                                  // registers "tick"
                rig.Server.Strict = true;
                rig.Enqueue(4, i => ("not_allowed", new Dictionary<string, object> { ["z"] = (long)i }));
                var refused = rig.Send();
                Assert.Equal(V7ResultKind.Fallback, refused.Kind);
                Assert.Contains("422", refused.Detail);
                Assert.Equal(1, rig.V8.ShapeCount);                      // the refused shape is not carried into later packets
                var v1 = rig.Queue.ReadOldest(4);
                rig.Queue.DeleteAcknowledged("[" + string.Join(",", Enumerable.Range(0, v1.Count).Select(i => "\"" + v1.EventId(i) + "\"")) + "]");     // V1 delivered them
                rig.Enqueue(6);
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
            }
        }

        [Fact]
        public void AServerWithoutKeysTurnsV8OffForAWhile()
        {
            using (var rig = new Rig())
            {
                rig.Server.Override = call => FakeV8Server.Error(503, "transport_unavailable");
                rig.Enqueue(5);
                Assert.Equal(V7ResultKind.Retry, rig.Send().Kind);          // hello: 503 is transient for a hello
                rig.Server.Override = call => call.Path == "/v3/hello" ? FakeV8Server.Error(404, "not_found") : null;
                var result = rig.Send();
                Assert.Equal(V7ResultKind.Fallback, result.Kind);
                rig.Server.Calls.Clear();
                Assert.Equal(V7ResultKind.Fallback, rig.Send().Kind);
                Assert.Empty(rig.Server.Calls);                              // no request while it is switched off
                rig.Now = rig.Now.AddHours(2);
                rig.Server.Override = null;
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
            }
        }

        [Fact]
        public void APacketTheServerCalls413OrTooBigIsReportedForHalving()
        {
            using (var rig = new Rig())
            {
                rig.Enqueue(40);
                rig.Send(10);
                rig.Server.MaxPacketRows = 5;
                var result = rig.Send(10);
                Assert.Equal(V7ResultKind.PayloadTooLarge, result.Kind);
                Assert.Equal(400, result.Status);
                rig.Server.Override = call => call.Path == "/v3/packet" ? FakeV8Server.Error(413, "payload_too_large") : null;
                Assert.Equal(V7ResultKind.PayloadTooLarge, rig.Send(10).Kind);
            }
        }

        [Fact]
        public void ADroppedRangeReachesTheServerAndIsAcknowledgedPast()
        {
            using (var rig = new Rig())
            {
                rig.Enqueue(30, null, limit: 20);                      // the queue evicted the oldest 10: they are dropped, never to be sent
                var result = rig.Send(30);
                Assert.Equal(V7ResultKind.Delivered, result.Kind);
                Assert.Equal(20, rig.Server.StoredSequences.Count);
                var stream = rig.Server.Streams.Values.First().Values.First();
                Assert.Equal(11, stream.Base);                          // a new stream starts at the lowest queued row: what lies below was dealt with before it existed
                Assert.Equal(30, FakeV8Server.Ack(stream));
                Assert.Equal(0, rig.Queue.Pending);
            }
        }

        [Fact]
        public void DroppedRangesAfterTheFirstSendTravelInsideThePacket()
        {
            using (var rig = new Rig())
            {
                rig.Enqueue(10);
                rig.Send();
                rig.Enqueue(30, null, limit: 20);                       // evicts 11..20 (and some of the new ones) after the stream is open
                var result = rig.Send(30);
                Assert.Equal(V7ResultKind.Delivered, result.Kind);
                var stream = rig.Server.Streams.Values.First().Values.First();
                Assert.NotEmpty(stream.Dropped);
                Assert.Equal(40, FakeV8Server.Ack(stream));
                Assert.Equal(0, rig.Calls("/v3/hello") - 1);
            }
        }

        [Fact]
        public void ThePolicyIsRefetchedOnlyWhenItsVersionChanges()
        {
            using (var rig = new Rig())
            {
                rig.Enqueue(5); rig.Send();
                rig.Enqueue(5); rig.Send();
                Assert.Equal(1, rig.Calls("/v3/policy"));
                rig.Server.PolicyVersion = 2000; rig.Server.PolicyMode = "pause_upload";
                rig.Enqueue(5);
                var result = rig.Send();
                Assert.Equal(2, rig.Calls("/v3/policy"));
                Assert.Equal("pause_upload", result.PolicyMode);
            }
        }

        [Fact]
        public void ADictionaryTrainedLaterIsAnnouncedInTheAcknowledgementAndFetchedOnce()
        {
            using (var rig = new Rig())
            {
                rig.Enqueue(10); rig.Send();
                var dictionary = System.Text.Encoding.ASCII.GetBytes(new string('d', 400));
                rig.Server.Dictionary = dictionary; rig.Server.DictionaryId = ScriptedHttp.Id(dictionary);
                rig.Enqueue(10);
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);          // this packet still names no dictionary; the answer announces one
                Assert.Equal(0, rig.Calls("/v3/assets/dictionary/" + rig.Server.DictionaryId));
                rig.Enqueue(10);
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);          // the encoder is rebuilt with it: one fetch
                Assert.Equal(1, rig.Calls("/v3/assets/dictionary/" + rig.Server.DictionaryId));
                rig.Enqueue(10);
                Assert.Equal(V7ResultKind.Delivered, rig.Send().Kind);
                Assert.Equal(1, rig.Calls("/v3/assets/dictionary/" + rig.Server.DictionaryId));       // cached
                Assert.Equal(40, rig.Server.StoredSequences.Distinct().Count());
            }
        }

        [Fact]
        public void AnAcknowledgementThatSettlesNothingEventuallyYieldsToV1()
        {
            using (var rig = new Rig())
            {
                rig.Enqueue(5);
                rig.Send();
                rig.Enqueue(5);
                rig.Server.Override = call => call.Path == "/v3/packet" ? FakeV8Server.Json(200, "{\"ack\":0,\"p\":1000}") : null;
                Assert.Equal(V7ResultKind.Retry, rig.Send().Kind);
                Assert.Equal(V7ResultKind.Retry, rig.Send().Kind);
                Assert.Equal(V7ResultKind.Fallback, rig.Send().Kind);
            }
        }
    }
}
