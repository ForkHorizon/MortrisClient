// EditMode tests of the browser (WebGL) pipeline: queue, uploads, failure rules, page hide, reloads and two tabs.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using Daliys.Analytics.Internal.Session;
using Daliys.Analytics.Internal.Transport;
using Daliys.Analytics.Internal.Web;
using NUnit.Framework;

namespace Daliys.Analytics.Internal
{
    /// <summary>The browser (WebGL) pipeline with an in-memory localStorage, a scripted server and a hand-moved clock.</summary>
    public sealed class WebPipelineTests
    {
        private const string Policy = "\"client_policy\":{\"mode\":\"active\",\"next_check_seconds\":3600,\"discard_pending\":false}";
        private const string Registered = "{\"server_time\":\"2026-11-19T12:00:00.000Z\",\"installation_status\":\"registered\"," + Policy + "}";

        private sealed class MemoryStorage : IWebStorage
        {
            internal readonly Dictionary<string, string> Items = new Dictionary<string, string>();
            internal int Quota = int.MaxValue;
            public string Get(string key) => Items.TryGetValue(key, out var v) ? v : "";
            public bool Set(string key, string value)
            {
                var others = Items.Where(p => p.Key != key).Sum(p => p.Value.Length);
                if (others + (value?.Length ?? 0) > Quota) return false;
                if (string.IsNullOrEmpty(value)) Items.Remove(key); else Items[key] = value;
                return true;
            }
        }

        private sealed class Request
        {
            internal string Url, Body, Bearer;
            internal byte[] Bytes;
            internal bool Gzip;
            internal Action<int, string, string> Done;
            internal bool Keepalive;
            internal List<string> EventIds => Regex.Matches(Body, "\"event_id\":\"([0-9a-f-]{36})\"").Cast<Match>().Select(m => m.Groups[1].Value).ToList();
        }

        /// <summary>Answers each request when the test says so; the default answer acknowledges every event as accepted.</summary>
        private sealed class ScriptedServer : IWebHttp
        {
            internal readonly List<Request> Requests = new List<Request>();
            internal Request Pending => Requests.LastOrDefault(r => r.Done != null && !r.Keepalive);
            internal bool KeepaliveAccepted = true;

            public void Post(string url, byte[] body, bool gzip, string bearer, Action<int, string, string> done) =>
                Requests.Add(new Request { Url = url, Bytes = body, Gzip = gzip, Body = Text(body, gzip), Bearer = bearer, Done = done });

            public bool PostKeepalive(string url, byte[] body, bool gzip, string bearer)
            {
                Requests.Add(new Request { Url = url, Bytes = body, Gzip = gzip, Body = Text(body, gzip), Bearer = bearer, Keepalive = true });
                return KeepaliveAccepted;
            }

            private static string Text(byte[] body, bool gzip)
            {
                if (!gzip) return System.Text.Encoding.UTF8.GetString(body);
                using (var input = new System.IO.Compression.GZipStream(new System.IO.MemoryStream(body), System.IO.Compression.CompressionMode.Decompress))
                using (var reader = new System.IO.StreamReader(input)) return reader.ReadToEnd();
            }

            internal void Answer(int status, string body, string retryAfter = null)
            {
                var request = Pending ?? throw new InvalidOperationException("no request in flight");
                var done = request.Done; request.Done = null;
                done(status, body, retryAfter);
            }

            internal void AcceptAll()
            {
                var ids = string.Join(",", Pending.EventIds.Select(id => "\"" + id + "\""));
                Answer(200, "{\"server_time\":\"2026-11-19T12:00:00.000Z\",\"accepted\":[" + ids + "],\"duplicates\":[],\"rejected\":[]," + Policy + "}");
            }
        }

        private MemoryStorage _storage;
        private ScriptedServer _server;
        private long _now;
        private readonly List<ServerPolicy> _policies = new List<ServerPolicy>();

        [SetUp]
        public void SetUp()
        {
            _storage = new MemoryStorage();
            _server = new ScriptedServer();
            _now = 1_763_553_600_000;
            _policies.Clear();
        }

