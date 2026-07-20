using System;

namespace Daliys.Analytics
{
    public sealed class AnalyticsDiagnostics
    {
        internal AnalyticsDiagnostics(bool initialized, bool collectionEnabled, int handoffCount, long handoffDropNewest, long invalidEvents)
        {
            IsInitialized = initialized;
            IsCollectionEnabled = collectionEnabled;
            HandoffCount = handoffCount;
            HandoffDropNewest = handoffDropNewest;
            InvalidEvents = invalidEvents;
        }

        public bool IsInitialized { get; }
        public bool IsCollectionEnabled { get; }
        public int HandoffCount { get; }
        public long HandoffDropNewest { get; }
        public long InvalidEvents { get; }
    }

    public enum TrackResult
    {
        AcceptedToHandoff,
        NotInitialized,
        CollectionDisabled,
        InvalidEventName,
        InvalidProperties,
        HandoffFull
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
