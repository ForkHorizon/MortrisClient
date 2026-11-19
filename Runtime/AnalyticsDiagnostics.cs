using System;

namespace Daliys.Analytics
{
    public sealed class AnalyticsDiagnostics
    {
        internal AnalyticsDiagnostics(bool initialized, bool collectionEnabled, int handoffCount, long handoffDropNewest, long invalidEvents, long rateLimited = 0, long queueEvictedEvents = 0, long bufferFlushedByTrack = 0)
        {
            IsInitialized = initialized;
            IsCollectionEnabled = collectionEnabled;
            HandoffCount = handoffCount;
            HandoffDropNewest = handoffDropNewest;
            InvalidEvents = invalidEvents;
            QueueEvictedEvents = queueEvictedEvents;
            BufferFlushedByTrack = bufferFlushedByTrack;
            RateLimited = rateLimited;
        }

        public bool IsInitialized { get; }
        public bool IsCollectionEnabled { get; }
        public int HandoffCount { get; }
        public long HandoffDropNewest { get; }
        public long InvalidEvents { get; }
        /// <summary>Events dropped from the on-device queue (oldest first) because it was full (<see cref="AnalyticsOptions.DurableByteLimit"/>), since the queue was created. The server is told which numbers were lost.</summary>
        public long QueueEvictedEvents { get; }
        /// <summary>How many times a <c>Track()</c> call had to write the full in-memory buffer to the queue itself (a burst larger than <see cref="AnalyticsOptions.EventBufferBytes"/>); each one made that frame longer. Use <c>TrackBatchAsync</c> for exports.</summary>
        public long BufferFlushedByTrack { get; }
        /// <summary>Events refused by the per-name rate limit.</summary>
        public long RateLimited { get; }
    }

    public enum TrackResult
    {
        AcceptedToHandoff,
        NotInitialized,
        CollectionDisabled,
        InvalidEventName,
        InvalidProperties,
        HandoffFull,
        RateLimited
    }

    public enum FlushStatus
    {
        NotInitialized,
        PersistenceUnavailable,
        PersistedToDevice,
        Uploaded,
        UploadDeferred,
        PersistenceFailed
    }

    public sealed class FlushResult
    {
        internal FlushResult(FlushStatus status, int handoffEventsPending)
        {
            Status = status;
            HandoffEventsPending = handoffEventsPending;
        }

        public FlushStatus Status { get; }
        public int HandoffEventsPending { get; }
    }
}