        private static AnalyticsOptions Options() => new AnalyticsOptions
        {
            ServerUrl = "https://collector.example/", ProjectId = "puzzle", Environment = "production",
            UploadInterval = TimeSpan.FromSeconds(120), UploadEventThreshold = 200,
        };

        private static AnalyticsDeviceContext Device() => new AnalyticsDeviceContext("1.0", "100", "webglplayer", "Chrome 131", "desktop", "en-US", 60);

        private WebPipeline Pipeline(AnalyticsOptions options = null) =>
            new WebPipeline(options ?? Options(), Device(), _storage, _server, () => _now, _policies.Add);

        private static byte[] Record(WebPipeline pipeline, string name, Dictionary<string, object> properties = null, Guid? session = null)
        {
            var writer = new EventRecordWriter();
            writer.Begin(new EventHeader(Guid.NewGuid(), session ?? Guid.NewGuid(), 1_763_553_600_123, 5, pipeline.ContextBytes), name, properties?.Count ?? 0);
            if (properties != null) foreach (var p in properties) writer.AddClr(p.Key, p.Value);
            var length = writer.Finish();
            var record = new byte[length];
            Buffer.BlockCopy(writer.Buffer, 0, record, 0, length);
            return record;
        }

        private static void Track(WebPipeline pipeline, int count)
        {
            for (var i = 0; i < count; i++)
            {
                var record = Record(pipeline, "level_start", new Dictionary<string, object> { ["level"] = i, ["name"] = "ü\"\n" });
                Assert.That(pipeline.TryEnqueue(record, record.Length), Is.True);
            }
        }

        private void Advance(TimeSpan by) => _now += (long)by.TotalMilliseconds;

        [Test]
        public void EventsBecomeV1JsonWithIncreasingSequences()
        {
            var pipeline = Pipeline();
            Track(pipeline, 3);
            var events = pipeline.Queue.Oldest(10, int.MaxValue);
            Assert.That(events.Count, Is.EqualTo(3));
            for (var i = 0; i < 3; i++)
            {
                var json = MiniJson.ParseObject(events[i]);
                Assert.That(json["name"], Is.EqualTo("level_start"));
                Assert.That(((JsonNumber)json["sequence"]).Lexeme, Is.EqualTo(i.ToString()));
                Assert.That(json["platform"], Is.EqualTo("webglplayer"));
                Assert.That(((Dictionary<string, object>)json["properties"])["name"], Is.EqualTo("ü\"\n"));
                Assert.That(events[i], Does.Not.Contain("\n"), "one event per stored line");
            }
        }

        [Test]
        public void RegistersAtOnceButBatchesWaitForTheIntervalOrThreshold()
        {
            var pipeline = Pipeline();
            Track(pipeline, 5);
            pipeline.Tick();
            Assert.That(_server.Pending.Url, Does.EndWith("/v1/installs/register"), "a short first visit must still be able to send on page hide");
            _server.Answer(200, Registered);
            Advance(TimeSpan.FromSeconds(119));
            pipeline.Tick();
            Assert.That(_server.Requests.Count, Is.EqualTo(1), "no batch before the interval");
            pipeline.RequestBackgroundUpload();
            Assert.That(_server.Requests.Last().Keepalive, Is.True);
        }

        [Test]
        public void ALaterPageDoesNotRegisterAgain()
        {
            var first = Pipeline();
            first.Tick(); _server.Answer(200, Registered);
            first.PersistNow();
            _server.Requests.Clear();

            var second = Pipeline();
            Track(second, 3);
            second.RequestBackgroundUpload();
            Assert.That(_server.Requests.Single().Keepalive, Is.True, "the keepalive works before any request of this page");
            Advance(TimeSpan.FromSeconds(121));
            second.Tick();
            Assert.That(_server.Pending.Url, Does.EndWith("/v1/client/policy"), "policy, not registration");
        }

