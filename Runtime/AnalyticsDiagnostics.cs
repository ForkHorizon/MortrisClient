using System;

namespace Daliys.Analytics
{
    public sealed class AnalyticsDiagnostics
    {
        internal AnalyticsDiagnostics(bool initialized, bool collectionEnabled, int handoffCount, long handoffDropNewest, long invalidEvents, long rateLimited = 0)
        {
            IsInitialized = initialized;
            IsCollectionEnabled = collectionEnabled;
            HandoffCount = handoffCount;
            HandoffDropNewest = handoffDropNewest;
            InvalidEvents = invalidEvents;
            RateLimited = rateLimited;
        }

        public bool IsInitialized { get; }
        public bool IsCollectionEnabled { get; }
        public int HandoffCount { get; }
        public long HandoffDropNewest { get; }
        public long InvalidEvents { get; }
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
