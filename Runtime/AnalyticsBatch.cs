// Batch of events for Analytics.TrackBatchAsync.
using System;
using System.Collections.Generic;

namespace Daliys.Analytics
{
    /// <summary>One event of <see cref="Analytics.TrackBatchAsync"/>. <see cref="Time"/> is when it happened; leave it empty for the moment of the call.</summary>
    public readonly struct BatchEvent
    {
        public BatchEvent(string name, IReadOnlyDictionary<string, object> properties = null, DateTimeOffset? time = null)
        {
            Name = name;
            Properties = properties;
            Time = time;
        }

        public string Name { get; }
        public IReadOnlyDictionary<string, object> Properties { get; }
        public DateTimeOffset? Time { get; }
    }

    /// <summary>What happened to the events of one <see cref="Analytics.TrackBatchAsync"/> call.</summary>
    public sealed class BatchResult
    {
        internal BatchResult(int total, int accepted, int invalid, int notStored, bool completed, bool collectionDisabled = false)
        {
            Total = total;
            Accepted = accepted;
            Invalid = invalid;
            NotStored = notStored;
            Completed = completed;
            CollectionDisabled = collectionDisabled;
        }

        /// <summary>Events handed in.</summary>
        public int Total { get; }
        /// <summary>Events written to the on-device queue (they will be sent like any other).</summary>
        public int Accepted { get; }
        /// <summary>Events refused because of an invalid name or properties (counted in <see cref="AnalyticsDiagnostics.InvalidEvents"/> too).</summary>
        public int Invalid { get; }
        /// <summary>Events that could not be stored (no queue on this platform, or the write failed).</summary>
        public int NotStored { get; }
        /// <summary>False when the call was cancelled before every event was handled.</summary>
        public bool Completed { get; }
        /// <summary>Collection is switched off (see <see cref="Analytics.SetCollectionEnabled"/>): nothing was stored.</summary>
        public bool CollectionDisabled { get; }
    }
}