        [Test]
        public void RegistersThenSendsAPlainJsonBatchAndForgetsAcknowledgedEvents()
        {
            var pipeline = Pipeline();
            Track(pipeline, 5);
            Advance(TimeSpan.FromSeconds(121));

            pipeline.Tick();
            Assert.That(_server.Pending.Url, Is.EqualTo("https://collector.example/v1/installs/register"));
            var register = MiniJson.ParseObject(_server.Pending.Body);
            Assert.That(register["install_id"], Is.EqualTo(pipeline.Queue.InstallationId));
            Assert.That(((string)register["installation_credential"]).Length, Is.EqualTo(43));
            Assert.That(Regex.IsMatch((string)register["install_id"], "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"), Is.True);
            pipeline.Tick();
            Assert.That(_server.Requests.Count, Is.EqualTo(1), "one request at a time");
            _server.Answer(200, Registered);
            Assert.That(pipeline.Registered && pipeline.Queue.Registered, Is.True);

            pipeline.Tick();
            Assert.That(_server.Pending.Url, Is.EqualTo("https://collector.example/v1/events/batch"));
            Assert.That(_server.Pending.Bearer, Is.EqualTo(pipeline.Queue.Credential));
            Assert.That(_server.Pending.Gzip, Is.True, "the V1 batch endpoint takes gzip only");
            var batch = MiniJson.ParseObject(_server.Pending.Body);
            Assert.That(((List<object>)batch["events"]).Count, Is.EqualTo(5));
            Assert.That(batch["sent_at_client"], Does.Match(@"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"));
            _server.AcceptAll();

            Assert.That(pipeline.Queue.Count, Is.Zero);
            pipeline.Tick();
            Assert.That(_server.Requests.Count, Is.EqualTo(2), "the round is over until the next interval");
        }

        [Test]
        public void AnOmittedEventStaysQueued()
        {
            var pipeline = Pipeline();
            Track(pipeline, 2);
            Advance(TimeSpan.FromSeconds(121));
            pipeline.Tick(); _server.Answer(200, Registered);
            pipeline.Tick();
            var ids = _server.Pending.EventIds;
            _server.Answer(200, "{\"server_time\":\"2026-11-19T12:00:00.000Z\",\"accepted\":[\"" + ids[0] + "\"],\"duplicates\":[],\"rejected\":[]," + Policy + "}");
            Assert.That(pipeline.Queue.Count, Is.EqualTo(1));
            Assert.That(WebEventQueue.IdOf(pipeline.Queue.Oldest(1, int.MaxValue)[0]), Is.EqualTo(ids[1]));
        }

        [Test]
        public void TheThresholdStartsAnUploadAndFullBatchesFollowEachOther()
        {
            var options = Options(); options.UploadEventThreshold = 150;
            var pipeline = Pipeline(options);
            Track(pipeline, 250);
            pipeline.Tick(); _server.Answer(200, Registered);
            pipeline.Tick();
            Assert.That(_server.Pending.EventIds.Count, Is.EqualTo(100), "V1 takes at most 100 events per request");
            _server.AcceptAll();
            pipeline.Tick();
            Assert.That(_server.Pending.EventIds.Count, Is.EqualTo(100));
            _server.AcceptAll();
            pipeline.Tick();
            Assert.That(_server.Pending, Is.Null, "50 left: under the threshold, they wait for the interval");
            Assert.That(pipeline.Queue.Count, Is.EqualTo(50));
        }

        [Test]
        public void NetworkFailureBacksOffAndRetryAfterIsHonoured()
        {
            var pipeline = Pipeline();
            Track(pipeline, 3);
            pipeline.Tick();
            _server.Answer(0, "");                       // offline or CORS refused
            pipeline.Tick();
            Assert.That(_server.Requests.Count, Is.EqualTo(1), "no retry in the same instant");
            Advance(TimeSpan.FromSeconds(6));           // the first back-off step is 2.5-5 s
            pipeline.Tick();
            Assert.That(_server.Requests.Count, Is.EqualTo(2));
            _server.Answer(429, "{\"code\":\"rate_limited\"}", "120");
            Advance(TimeSpan.FromSeconds(119));
            pipeline.Tick();
            Assert.That(_server.Requests.Count, Is.EqualTo(2), "Retry-After: 120 is never cut short");
            Advance(TimeSpan.FromSeconds(15));
            pipeline.Tick();
            Assert.That(_server.Requests.Count, Is.EqualTo(3));
            Assert.That(pipeline.Queue.Count, Is.EqualTo(3), "nothing was lost");
        }

