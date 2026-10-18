using System;

namespace Daliys.Analytics.Internal
{
    internal interface IAnalyticsQueueBridge : IDisposable
    {
        void EnqueueBatch(string eventsJson, int eventLimit, long byteLimit, long maxAgeMilliseconds);
        AnalyticsQueueState GetState();
        AnalyticsQueueState ResetIdentity();
        string ReadOldestBatch(int maxEvents);
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

            public void EnqueueBatch(string eventsJson, int eventLimit, long byteLimit, long maxAgeMilliseconds)
            {
                var result = _queue.Call<UnityEngine.AndroidJavaObject>("enqueueBatch", eventsJson, eventLimit, byteLimit, maxAgeMilliseconds);
                result?.Dispose();
            }

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

            public string ReadOldestBatch(int maxEvents) => _queue.Call<string>("readOldestBatch", maxEvents);

            public int DeleteAcknowledged(string eventIdsJson) =>
                _queue.Call<int>("deleteAcknowledged", eventIdsJson);

            public void ClearAllPendingEvents()
            {
                _queue.Call("clearAllPendingEvents");
            }

            public string GetSequenceState() => _queue.Call<string>("getSequenceState");

            public void SetStreamEpoch(long epoch) => _queue.Call("setStreamEpoch", epoch);

            public int DeleteThroughSequence(long ackThrough) => _queue.Call<int>("deleteThroughSequence", ackThrough);

            public void BeginNewStream() => _queue.Call("beginNewStream");

            public void Dispose()
            {
                _queue.Dispose();
            }

            private static AnalyticsQueueState ToState(UnityEngine.AndroidJavaObject result) =>
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
