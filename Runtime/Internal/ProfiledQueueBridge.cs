// Queue bridge with every call timed; created only by the profiling build.
using Daliys.Analytics.Internal.Transport;

namespace Daliys.Analytics.Internal
{
    /// <summary>
    /// The queue bridge with every call timed (<see cref="AnalyticsProf"/>); only created by a build with the profiling define, so the shipped SDK talks to the Java queue directly.
    /// </summary>
    internal sealed class ProfiledQueueBridge : IAnalyticsQueueBridge
    {
        private readonly IAnalyticsQueueBridge _inner;

        internal ProfiledQueueBridge(IAnalyticsQueueBridge inner) { _inner = inner; }

        public int PendingCount => _inner.PendingCount;

        private static T Timed<T>(Stage stage, System.Func<T> call)
        {
            var t = AnalyticsProf.Begin();
            try { return call(); } finally { AnalyticsProf.End(stage, t); }
        }

        private static void Timed(Stage stage, System.Action call)
        {
            var t = AnalyticsProf.Begin();
            try { call(); } finally { AnalyticsProf.End(stage, t); }
        }

        public void EnqueueRecords(byte[] frames, int count, string counters = null) => Timed(Stage.JniEnqueue, () => _inner.EnqueueRecords(frames, count, counters));
        public void SetLimits(int eventLimit, long byteLimit, long maxAgeMilliseconds) => Timed(Stage.JniOther, () => _inner.SetLimits(eventLimit, byteLimit, maxAgeMilliseconds));
        public AnalyticsQueueState GetState() => Timed(Stage.JniGetState, () => _inner.GetState());
        public AnalyticsQueueState ResetIdentity() => Timed(Stage.JniOther, () => _inner.ResetIdentity());
        public QueueBatch ReadOldest(int maxEvents) => Timed(Stage.JniReadOldest, () => _inner.ReadOldest(maxEvents));
        public void SaveSessionState(string state) => Timed(Stage.JniSession, () => _inner.SaveSessionState(state));
        public string LoadSessionState() => Timed(Stage.JniSession, () => _inner.LoadSessionState());
        public string GetPreviousExitInfo() => Timed(Stage.JniOther, () => _inner.GetPreviousExitInfo());
        public int DeleteAcknowledged(string eventIdsJson) => Timed(Stage.JniDelete, () => _inner.DeleteAcknowledged(eventIdsJson));
        public void ClearAllPendingEvents() => Timed(Stage.JniOther, () => _inner.ClearAllPendingEvents());
        public string GetSequenceState() => Timed(Stage.JniSequenceState, () => _inner.GetSequenceState());
        public void SetStreamEpoch(long epoch) => Timed(Stage.JniOther, () => _inner.SetStreamEpoch(epoch));
        public int DeleteThroughSequence(long ackThrough) => Timed(Stage.JniDelete, () => _inner.DeleteThroughSequence(ackThrough));
        public void BeginNewStream() => Timed(Stage.JniOther, () => _inner.BeginNewStream());
        public string GetMeta(string key) => Timed(Stage.JniMeta, () => _inner.GetMeta(key));
        public void SetMeta(string key, string value) => Timed(Stage.JniMeta, () => _inner.SetMeta(key, value));
        public void AdoptIdentity(string installationId, string credential) => Timed(Stage.JniOther, () => _inner.AdoptIdentity(installationId, credential));
        public void Dispose() => _inner.Dispose();
    }
}
