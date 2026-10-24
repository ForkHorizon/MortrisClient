#!/usr/bin/env python3
"""Copies the analytics package to DEST and adds V7Prof instrumentation. The repo package is never modified.
Every replacement must match exactly once, otherwise the script aborts (so a changed SDK cannot silently lose a probe point)."""
import shutil, sys, os, re
SRC, DEST = sys.argv[1], sys.argv[2]
shutil.rmtree(DEST, ignore_errors=True)
shutil.copytree(SRC, DEST, ignore=shutil.ignore_patterns('night-run~', 'profiling-run~', 'MortrisV7Data', 'Theory~', 'graphify-out', '.git', 'Native~', 'Tests', 'Samples~', '*.meta.bak'))
shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'unity/V7Prof.cs'), os.path.join(DEST, 'Runtime/Internal/V7Prof.cs'))
def patch(rel, old, new, count=1):
    p = os.path.join(DEST, rel); s = open(p).read()
    if s.count(old) != count: sys.exit(f'PATCH FAILED {rel}: expected {count} match(es), found {s.count(old)}: {old[:70]!r}')
    open(p, 'w').write(s.replace(old, new))
R = 'Runtime/Internal/'
# main thread
patch(R + 'AnalyticsRuntime.cs', 'internal TrackResult Track(string eventName, IReadOnlyDictionary<string, object> properties)\n        {',
 'internal TrackResult Track(string eventName, IReadOnlyDictionary<string, object> properties)\n        { var pt = V7Prof.Begin(); try { return TrackInner(eventName, properties); } finally { V7Prof.End(V7Prof.TrackTotal, pt); } }\n\n        private TrackResult TrackInner(string eventName, IReadOnlyDictionary<string, object> properties)\n        {')
patch(R + 'AnalyticsRuntime.cs', 'if (!_persistenceWorker.TryEnqueue(trackedEvent))', 'var pe = V7Prof.Begin(); var accepted = _persistenceWorker.TryEnqueue(trackedEvent); V7Prof.End(V7Prof.TrackEnqueue, pe);\n            if (!accepted)')
# worker
W = R + 'AnalyticsPersistenceWorker.cs'
patch(W, 'if (Interlocked.CompareExchange(ref _isScheduled, 1, 0) == 0)\n                ThreadPool', 'V7Prof.Add(V7Prof.ScheduleCalls, 1);\n            if (Interlocked.CompareExchange(ref _isScheduled, 1, 0) == 0)\n                ThreadPool')
patch(W, 'private void PersistPending()\n        {', 'private void PersistPending()\n        { V7Prof.Add(V7Prof.PersistCalls, 1); var pp = V7Prof.Begin(); try { PersistPendingInner(); } finally { V7Prof.End(V7Prof.PersistTotal, pp); } }\n\n        private void PersistPendingInner()\n        {')
patch(W, 'var batch = SnapshotBatch();', 'var ps = V7Prof.Begin(); var batch = SnapshotBatch(); V7Prof.End(V7Prof.Snapshot, ps);')
patch(W, '''                    _bridge.EnqueueBatch(
                        PersistenceEventSerializer.Serialize(batch, _device),''', '''                    V7Prof.Add(V7Prof.PersistEvents, batch.Count);
                    var pz = V7Prof.Begin(); var json = PersistenceEventSerializer.Serialize(batch, _device); V7Prof.End(V7Prof.Serialize, pz);
                    _bridge.EnqueueBatch(
                        json,''')
patch(W, 'RemovePersistedPrefix(batch);', 'var pr = V7Prof.Begin(); RemovePersistedPrefix(batch); V7Prof.End(V7Prof.RemovePrefix, pr);')
patch(W, 'var upload = _uploader.Flush(_bridge, HasFlushWaiters());', 'V7Prof.Add(V7Prof.FlushCalls, 1); var pf = V7Prof.Begin(); var upload = _uploader.Flush(_bridge, HasFlushWaiters()); V7Prof.End(V7Prof.UploaderFlush, pf);')
# JNI bridge
B = R + 'AndroidQueueBridge.cs'
patch(B, 'var result = _queue.Call<UnityEngine.AndroidJavaObject>("enqueueBatch", eventsJson, eventLimit, byteLimit, maxAgeMilliseconds);\n                result?.Dispose();',
 'var pj = V7Prof.Begin(); var result = _queue.Call<UnityEngine.AndroidJavaObject>("enqueueBatch", eventsJson, eventLimit, byteLimit, maxAgeMilliseconds);\n                result?.Dispose(); V7Prof.End(V7Prof.JniEnqueueBatch, pj);')
