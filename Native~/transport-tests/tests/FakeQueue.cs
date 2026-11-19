// In-memory model of the Android queue with the same sequence, journal and epoch rules, for host tests.
using System;
using System.Collections.Generic;
using System.Linq;
using Daliys.Analytics.Internal;
using Daliys.Analytics.Internal.Transport;

namespace M7Transport.Tests
{
    /// <summary>
    /// In-memory model of the Android queue (AnalyticsQueue.java) with the same sequence, journal and epoch rules. The Java original is
    /// verified on a device by the instrumentation tests; this keeps the V7 session testable on the host.
    /// </summary>
    internal sealed class FakeQueue : IAnalyticsQueueBridge
    {
        private sealed class Row { internal long Sequence; internal string EventId; internal byte[] Record; }

        private readonly List<Row> _rows = new List<Row>();
        private readonly SortedDictionary<long, long> _dropped = new SortedDictionary<long, long>();
        private long _next = 1, _base = 1, _epoch, _droppedVersion;
        internal string InstallId = Guid.NewGuid().ToString("D"), Credential = "credential";
        internal readonly List<string> Calls = new List<string>();

        internal int Pending => _rows.Count;
        internal IReadOnlyList<long> PendingSequences => _rows.Select(r => r.Sequence).ToList();
        internal long StreamEpoch => _epoch;
        internal long DroppedVersion => _droppedVersion;
        internal string DroppedJson() => string.Join(",", _dropped.Select(d => "[" + d.Key + "," + d.Value + "]"));

        /// <summary>Appends events (renumbering them like the queue does); evicts the oldest beyond <paramref name="limit"/>.</summary>
        internal void Enqueue(string eventsJson, int limit = 10000)
        {
            foreach (Dictionary<string, object> e in MiniJson.ParseArray(eventsJson))
            {
                var record = EventRecordJson.FromJson(e, out _);
                Add(record);
            }
            Trim(limit);
        }

        private void Add(byte[] record)
        {
            _rows.Add(new Row { Sequence = _next, EventId = EventRecordFormat.UuidText(record, EventRecordFormat.IdOffset), Record = record });
            _next++;
        }

        private void Trim(int limit)
        {
            var evicted = 0;
            while (_rows.Count > limit) { RecordDropped(_rows[0].Sequence); _rows.RemoveAt(0); evicted++; }
            if (evicted > 0) _droppedVersion++;
        }

        private int _eventLimit = int.MaxValue;

        public void SetLimits(int eventLimit, long byteLimit, long maxAgeMilliseconds) => _eventLimit = eventLimit == 0 ? int.MaxValue : eventLimit;

        public void EnqueueRecords(byte[] frames, int count, string counters = null)
        {
            Calls.Add("EnqueueRecords " + count);
            if (counters != null) Meta["counters"] = counters;
            var position = 0;
            for (var i = 0; i < count; i++)
            {
                var length = QueueBatch.ReadInt32(frames, ref position);
                var record = new byte[length];
                Buffer.BlockCopy(frames, position, record, 0, length);
                position += length;
                if (_rows.Any(r => r.EventId == EventRecordFormat.UuidText(record, EventRecordFormat.IdOffset))) continue;
                Add(record);
            }
            Trim(_eventLimit);
        }

        public int PendingCount => _rows.Count;
        internal readonly Dictionary<string, string> Meta = new Dictionary<string, string>();
        public void AdoptIdentity(string installationId, string credential) { Calls.Add("AdoptIdentity"); InstallId = installationId; Credential = credential; }
        public string GetMeta(string key) => Meta.TryGetValue(key, out var v) ? v : "";
        public void SetMeta(string key, string value) { Calls.Add("SetMeta " + key); Meta[key] = value ?? ""; }
        public string SessionState = "", ExitInfo = "";
        public void SaveSessionState(string state) { Calls.Add("SaveSessionState"); SessionState = state; }
        public string LoadSessionState() => SessionState;
        public string GetPreviousExitInfo() => ExitInfo;