        [Test]
        public void AMalformedSuccessIsRetriedNotTrusted()
        {
            var pipeline = Pipeline();
            Track(pipeline, 2);
            Advance(TimeSpan.FromSeconds(121));
            pipeline.Tick(); _server.Answer(200, Registered);
            pipeline.Tick(); _server.Answer(200, "{\"truncated\":");
            Assert.That(pipeline.Queue.Count, Is.EqualTo(2));
            Assert.That(pipeline.Blocked, Is.False);
        }

        [Test]
        public void AnUnauthorizedBatchRegistersAgainOnce()
        {
            var pipeline = Pipeline();
            Track(pipeline, 2);
            Advance(TimeSpan.FromSeconds(121));
            pipeline.Tick(); _server.Answer(200, Registered);
            pipeline.Tick(); _server.Answer(401, "{\"code\":\"unauthorized\"}");
            pipeline.Tick();
            Assert.That(_server.Pending.Url, Does.EndWith("/v1/installs/register"));
            _server.Answer(200, Registered);
            pipeline.Tick();
            Assert.That(_server.Pending.Url, Does.EndWith("/v1/events/batch"));
            _server.AcceptAll();
            Assert.That(pipeline.Queue.Count, Is.Zero);
        }

        [Test]
        public void AnInvalidCredentialGetsAFreshIdentityOnce()
        {
            var pipeline = Pipeline();
            Track(pipeline, 1);
            var firstId = pipeline.Queue.InstallationId;
            Advance(TimeSpan.FromSeconds(121));
            pipeline.Tick(); _server.Answer(400, "{\"code\":\"invalid_credential\"}");
            Assert.That(pipeline.Queue.InstallationId, Is.Not.EqualTo(firstId));
            pipeline.Tick(); _server.Answer(400, "{\"code\":\"invalid_credential\"}");
            Assert.That(pipeline.Blocked, Is.True, "a second refusal must not loop");
            Assert.That(pipeline.Queue.Count, Is.EqualTo(1), "the queue is kept");
        }

        [Test]
        public void TooLargeHalvesTheBatchAndDropsASingleUnsendableEvent()
        {
            var options = Options(); options.UploadEventThreshold = 4;
            var pipeline = Pipeline(options);
            Track(pipeline, 4);
            pipeline.Tick(); _server.Answer(200, Registered);
            pipeline.Tick(); Assert.That(_server.Pending.EventIds.Count, Is.EqualTo(4)); _server.Answer(413, "{\"code\":\"payload_too_large\"}");
            pipeline.Tick(); Assert.That(_server.Pending.EventIds.Count, Is.EqualTo(2)); _server.Answer(413, "{\"code\":\"payload_too_large\"}");
            pipeline.Tick(); Assert.That(_server.Pending.EventIds.Count, Is.EqualTo(1)); _server.Answer(413, "{\"code\":\"payload_too_large\"}");
            Assert.That(pipeline.Queue.Count, Is.EqualTo(3));
        }

        [Test]
        public void ConflictStopsUploadingAndKeepsTheQueue()
        {
            var pipeline = Pipeline();
            Track(pipeline, 2);
            Advance(TimeSpan.FromSeconds(121));
            pipeline.Tick(); _server.Answer(409, "{\"code\":\"install_conflict\"}");
            Advance(TimeSpan.FromHours(1));
            pipeline.Tick();
            Assert.That(_server.Requests.Count, Is.EqualTo(1));
            Assert.That(pipeline.Queue.Count, Is.EqualTo(2));
        }

