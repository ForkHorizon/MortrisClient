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
        private sealed class Row { internal long Sequence; internal string EventId; internal string Payload; }

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
                e["sequence"] = new JsonNumber(_next.ToString());
                _rows.Add(new Row { Sequence = _next, EventId = (string)e["event_id"], Payload = TestSupport.Serialize(e) });
                _next++;
            }
            var evicted = 0;
            while (_rows.Count > limit) { RecordDropped(_rows[0].Sequence); _rows.RemoveAt(0); evicted++; }
            if (evicted > 0) _droppedVersion++;
        }

        public void EnqueueBatch(string eventsJson, int eventLimit, long byteLimit, long maxAgeMilliseconds) => Enqueue(eventsJson, eventLimit);
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

        public string ReadOldestBatch(int maxEvents) => "[" + string.Join(",", _rows.Take(maxEvents).Select(r => r.Payload)) + "]";

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
