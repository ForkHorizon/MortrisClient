// What the runtime needs from the path between Track() and the server: the Android worker (threads, SQLite queue) or the browser pipeline (main thread, localStorage).
using System;
using System.Threading;
using System.Threading.Tasks;
using Daliys.Analytics.Internal.Session;

namespace Daliys.Analytics.Internal
{
    internal interface IEventPipeline : IDisposable
    {
        /// <summary>The device fields every record carries, encoded once.</summary>
        byte[] ContextBytes { get; }
        int HandoffCount { get; }
        long BufferFlushedByTrack { get; }
        long QueueEvicted { get; }
        /// <summary>True when everything runs on the Unity main thread (WebGL): work that would go to a pool thread runs inline instead.</summary>
        bool MainThreadOnly { get; }
        void AttachSession(SessionTracker session);
        bool TryEnqueue(byte[] record, int length, bool priority = false);
        bool WriteFramesDirect(byte[] frames, int count);
        void WakeUp();
        void SetNetworkReachable(bool reachable);
        long NextId(string counter);
        void ClearPending();
        bool PersistNow();
        void RequestBackgroundUpload();
        void OnForeground();
        Task<FlushResult> FlushAsync(CancellationToken cancellationToken);
        /// <summary>Called every frame on the main thread (the browser pipeline's clock; the Android worker has its own timers).</summary>
        void Tick();
    }
}