        [Test]
        public void PausedPolicyStopsBatchesUntilTheNextCheck()
        {
            var pipeline = Pipeline();
            Track(pipeline, 2);
            Advance(TimeSpan.FromSeconds(121));
            pipeline.Tick();
            _server.Answer(200, "{\"server_time\":\"2026-11-19T12:00:00.000Z\",\"installation_status\":\"registered\",\"client_policy\":{\"mode\":\"pause_upload\",\"next_check_seconds\":600,\"discard_pending\":false}}");
            Assert.That(_policies.Last().Mode, Is.EqualTo(ServerPolicyMode.PauseUpload));
            Advance(TimeSpan.FromSeconds(121));
            pipeline.Tick();
            Assert.That(_server.Requests.Count, Is.EqualTo(1), "paused: no batch");
            Advance(TimeSpan.FromSeconds(600));
            pipeline.Tick();
            Assert.That(_server.Pending.Url, Does.EndWith("/v1/client/policy"));
        }

        [Test]
        public void FlushUploadsEverythingAtOnceAndReportsIt()
        {
            var pipeline = Pipeline();
            Track(pipeline, 3);
            var flush = pipeline.FlushAsync(default);
            pipeline.Tick(); _server.Answer(200, Registered);
            pipeline.Tick(); _server.AcceptAll();
            Assert.That(flush.IsCompleted, Is.False);
            pipeline.Tick();
            Assert.That(flush.IsCompleted, Is.True);
            Assert.That(flush.Result.Status, Is.EqualTo(FlushStatus.Uploaded));
        }

        [Test]
        public void HiddenPageSendsAKeepaliveUnder64KiBOnlyOnceRegistered()
        {
            var pipeline = Pipeline();
            Track(pipeline, 300);
            pipeline.RequestBackgroundUpload();
            Assert.That(_server.Requests.Where(r => r.Keepalive), Is.Empty, "an installation the server never registered would only get a 401");

            pipeline.Tick(); _server.Answer(200, Registered);
            pipeline.RequestBackgroundUpload();
            var keepalive = _server.Requests.Single(r => r.Keepalive);
            Assert.That(keepalive.Url, Is.EqualTo("https://collector.example/v1/events/batch"));
            Assert.That(keepalive.Gzip, Is.True);
            Assert.That(keepalive.Bytes.Length, Is.LessThanOrEqualTo(WebPipeline.KeepaliveByteLimit));
            Assert.That(keepalive.EventIds.Count, Is.InRange(1, 100));
            Assert.That(pipeline.Queue.Count, Is.EqualTo(300), "kept until a regular upload is acknowledged");

            pipeline.RequestBackgroundUpload();
            Assert.That(_server.Requests.Count(r => r.Keepalive), Is.EqualTo(1), "quick tab switching does not send a string of requests");
        }

        [Test]
        public void TheQueueSurvivesAReloadWithItsIdentityAndSequence()
        {
            var first = Pipeline();
            Track(first, 3);
            Assert.That(first.PersistNow(), Is.True);
            var id = first.Queue.InstallationId;

            var second = Pipeline();
            Assert.That(second.Queue.Count, Is.EqualTo(3));
            Assert.That(second.Queue.InstallationId, Is.EqualTo(id));
            Track(second, 1);
            Assert.That(((JsonNumber)MiniJson.ParseObject(second.Queue.Oldest(4, int.MaxValue)[3])["sequence"]).Lexeme, Is.EqualTo("3"));
        }

        [Test]
        public void ProjectsOnOneOriginDoNotShareAQueue()
        {
            var first = Pipeline();
            Track(first, 2);
            first.PersistNow();
            var other = Options(); other.ProjectId = "another-game";
            Assert.That(Pipeline(other).Queue.Count, Is.Zero);
            Assert.That(Pipeline().Queue.Count, Is.EqualTo(2));
        }

        [Test]
        public void AFullQueueDropsTheOldestAndCountsThem()
        {
            var options = Options(); options.DurableEventLimit = 10;
            var pipeline = Pipeline(options);
            Track(pipeline, 15);
            Assert.That(pipeline.Queue.Count, Is.EqualTo(10));
            Assert.That(pipeline.QueueEvicted, Is.EqualTo(5));
            Assert.That(((JsonNumber)MiniJson.ParseObject(pipeline.Queue.Oldest(1, int.MaxValue)[0])["sequence"]).Lexeme, Is.EqualTo("5"));
        }