patch(B, 'using (var result = _queue.Call<UnityEngine.AndroidJavaObject>("getState"))\n                    return ToState(result);',
 'var pj = V7Prof.Begin(); try { using (var result = _queue.Call<UnityEngine.AndroidJavaObject>("getState"))\n                    return ToState(result); } finally { V7Prof.End(V7Prof.JniGetState, pj); }')
patch(B, 'public string ReadOldestBatch(int maxEvents) => _queue.Call<string>("readOldestBatch", maxEvents);', 'public string ReadOldestBatch(int maxEvents) => V7Prof.Timed(V7Prof.JniReadBatch, () => _queue.Call<string>("readOldestBatch", maxEvents));')
patch(B, '_queue.Call<int>("deleteAcknowledged", eventIdsJson);', 'V7Prof.Timed(V7Prof.JniDeleteAck, () => _queue.Call<int>("deleteAcknowledged", eventIdsJson));')
patch(B, 'public int DeleteThroughSequence(long ackThrough) => _queue.Call<int>("deleteThroughSequence", ackThrough);', 'public int DeleteThroughSequence(long ackThrough) => V7Prof.Timed(V7Prof.JniDeleteAck, () => _queue.Call<int>("deleteThroughSequence", ackThrough));')
# uploader (V1 path + http)
U = R + 'AnalyticsUploader.cs'
patch(U, 'var events = ParseQueuedEvents(queue.ReadOldestBatch(batchSize));', 'var rawBatch = queue.ReadOldestBatch(batchSize); var pq = V7Prof.Begin(); var events = ParseQueuedEvents(rawBatch); V7Prof.End(V7Prof.V1ParseQueued, pq);')
patch(U, 'private ServerResponse SendBatch(AnalyticsQueueState state, string eventsJson)\n        {', 'private ServerResponse SendBatch(AnalyticsQueueState state, string eventsJson)\n        { V7Prof.Add(V7Prof.Batches, 1); var pb = V7Prof.Begin(); try { return SendBatchInner(state, eventsJson); } finally { V7Prof.End(V7Prof.V1SendBatch, pb); } }\n\n        private ServerResponse SendBatchInner(AnalyticsQueueState state, string eventsJson)\n        {')
patch(U, 'request.Content = gzip ? GzipContent(body) : new StringContent(body, Encoding.UTF8, "application/json");', 'var pg = V7Prof.Begin(); if (gzip) V7Prof.Add(V7Prof.BytesV1Json, Encoding.UTF8.GetByteCount(body));\n                request.Content = gzip ? GzipContent(body) : new StringContent(body, Encoding.UTF8, "application/json"); if (gzip) V7Prof.End(V7Prof.V1Gzip, pg);')
patch(U, 'using (var response = _client.SendAsync(request).GetAwaiter().GetResult())\n                {\n                    var responseBody', 'var ph = V7Prof.Begin(); var sent = _client.SendAsync(request).GetAwaiter().GetResult(); V7Prof.End(V7Prof.HttpSend, ph);\n                using (var response = sent)\n                {\n                    var responseBody')
patch(U, 'var content = new ByteArrayContent(bytes.ToArray());', 'var gz = bytes.ToArray(); V7Prof.Add(V7Prof.BytesV1Gzip, gz.Length); var content = new ByteArrayContent(gz);')
# V7 session
S = R + 'Transport/V7Session.cs'
patch(S, 'var encoded = _encoder.Encode(batch);', 'var pe7 = V7Prof.Begin(); var encoded = _encoder.Encode(batch); V7Prof.End(V7Prof.V7Encode, pe7);')
patch(S, 'return _http.PostPacket("/v2/events/packet", encoded.Frame, headers, state.InstallationCredential);', 'V7Prof.Add(V7Prof.BytesV7, encoded.Frame.Length); V7Prof.Add(V7Prof.Packets, 1); var pp7 = V7Prof.Begin(); try { return _http.PostPacket("/v2/events/packet", encoded.Frame, headers, state.InstallationCredential); } finally { V7Prof.End(V7Prof.V7PostPacket, pp7); }')
print('patched OK ->', DEST)
