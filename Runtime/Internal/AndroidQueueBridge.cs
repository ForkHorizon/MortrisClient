using System;
using Daliys.Analytics.Internal.Transport;

namespace Daliys.Analytics.Internal
{
    internal interface IAnalyticsQueueBridge : IDisposable
    {
        /// <summary>Stores <paramref name="count"/> event records (frame layout of <see cref="EventBuffer"/>) in one transaction; the queue numbers them.</summary>
        void EnqueueRecords(byte[] frames, int count, string counters = null);
        /// <summary>Bounds every later <see cref="EnqueueRecords"/> applies: event count (0 = none), bytes (positive), age in ms (0 = no expiry). Set once before the first write.</summary>
        void SetLimits(int eventLimit, long byteLimit, long maxAgeMilliseconds);
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
        /// <summary>Small durable key/value storage of the queue (V8 keeps its token, shape table and server counts here). Missing keys read as an empty string.</summary>
        string GetMeta(string key);
        void SetMeta(string key, string value);
        /// <summary>Takes the installation identity the V8 server issued, so a V1 fallback belongs to the same installation (queued rows and the stream are untouched).</summary>
        void AdoptIdentity(string installationId, string credential);
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
                if (activity == null) return null;
                var instance = new AndroidQueueBridgeInstance(activity);
                if (!AnalyticsProf.Compiled) return instance;
                instance.EnableJavaProfile();
                AnalyticsProf.JavaProfile = instance.GetJavaProfile;
                return new ProfiledQueueBridge(instance);
            }
        }

        private sealed class AndroidQueueBridgeInstance : IAnalyticsQueueBridge
        {
            private readonly UnityEngine.AndroidJavaObject _queue;
            // The two calls made for every write and read go through plain JNI with method ids resolved once: AndroidJavaObject.Call builds a
            // signature by reflection on each call, which measured at about 34 KB of managed garbage per call.
            private readonly bool _lowLevel;
            private readonly System.IntPtr _handle, _enqueueId, _readId;
            private System.IntPtr _classRef;
            // The Java calls that change the row count and the cached count are one step, so the cache never ends up behind the queue.
            private readonly object _countSync = new object();
            private readonly UnityEngine.jvalue[] _enqueueArgs = new UnityEngine.jvalue[3], _readArgs = new UnityEngine.jvalue[1];

            internal AndroidQueueBridgeInstance(UnityEngine.AndroidJavaObject activity)
            {
                _queue = new UnityEngine.AndroidJavaObject("com.daliys.analytics.AnalyticsQueue", activity);
                try
                {
                    _handle = _queue.GetRawObject();
                    var local = UnityEngine.AndroidJNI.GetObjectClass(_handle);
                    var type = _classRef = UnityEngine.AndroidJNI.NewGlobalRef(local); // keeps the class (and so its method ids) alive
                    UnityEngine.AndroidJNI.DeleteLocalRef(local);
                    _enqueueId = UnityEngine.AndroidJNI.GetMethodID(type, "enqueueRecords", "([BILjava/lang/String;)I");
                    _readId = UnityEngine.AndroidJNI.GetMethodID(type, "readOldest", "(I)[B");
                    _lowLevel = _enqueueId != System.IntPtr.Zero && _readId != System.IntPtr.Zero;
                }
                catch (System.Exception)
                {
                    _lowLevel = false;
                }
            }

            private static void ThrowIfJavaFailed()
            {
                var failure = UnityEngine.AndroidJNI.ExceptionOccurred();
                if (failure == System.IntPtr.Zero) return;
                UnityEngine.AndroidJNI.ExceptionClear();
                UnityEngine.AndroidJNI.DeleteLocalRef(failure);
                throw new System.InvalidOperationException("The Android analytics queue rejected the call.");
            }

            private int EnqueueLowLevel(byte[] frames, int count, string counters)
            {
                var array = UnityEngine.AndroidJNI.ToByteArray(frames);
                var text = counters == null ? System.IntPtr.Zero : UnityEngine.AndroidJNI.NewStringUTF(counters);
                try
                {
                    _enqueueArgs[0].l = array; _enqueueArgs[1].i = count; _enqueueArgs[2].l = text;
                    var pending = UnityEngine.AndroidJNI.CallIntMethod(_handle, _enqueueId, _enqueueArgs);
                    ThrowIfJavaFailed();
                    return pending;
                }
                finally
                {
                    UnityEngine.AndroidJNI.DeleteLocalRef(array);
                    if (text != System.IntPtr.Zero) UnityEngine.AndroidJNI.DeleteLocalRef(text);
                }
            }

            private byte[] ReadLowLevel(int maxEvents)
            {
                _readArgs[0].i = maxEvents;
                var array = UnityEngine.AndroidJNI.CallObjectMethod(_handle, _readId, _readArgs);
                ThrowIfJavaFailed();
                try { return array == System.IntPtr.Zero ? null : UnityEngine.AndroidJNI.FromByteArray(array); }
                finally { if (array != System.IntPtr.Zero) UnityEngine.AndroidJNI.DeleteLocalRef(array); }
            }

            private int _pending;

            /// <summary>Profiling build only: the Java queue records its own stage timers from now on.</summary>
            internal void EnableJavaProfile() { try { _queue.Call("setProfiling", true); } catch (System.Exception) { } }

            internal string GetJavaProfile()
            {
                try { return _queue.Call<string>("getProfile"); } catch (System.Exception) { return ""; }
            }

            public int PendingCount => System.Threading.Volatile.Read(ref _pending);

            public void EnqueueRecords(byte[] frames, int count, string counters = null)
            {
                lock (_countSync)
                    _pending = _lowLevel ? EnqueueLowLevel(frames, count, counters) : _queue.Call<int>("enqueueRecords", frames, count, counters ?? "");
            }

            public void SetLimits(int eventLimit, long byteLimit, long maxAgeMilliseconds) => _queue.Call("setLimits", eventLimit, byteLimit, maxAgeMilliseconds);

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

            public QueueBatch ReadOldest(int maxEvents) => QueueBatch.FromFrame(_lowLevel ? ReadLowLevel(maxEvents) : _queue.Call<byte[]>("readOldest", maxEvents));

            public void SaveSessionState(string state) => _queue.Call("saveSessionState", state);

            public string LoadSessionState() => _queue.Call<string>("loadSessionState");

            public string GetPreviousExitInfo() => _queue.Call<string>("getPreviousExitInfo");

            public int DeleteAcknowledged(string eventIdsJson)
            {
                lock (_countSync)
                {
                    var deleted = _queue.Call<int>("deleteAcknowledged", eventIdsJson);
                    _pending -= deleted;
                    return deleted;
                }
            }

            public void ClearAllPendingEvents()
            {
                lock (_countSync)
                {
                    _queue.Call("clearAllPendingEvents");
                    _pending = 0;
                }
            }

            public string GetSequenceState() => _queue.Call<string>("getSequenceState");

            public void SetStreamEpoch(long epoch) => _queue.Call("setStreamEpoch", epoch);

            public int DeleteThroughSequence(long ackThrough)
            {
                lock (_countSync)
                {
                    var deleted = _queue.Call<int>("deleteThroughSequence", ackThrough);
                    _pending -= deleted;
                    return deleted;
                }
            }

            public void BeginNewStream() => _queue.Call("beginNewStream");

            public string GetMeta(string key) => _queue.Call<string>("getMeta", key) ?? "";

            public void SetMeta(string key, string value) => _queue.Call("setMeta", key, value ?? "");

            public void AdoptIdentity(string installationId, string credential) => _queue.Call("adoptIdentity", installationId, credential);

            public void Dispose()
            {
                if (_classRef != System.IntPtr.Zero)
                {
                    UnityEngine.AndroidJNI.DeleteGlobalRef(_classRef);
                    _classRef = System.IntPtr.Zero;
                }
                _queue.Dispose();
            }

            private AnalyticsQueueState ToState(UnityEngine.AndroidJavaObject result)
            {
                var state = ReadState(result);
                lock (_countSync)
                    _pending = state.PendingCount;
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