        [Test]
        public void AStorageQuotaStoresWhatFitsAndKeepsEverythingInMemory()
        {
            var pipeline = Pipeline();
            Track(pipeline, 40);
            Assert.That(pipeline.Queue.Chars, Is.GreaterThan(12 * 1024), "the test needs a queue bigger than the quota");
            _storage.Quota = 8 * 1024;
            Assert.That(pipeline.PersistNow(), Is.False, "the stored copy is short");
            Assert.That(pipeline.Queue.Count, Is.EqualTo(40), "memory is never trimmed to make a write fit");
            Assert.That(pipeline.QueueEvicted, Is.Zero);
            var reloaded = Pipeline().Queue.Count;
            Assert.That(reloaded, Is.InRange(1, 39), "the oldest part that fits was stored");
        }

        [Test, Timeout(5000)]
        public void StorageThatRefusesEverythingNeitherHangsNorLosesEvents()
        {
            var pipeline = Pipeline();
            Track(pipeline, 3);
            _storage.Quota = 0;
            Assert.That(pipeline.PersistNow(), Is.False);
            Assert.That(pipeline.Queue.Count, Is.EqualTo(3));
            pipeline.Tick(); _server.Answer(200, Registered);
            Advance(TimeSpan.FromSeconds(121));
            pipeline.Tick(); _server.AcceptAll();
            Assert.That(pipeline.Queue.Count, Is.Zero, "uploads go on from memory");
        }

        [Test]
        public void AnEventIdAlreadyQueuedIsIgnored()
        {
            var pipeline = Pipeline();
            var record = Record(pipeline, "sys_session_end");
            Assert.That(pipeline.TryEnqueue(record, record.Length), Is.True);
            Assert.That(pipeline.TryEnqueue(record, record.Length), Is.False);
            Assert.That(pipeline.Queue.Count, Is.EqualTo(1), "a batch with one id twice would be refused as a whole");
        }

        [Test]
        public void AnAcknowledgementThatSettlesNothingBacksOff()
        {
            var options = Options(); options.UploadEventThreshold = 1;
            var pipeline = Pipeline(options);
            Track(pipeline, 120);
            pipeline.Tick(); _server.Answer(200, Registered);
            pipeline.Tick();
            _server.Answer(200, "{\"server_time\":\"2026-11-19T12:00:00.000Z\",\"accepted\":[],\"duplicates\":[],\"rejected\":[]," + Policy + "}");
            pipeline.Tick();
            Assert.That(_server.Requests.Count, Is.EqualTo(2), "no resend in the same instant");
        }

        private sealed class ThrowingHttp : IWebHttp
        {
            public void Post(string url, byte[] body, bool gzip, string bearer, Action<int, string, string> done) => throw new UriFormatException("bad url");
            public bool PostKeepalive(string url, byte[] body, bool gzip, string bearer) => false;
        }

        [Test]
        public void ARequestThatCannotStartDoesNotWedgeThePipeline()
        {
            var pipeline = new WebPipeline(Options(), Device(), _storage, new ThrowingHttp(), () => _now, _policies.Add);
            Track(pipeline, 1);
            var flush = pipeline.FlushAsync(default);
            pipeline.Tick();
            Assert.That(pipeline.InFlight, Is.False);
            Assert.That(flush.IsCompleted, Is.True);
            Assert.That(flush.Result.Status, Is.EqualTo(FlushStatus.UploadDeferred));
        }

        [Test]
        public void TwoTabsOfOneGameDoNotOverwriteEachOther()
        {
            var tabA = Pipeline();
            var tabB = Pipeline();
            Track(tabA, 2);
            Track(tabB, 3);
            tabA.PersistNow();
            tabB.PersistNow();   // B's save must take in A's events, not replace them
            tabA.PersistNow();
            Assert.That(Pipeline().Queue.Count, Is.EqualTo(5));

            // what one tab got acknowledged does not come back from the other tab's stored copy
            tabB.Tick(); _server.Answer(200, Registered);
            tabB.FlushAsync(default);
            tabB.Tick(); _server.AcceptAll();
            tabB.PersistNow();
            Assert.That(Pipeline().Queue.Count, Is.Zero);
        }

