using System;
using Daliys.Analytics.Internal.Transport;

namespace Daliys.Analytics.Internal
{
    internal interface IAnalyticsQueueBridge : IDisposable
    {
        /// <summary>Stores <paramref name="count"/> event records (frame layout of <see cref="EventBuffer"/>) in one transaction; the queue numbers them.</summary>
        void EnqueueRecords(byte[] frames, int count, int eventLimit, long byteLimit, long maxAgeMilliseconds);
        AnalyticsQueueState GetState();
        AnalyticsQueueState ResetIdentity();
        /// <summary>Rows queued, as last reported by the queue (kept in step by every call that changes it); no round trip.</summary>
        int PendingCount { get; }
        QueueBatch ReadOldest(int maxEvents);
        void SaveSessionState(string state);
        string LoadSessionState();
        /// <summary>How the previous process of the app ended (JSON), or an empty string.</summary>
        string GetPreviousExitInfo();
        int DeleteAcknowledged(string eventIdsJson);
        void ClearAllPendingEvents();
        /// <summary>JSON: install_id, stream_base, next_sequence, stream_epoch, dropped_version and the dropped [from, to] ranges.</summary>
        string GetSequenceState();
        void SetStreamEpoch(long epoch);
        /// <summary>Deletes queued rows with sequence &lt;= ackThrough (settled by the server). Returns the number deleted.</summary>
        int DeleteThroughSequence(long ackThrough);
        /// <summary>Starts a fresh stream at the lowest queued sequence (epoch cleared, older ranges forgotten).</summary>
        void BeginNewStream();
    }

    internal sealed class AnalyticsQueueState
    {
        internal AnalyticsQueueState(string installationId, string installationCredential, int pendingCount)
        {
            InstallationId = installationId;
            InstallationCredential = installationCredential;
            PendingCount = pendingCount;
        }

        internal string InstallationId { get; }
        internal string InstallationCredential { get; }
        internal int PendingCount { get; }
    }

    internal static class AndroidQueueBridge
    {
#if UNITY_ANDROID && !UNITY_EDITOR
        internal static bool IsSupported => true;

        internal static IAnalyticsQueueBridge TryCreate()
        {
            using (var unityPlayer = new UnityEngine.AndroidJavaClass("com.unity3d.player.UnityPlayer"))
            using (var activity = unityPlayer.GetStatic<UnityEngine.AndroidJavaObject>("currentActivity"))
            {
                return activity == null ? null : new AndroidQueueBridgeInstance(activity);
            }
        }

        private sealed class AndroidQueueBridgeInstance : IAnalyticsQueueBridge
        {
            private readonly UnityEngine.AndroidJavaObject _queue;

            internal AndroidQueueBridgeInstance(UnityEngine.AndroidJavaObject activity)
            {
                _queue = new UnityEngine.AndroidJavaObject("com.daliys.analytics.AnalyticsQueue", activity);
            }

            private int _pending;

            public int PendingCount => System.Threading.Volatile.Read(ref _pending);

            public void EnqueueRecords(byte[] frames, int count, int eventLimit, long byteLimit, long maxAgeMilliseconds) =>
                System.Threading.Volatile.Write(ref _pending, _queue.Call<int>("enqueueRecords", frames, count, eventLimit, byteLimit, maxAgeMilliseconds));

            public AnalyticsQueueState GetState()
            {
                using (var result = _queue.Call<UnityEngine.AndroidJavaObject>("getState"))
                    return ToState(result);
            }

            public AnalyticsQueueState ResetIdentity()
            {
                using (var result = _queue.Call<UnityEngine.AndroidJavaObject>("resetIdentity"))
                    return ToState(result);
            }

            public QueueBatch ReadOldest(int maxEvents) => QueueBatch.FromFrame(_queue.Call<byte[]>("readOldest", maxEvents));

            public void SaveSessionState(string state) => _queue.Call("saveSessionState", state);

            public string LoadSessionState() => _queue.Call<string>("loadSessionState");

            public string GetPreviousExitInfo() => _queue.Call<string>("getPreviousExitInfo");

            public int DeleteAcknowledged(string eventIdsJson)
            {
                var deleted = _queue.Call<int>("deleteAcknowledged", eventIdsJson);
                System.Threading.Interlocked.Add(ref _pending, -deleted);
                return deleted;
            }

            public void ClearAllPendingEvents()
            {
                _queue.Call("clearAllPendingEvents");
                System.Threading.Volatile.Write(ref _pending, 0);
            }

            public string GetSequenceState() => _queue.Call<string>("getSequenceState");

            public void SetStreamEpoch(long epoch) => _queue.Call("setStreamEpoch", epoch);

            public int DeleteThroughSequence(long ackThrough)
            {
                var deleted = _queue.Call<int>("deleteThroughSequence", ackThrough);
                System.Threading.Interlocked.Add(ref _pending, -deleted);
                return deleted;
            }

            public void BeginNewStream() => _queue.Call("beginNewStream");

            public void Dispose()
            {
                _queue.Dispose();
            }

            private AnalyticsQueueState ToState(UnityEngine.AndroidJavaObject result)
            {
                var state = ReadState(result);
                System.Threading.Volatile.Write(ref _pending, state.PendingCount);
                return state;
            }

            private static AnalyticsQueueState ReadState(UnityEngine.AndroidJavaObject result) =>
                new AnalyticsQueueState(
                    result.Call<string>("getInstallationId"),
                    result.Call<string>("getInstallationCredential"),
                    result.Call<int>("getPendingCount"));
        }
#else
        internal static bool IsSupported => false;

        internal static IAnalyticsQueueBridge TryCreate() => null;
#endif
    }
}