        public QueueBatch ReadOldest(int maxEvents)
        {
            var rows = _rows.Take(maxEvents).ToList();
            var frame = new List<byte>();
            void Int32(int v) { frame.Add((byte)(v >> 24)); frame.Add((byte)(v >> 16)); frame.Add((byte)(v >> 8)); frame.Add((byte)v); }
            Int32(rows.Count);
            foreach (var row in rows)
            {
                frame.Add(EventRecordFormat.Version);
                for (var shift = 56; shift >= 0; shift -= 8) frame.Add((byte)(row.Sequence >> shift));
                Int32(row.Record.Length);
                frame.AddRange(row.Record);
            }
            return QueueBatch.FromFrame(frame.ToArray());
        }

        /// <summary>A batch made of <paramref name="count"/> rows from <paramref name="from"/> (test helper for packet-sized slices of a large queue).</summary>
        public QueueBatch SliceForTest(int from, int count)
        {
            return ReadOldestFrom(from, count);
        }

        private QueueBatch ReadOldestFrom(int from, int count)
        {
            var rows = _rows.Skip(from).Take(count).ToList();
            var frame = new List<byte>();
            void Int32(int v) { frame.Add((byte)(v >> 24)); frame.Add((byte)(v >> 16)); frame.Add((byte)(v >> 8)); frame.Add((byte)v); }
            Int32(rows.Count);
            foreach (var row in rows)
            {
                frame.Add(EventRecordFormat.Version);
                for (var shift = 56; shift >= 0; shift -= 8) frame.Add((byte)(row.Sequence >> shift));
                Int32(row.Record.Length);
                frame.AddRange(row.Record);
            }
            return QueueBatch.FromFrame(frame.ToArray());
        }

        /// <summary>The queued rows in the V1 JSON form, for tests that read what would be sent.</summary>
        public string ReadOldestBatch(int maxEvents) => ReadOldest(maxEvents).ToJsonArray(new EventRecordReader());

        public AnalyticsQueueState GetState() => new AnalyticsQueueState(InstallId, Credential, _rows.Count);

        public AnalyticsQueueState ResetIdentity()
        {
            InstallId = Guid.NewGuid().ToString("D");
            Credential = "credential-" + Guid.NewGuid().ToString("N");
            _epoch = 0;
            _dropped.Clear();
            _base = _rows.Count > 0 ? _rows[0].Sequence : _next;
            return GetState();
        }

        public int DeleteAcknowledged(string eventIdsJson)
        {
            Calls.Add("DeleteAcknowledged");
            var ids = MiniJson.ParseArray(eventIdsJson).Cast<string>().ToList();
            var deleted = 0;
            foreach (var id in ids)
            {
                var row = _rows.FirstOrDefault(r => r.EventId == id);
                if (row == null) continue;
                if (_epoch > 0) { RecordDropped(row.Sequence); _droppedVersion++; }
                _rows.Remove(row);
                deleted++;
            }
            return deleted;
        }

        public void ClearAllPendingEvents() { foreach (var r in _rows) RecordDropped(r.Sequence); if (_rows.Count > 0) _droppedVersion++; _rows.Clear(); }

        public string GetSequenceState() => "{\"install_id\":\"" + InstallId + "\",\"stream_base\":" + _base + ",\"next_sequence\":" + _next + ",\"stream_epoch\":" + _epoch +
            ",\"dropped_version\":" + _droppedVersion + ",\"dropped\":[" + DroppedJson() + "]}";

        public void SetStreamEpoch(long epoch) { Calls.Add("SetStreamEpoch " + epoch); _epoch = epoch; }

        public int DeleteThroughSequence(long ackThrough)
        {
            Calls.Add("DeleteThroughSequence " + ackThrough);
            var deleted = _rows.RemoveAll(r => r.Sequence <= ackThrough);
            foreach (var key in _dropped.Keys.ToList())
            {
                var to = _dropped[key];
                if (to <= ackThrough) _dropped.Remove(key);
                else if (key <= ackThrough) { _dropped.Remove(key); _dropped[ackThrough + 1] = to; }
            }
            return deleted;
        }

        public void BeginNewStream()
        {
            Calls.Add("BeginNewStream");
            _base = _rows.Count > 0 ? _rows[0].Sequence : _next;
            _epoch = 0;
            _dropped.Clear();
            _droppedVersion++;
        }

        public void Dispose() { }

        private void RecordDropped(long sequence)
        {
            var from = _dropped.Where(d => d.Value == sequence - 1).Select(d => (long?)d.Key).FirstOrDefault();
            if (from.HasValue) _dropped[from.Value] = sequence;
            else _dropped[sequence] = sequence;
        }
    }
}