        [Test]
        public void TwoTabsDoNotHandOutTheSameSequenceAfterASave()
        {
            var tabA = Pipeline();
            var tabB = Pipeline();
            Track(tabA, 5);
            tabA.PersistNow();
            Track(tabB, 1);
            tabB.PersistNow();
            Track(tabB, 1);
            Assert.That(tabB.Queue.InstallationId, Is.EqualTo(tabA.Queue.InstallationId), "a first-visit tab adopts the identity the other tab stored");
            var last = tabB.Queue.Oldest(100, int.MaxValue).Last();
            Assert.That(((JsonNumber)MiniJson.ParseObject(last)["sequence"]).Lexeme, Is.EqualTo("5"), "B continues after A's numbers once it saw them");
        }

        [Test]
        public void ADamagedStoreStartsFreshInsteadOfThrowing()
        {
            _storage.Items["mortris:puzzle:production:id"] = "garbage";
            _storage.Items["mortris:puzzle:production:q"] = "not json\n{\"event_id\":\"x\"}";
            var pipeline = Pipeline();
            Assert.That(pipeline.Queue.Count, Is.Zero);
            Assert.That(Guid.TryParse(pipeline.Queue.InstallationId, out _), Is.True);
        }

        [Test]
        public void CountersSurviveAReload()
        {
            var first = Pipeline();
            Assert.That(first.NextId("attempt"), Is.EqualTo(1));
            Assert.That(first.NextId("attempt"), Is.EqualTo(2));
            first.PersistNow();
            Assert.That(Pipeline().NextId("attempt"), Is.EqualTo(3));
        }

        [Test]
        public void AClosedTabsSessionIsEndedOnTheNextPage()
        {
            var sink = new List<string>();
            var first = Pipeline();
            var tracker = new SessionTracker(() => _now, TimeSpan.FromMinutes(5), new Sink(sink));
            first.AttachSession(tracker);
            tracker.Start();
            Advance(TimeSpan.FromSeconds(30));
            tracker.OnPause(true);       // the tab was hidden, then closed
            first.PersistNow();

            sink.Clear();
            var second = Pipeline();
            second.AttachSession(new SessionTracker(() => _now, TimeSpan.FromMinutes(5), new Sink(sink)));
            Assert.That(sink, Is.EqualTo(new[] { "sys_session_end:background_killed" }));
        }

        private sealed class Sink : ISessionEventSink
        {
            private readonly List<string> _names;
            internal Sink(List<string> names) { _names = names; }
            public void Emit(string name, Guid sessionId, long occurredAtUnixMs, long sessionElapsedMs, IReadOnlyDictionary<string, object> properties) =>
                _names.Add(properties != null && properties.TryGetValue("reason", out var reason) && name == "sys_session_end" ? name + ":" + reason : name);
        }

        [Test]
        public void ARuntimeOnTheWebPipelineTracksAndBatchesOnTheCallingThread()
        {
            WebPipeline pipeline = null;
            var runtime = new AnalyticsRuntime(Options(), policy => pipeline = new WebPipeline(Options(), Device(), _storage, _server, () => _now, policy));
            try
            {
                Assert.That(runtime.Track("level_start", new Dictionary<string, object> { ["level"] = 1 }), Is.EqualTo(TrackResult.AcceptedToHandoff));
                var batch = runtime.TrackBatchAsync(new[] { new BatchEvent("level_end"), new BatchEvent("level_end") }, default);
                Assert.That(batch.IsCompleted, Is.True, "no pool thread in a WebGL player");
                Assert.That(batch.Result.Accepted, Is.EqualTo(2));
                var names = pipeline.Queue.Oldest(10, int.MaxValue).Select(e => (string)MiniJson.ParseObject(e)["name"]).ToList();
                Assert.That(names, Is.EqualTo(new[] { "sys_session_start", "level_start", "level_end", "level_end" }));

                runtime.OnApplicationPause(true);
                Assert.That(_storage.Items.Keys, Does.Contain("mortris:puzzle:production:q"));
                Assert.That(_storage.Items["mortris:puzzle:production:s"], Does.Not.Contain("\"bg\":0,"), "the saved session knows the player left");
            }
            finally { runtime.Dispose(); }
        }
    }
}
