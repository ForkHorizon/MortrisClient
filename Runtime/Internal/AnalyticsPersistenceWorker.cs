using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Daliys.Analytics.Internal.Session;
using Daliys.Analytics.Internal.Transport;
using UnityEngine;

namespace Daliys.Analytics.Internal
{
    /// <summary>
    /// Owns the path from <c>Track()</c> to the durable queue and the uploader. Events are written as binary records into an in-memory buffer; a short
    /// timer (the buffer window, 200 ms by default) or a size threshold hands the buffer to the Java queue in one transaction. Lifecycle callers can ask
    /// for an immediate, awaited write (<see cref="PersistNow"/>); the upload still follows its own schedule.
    /// </summary>
    internal sealed class AnalyticsPersistenceWorker : IDisposable
    {
        /// <summary>Records that make the buffer write straight away instead of waiting for the window.</summary>
        private const int ImmediateThreshold = 128;
        internal const int BufferCapacity = 1 << 30;   // the buffer is bounded by bytes (AnalyticsOptions.EventBufferBytes), not by a number of events
        private static readonly TimeSpan RetryDelay = TimeSpan.FromSeconds(2);
        private static readonly TimeSpan HeartbeatInterval = TimeSpan.FromSeconds(30);

        private readonly object _sync = new object();
        private readonly AnalyticsOptions _options;
        private readonly AnalyticsDeviceContext _device;
        private readonly AnalyticsUploader _uploader;
        private readonly Action<ServerPolicy> _policyChanged;
        private readonly Timer _uploadTimer, _flushTimer, _heartbeatTimer, _restoreTimer;
        private int _networkReachable = 1;
        private static readonly System.Random RestoreJitter = new System.Random();
        private readonly EventBuffer _buffer;
        private readonly AnalyticsCounters _counters = new AnalyticsCounters();
        private readonly List<TaskCompletionSource<FlushResult>> _flushWaiters = new List<TaskCompletionSource<FlushResult>>();
        private readonly object _writeSync = new object();
        private IAnalyticsQueueBridge _bridge;
        private SessionTracker _session;
        private int _savedSessionVersion = -1;
        private bool _sessionRecovered;
        private int _clearRequested;
        private int _isScheduled;
        private int _isDisposed;
        private int _timerArmed;
        private int _heartbeatDue;
        private int _backgroundUploadRequested;
        private long _lastBackgroundUploadTicks;
        private long _bufferFlushedByTrack;
        private long _queueEvicted;
        private long _lastEvictedReadTicks;

        internal AnalyticsPersistenceWorker(AnalyticsOptions options, Action<ServerPolicy> policyChanged)
        {
            _options = options;
            _buffer = new EventBuffer(BufferCapacity, options.EventBufferBytes);
            var pi = AnalyticsProf.Begin();
            _device = AnalyticsDeviceContext.Create(options);
            AnalyticsProf.End(Stage.InitDeviceContext, pi);
            pi = AnalyticsProf.Begin();
            ContextBytes = EventContext.Build(_device.AppVersion, _device.BuildNumber, _device.Platform, _device.OSVersion, _device.DeviceClass, _device.Locale, _device.TimezoneOffsetMinutes);
            AnalyticsProf.End(Stage.InitEventContext, pi);
            _policyChanged = policyChanged;
            pi = AnalyticsProf.Begin();
            _uploader = new AnalyticsUploader(options, _device, policyChanged);
            AnalyticsProf.End(Stage.InitUploader, pi);
            pi = AnalyticsProf.Begin();
            _uploadTimer = new Timer(_ => Schedule(), null, options.UploadInterval, options.UploadInterval);
            _flushTimer = new Timer(_ => { Volatile.Write(ref _timerArmed, 0); Schedule(); }, null, Timeout.Infinite, Timeout.Infinite);
            _heartbeatTimer = new Timer(_ => { Volatile.Write(ref _heartbeatDue, 1); Schedule(); }, null, HeartbeatInterval, HeartbeatInterval);
            _restoreTimer = new Timer(_ => UploadSoon(), null, Timeout.Infinite, Timeout.Infinite);
            AnalyticsProf.End(Stage.InitTimers, pi);
        }

        /// <summary>The device fields every record carries, encoded once.</summary>
        internal byte[] ContextBytes { get; }

        /// <summary>Connects the session tracker whose state is saved with the queue and whose predecessor is recovered on the first run.</summary>
        internal void AttachSession(SessionTracker session) => _session = session;

        internal int HandoffCount => _buffer.Count;

        internal long BufferFlushedByTrack => Interlocked.Read(ref _bufferFlushedByTrack);
        internal long QueueEvicted => Interlocked.Read(ref _queueEvicted);

        internal bool TryEnqueue(byte[] record, int length, bool priority = false)
        {
            if (Volatile.Read(ref _isDisposed) != 0)
                return false;
            var tb = AnalyticsProf.Begin();
            var appended = _buffer.TryAppend(record, length, priority);
            AnalyticsProf.End(Stage.TrackBuffer, tb);
            if (!appended)
            {
                // A burst filled the buffer. Nothing is dropped: this call writes the buffer to the durable queue itself (the frame gets longer, which is the price of not using
                // Analytics.TrackBatchAsync) and then appends. Only where there is no queue to write to (the Editor) or the write failed does the event stay refused.
                var tp = AnalyticsProf.Begin();
                var flushed = !priority && FlushBufferOnCaller();
                AnalyticsProf.End(Stage.TrackPressureFlush, tp);
                AnalyticsProf.Count(AnalyticsProf.Counter.TrackBufferFull);
                if (!flushed || !_buffer.TryAppend(record, length, priority))
                    return false;
                Interlocked.Increment(ref _bufferFlushedByTrack);
            }

            if (_buffer.Count >= ImmediateThreshold || _options.EventBufferWindow <= TimeSpan.Zero)
                Schedule();
            else if (Interlocked.CompareExchange(ref _timerArmed, 1, 0) == 0)
                _flushTimer.Change(_options.EventBufferWindow, Timeout.InfiniteTimeSpan);
            return true;
        }

        /// <summary>
        /// The game is leaving the foreground or quitting: after the durable write, try one short upload of what is queued (no waiting for the interval).
        /// Skipped when the option is off or the previous such upload was less than <see cref="AnalyticsOptions.BackgroundUploadMinGap"/> ago.
        /// </summary>
        internal void RequestBackgroundUpload()
        {
            if (!_options.UploadOnBackground || !AndroidQueueBridge.IsSupported || Volatile.Read(ref _isDisposed) != 0)
                return;
            var now = System.Diagnostics.Stopwatch.GetTimestamp();
            var last = Interlocked.Read(ref _lastBackgroundUploadTicks);
            if (last != 0 && now - last < (long)(_options.BackgroundUploadMinGap.TotalSeconds * System.Diagnostics.Stopwatch.Frequency))
                return;
            Interlocked.Exchange(ref _lastBackgroundUploadTicks, now == 0 ? 1 : now);
            Interlocked.Exchange(ref _backgroundUploadRequested, 1);
            Schedule();
        }

        /// <summary>Writes everything buffered to the durable queue on the calling thread. False when there is no queue or the write failed (the records stay buffered).</summary>
        private bool FlushBufferOnCaller()
        {
            if (!AndroidQueueBridge.IsSupported) return false;
            try
            {
                lock (_writeSync)
                {
                    if (EnsureBridge() == null) return false;
                    RecoverPreviousSession();
                    while (_buffer.Count > 0) WriteBuffer();
                }
                return true;
            }
            catch (Exception exception)
            {
                if (_options.DebugLogging) Debug.LogException(exception);
                return false;
            }
        }

        /// <summary>
        /// Writes records that were already encoded (a frame: per record int32 length then the record) straight to the durable queue from any thread, after what the buffer
        /// holds, so events tracked before the batch keep their place. Used by <c>TrackBatchAsync</c>; returns false when the queue is unavailable or refused the write.
        /// </summary>
        internal bool WriteFramesDirect(byte[] frames, int count)
        {
            if (!AndroidQueueBridge.IsSupported || Volatile.Read(ref _isDisposed) != 0) return false;
#if UNITY_ANDROID && !UNITY_EDITOR
            if (AndroidJNI.AttachCurrentThread() != 0) return false;
#endif
            try
            {
                lock (_writeSync)
                {
                    if (EnsureBridge() == null) return false;
                    RecoverPreviousSession();
                    while (_buffer.Count > 0) WriteBuffer();
                    var counters = _counters.Snapshot();
                    _bridge.EnqueueRecords(frames, count, _options.DurableEventLimit, _options.DurableByteLimit, (long)_options.MaxEventAge.TotalMilliseconds, counters);
                }
                return true;
            }
            catch (Exception exception)
            {
                if (_options.DebugLogging) Debug.LogException(exception);
                return false;
            }
            finally
            {
#if UNITY_ANDROID && !UNITY_EDITOR
                AndroidJNI.DetachCurrentThread();
#endif
            }
        }

        /// <summary>
        /// The platform says whether there is a network at all (<c>Application.internetReachability</c>, polled on the main thread; it needs no permission). While there is none
        /// nothing is attempted. When it comes back an upload follows after 0-5 seconds of random delay, so a region that lost its network does not return in one instant.
        /// </summary>
        internal void SetNetworkReachable(bool reachable)
        {
            var was = Interlocked.Exchange(ref _networkReachable, reachable ? 1 : 0) == 1;
            _uploader.SetNetworkReachable(reachable);
            if (reachable && !was && Volatile.Read(ref _isDisposed) == 0)
            {
                int delay; lock (RestoreJitter) delay = RestoreJitter.Next(0, 5001);
                _restoreTimer.Change(delay, Timeout.Infinite);
            }
        }

        /// <summary>The player came back to the game: forget the back-off so what is due is sent without waiting for the old retry time.</summary>
        internal void OnForeground()
        {
            if (Volatile.Read(ref _isDisposed) != 0) return;
            _uploader.ForgetBackoff();
            Schedule();
        }

        private void UploadSoon()
        {
            if (Volatile.Read(ref _isDisposed) != 0) return;
            _uploader.RequestUploadSoon();
            Schedule();
        }

        /// <summary>Wakes the worker (upload logic included) after records were written behind its back.</summary>
        internal void WakeUp() => Schedule();

        /// <summary>
        /// The next number of a named counter (see <see cref="AnalyticsCounters"/>). The first call loads the stored values from the durable queue, which creates the
        /// queue on the calling thread; after that it is a lock and an increment.
        /// </summary>
        internal long NextId(string counter)
        {
            if (!_counters.IsLoaded)
            {
                lock (_writeSync)
                {
                    if (!_counters.IsLoaded)
                    {
                        var stored = "";
                        try { if (AndroidQueueBridge.IsSupported && EnsureBridge() != null) stored = _bridge.GetMeta("counters"); }
                        catch (Exception exception) { if (_options.DebugLogging) Debug.LogException(exception); }
                        var pc = AnalyticsProf.Begin();
                        _counters.Load(stored);
                        AnalyticsProf.End(Stage.CountersLoad, pc);
                    }
                }
            }
            return _counters.Next(counter);
        }

        internal void ClearPending()
        {
            _buffer.Clear();
            Interlocked.Exchange(ref _clearRequested, 1);
            Schedule();
        }

        /// <summary>
        /// Writes everything buffered (and the session state) to the durable queue on the calling thread, before returning. Used when the game is leaving the
        /// foreground: it must not wait for the worker, which may be inside a network call. Does not upload anything.
        /// </summary>
        internal bool PersistNow()
        {
            var tn = AnalyticsProf.Begin();
            try { return PersistNowCore(); } finally { AnalyticsProf.End(Stage.PersistNow, tn); }
        }

        private bool PersistNowCore()
        {
            if (!AndroidQueueBridge.IsSupported || Volatile.Read(ref _isDisposed) != 0) return false;
            try
            {
                lock (_writeSync)
                {
                    if (EnsureBridge() == null) return false;
                    RecoverPreviousSession();
                    while (_buffer.Count > 0) WriteBuffer();
                    SaveSessionState(true);
                }
                return true;
            }
            catch (Exception exception)
            {
                if (_options.DebugLogging) Debug.LogException(exception);
                return false;
            }
        }

        internal Task<FlushResult> FlushAsync(CancellationToken cancellationToken)
        {
            if (!AndroidQueueBridge.IsSupported)
                return Task.FromResult(new FlushResult(FlushStatus.PersistenceUnavailable, HandoffCount));

            var completion = new TaskCompletionSource<FlushResult>();
            lock (_sync)
                _flushWaiters.Add(completion);

            if (cancellationToken.CanBeCanceled)
                cancellationToken.Register(() => completion.TrySetCanceled(cancellationToken));

            Schedule();
            return completion.Task;
        }

        public void Dispose()
        {
            if (Interlocked.Exchange(ref _isDisposed, 1) != 0)
                return;

            _buffer.Clear();
            _bridge?.Dispose();
            _bridge = null;
            _uploader.Dispose();
            _uploadTimer.Dispose();
            _flushTimer.Dispose();
            _heartbeatTimer.Dispose();
            _restoreTimer.Dispose();
        }

        private void Schedule()
        {
            if (!AndroidQueueBridge.IsSupported || Volatile.Read(ref _isDisposed) != 0)
                return;

            if (Interlocked.CompareExchange(ref _isScheduled, 1, 0) == 0)
                ThreadPool.QueueUserWorkItem(_ => PersistPending());
        }

        private void PersistPending()
        {
            var tw = AnalyticsProf.Begin();
            try { PersistPendingCore(); } finally { AnalyticsProf.End(Stage.WorkerPass, tw); AnalyticsProf.Count(AnalyticsProf.Counter.WorkerPasses); }
        }

        private void PersistPendingCore()
        {
            var status = FlushStatus.PersistedToDevice;
#if UNITY_ANDROID && !UNITY_EDITOR
            var jniAttached = false;
#endif
            // Only the flushes requested before this pass began are forced and completed by it; one that arrives meanwhile gets its own pass,
            // otherwise it would complete with events still waiting for the next timer.
            var mine = TakeFlushWaiters();
            try
            {
                var ti = AnalyticsProf.Begin();
                var idle = IsIdle(mine.Count > 0);
                AnalyticsProf.End(Stage.WorkerIdleCheck, ti);
                if (idle)
                    return; // a timer tick with nothing buffered, no state change and no upload due: no need to attach to the JVM

#if UNITY_ANDROID && !UNITY_EDITOR
                var ta = AnalyticsProf.Begin();
                var attachResult = AndroidJNI.AttachCurrentThread();
                AnalyticsProf.End(Stage.WorkerAttach, ta);
                if (attachResult != 0)
                    throw new InvalidOperationException("Unable to attach the analytics persistence worker to the Android JVM.");
                jniAttached = true;
#endif
                lock (_writeSync)
                {
                    if (EnsureBridge() == null)
                    {
                        status = FlushStatus.PersistenceUnavailable;
                        return;
                    }

                    RecoverPreviousSession();
                    var force = mine.Count > 0;
                    while (Volatile.Read(ref _isDisposed) == 0)
                    {
                        if (Interlocked.Exchange(ref _clearRequested, 0) == 1)
                            _bridge.ClearAllPendingEvents();

                        WriteBuffer();
                        // A window write moves what is buffered; a forced one empties the buffer, including what arrives meanwhile.
                        if (!force || _buffer.Count == 0)
                            break;
                    }
                    var ts = AnalyticsProf.Begin();
                    SaveSessionState(false);
                    AnalyticsProf.End(Stage.WorkerSaveSession, ts);
                    ts = AnalyticsProf.Begin();
                    RefreshEvictedCount();
                    AnalyticsProf.End(Stage.WorkerEvictedRead, ts);
                }

                // A clear requested after the write step above must not let the upload send what it was meant to remove; the finally block reschedules.
                if (Volatile.Read(ref _clearRequested) == 1)
                    return;
                var background = Interlocked.Exchange(ref _backgroundUploadRequested, 0) == 1;
                var tu = AnalyticsProf.Begin();
                var upload = background
                    ? _uploader.Flush(_bridge, true, _options.BackgroundUploadTimeout)
                    : _uploader.Flush(_bridge, mine.Count > 0);
                AnalyticsProf.End(Stage.WorkerUpload, tu);
                status = upload.Status;
            }
            catch (Exception exception)
            {
                if (_options.DebugLogging)
                    Debug.LogException(exception);
                status = FlushStatus.PersistenceFailed;
            }
            finally
            {
#if UNITY_ANDROID && !UNITY_EDITOR
                if (jniAttached)
                {
                    var td = AnalyticsProf.Begin();
                    AndroidJNI.DetachCurrentThread();
                    AnalyticsProf.End(Stage.WorkerDetach, td);
                }
#endif
                Interlocked.Exchange(ref _isScheduled, 0);
                var tc = AnalyticsProf.Begin();
                CompleteFlushes(mine, status);
                AnalyticsProf.End(Stage.WorkerComplete, tc);
                if (HasFlushWaiters()) Schedule();

                if (status == FlushStatus.PersistenceFailed && _buffer.Count > 0 && Interlocked.CompareExchange(ref _timerArmed, 1, 0) == 0)
                    _flushTimer.Change(RetryDelay, Timeout.InfiniteTimeSpan); // a transient write failure retries without waiting for new events
                else if (status != FlushStatus.PersistenceUnavailable && status != FlushStatus.PersistenceFailed)
                {
                    if (Volatile.Read(ref _clearRequested) == 1 || _buffer.Count >= ImmediateThreshold)
                        Schedule();
                    else if (_buffer.Count > 0 && Interlocked.CompareExchange(ref _timerArmed, 1, 0) == 0)
                        _flushTimer.Change(_options.EventBufferWindow, Timeout.InfiniteTimeSpan);
                }
            }
        }

        private void WriteBuffer()
        {
            var tw = AnalyticsProf.Begin();
            var td = AnalyticsProf.Begin();
            var frames = _buffer.Drain(out var count);
            AnalyticsProf.End(Stage.WorkerBufferDrain, td);
            if (count == 0)
                return;
            AnalyticsProf.Count(AnalyticsProf.Counter.WorkerWrites);
            AnalyticsProf.Count(AnalyticsProf.Counter.EventsWritten, count);
            try { WriteDrained(frames, count); } finally { AnalyticsProf.End(Stage.WorkerWriteBuffer, tw); }
        }

        private void WriteDrained(byte[] frames, int count)
        {

            // counters are read after the drain: every number the drained events use was handed out before they were tracked
            var counters = _counters.Snapshot();
            try
            {
                _bridge.EnqueueRecords(frames, count, _options.DurableEventLimit, _options.DurableByteLimit, (long)_options.MaxEventAge.TotalMilliseconds, counters);
            }
            catch
            {
                _buffer.Restore(frames, count); // the records stay in memory for the next attempt
                if (counters != null) _counters.MarkDirty();
                throw;
            }
        }

        /// <summary>The queue counts the events it had to drop (full or expired); read it at most every 5 seconds.</summary>
        private void RefreshEvictedCount()
        {
            var now = System.Diagnostics.Stopwatch.GetTimestamp();
            if (now - Interlocked.Read(ref _lastEvictedReadTicks) < 5 * System.Diagnostics.Stopwatch.Frequency) return;
            Interlocked.Exchange(ref _lastEvictedReadTicks, now);
            long.TryParse(_bridge.GetMeta("evicted_total"), System.Globalization.NumberStyles.None, System.Globalization.CultureInfo.InvariantCulture, out var total);
            Interlocked.Exchange(ref _queueEvicted, total);
        }

        private bool IsIdle(bool flushRequested) =>
            _bridge != null && _sessionRecovered && _buffer.Count == 0 && Volatile.Read(ref _clearRequested) == 0 && Volatile.Read(ref _heartbeatDue) == 0 &&
            Volatile.Read(ref _backgroundUploadRequested) == 0 && !flushRequested && !HasFlushWaiters() && (_session == null || _session.StateVersion == _savedSessionVersion) && _uploader.NothingToDo(_bridge, false);

        private IAnalyticsQueueBridge EnsureBridge()
        {
            if (_bridge != null) return _bridge;
            var t = AnalyticsProf.Begin();
            _bridge = AndroidQueueBridge.TryCreate();
            AnalyticsProf.End(Stage.BridgeCreate, t);
            return _bridge;
        }

        /// <summary>The first run of a process closes the session its predecessor left open (see SessionTracker.Recover).</summary>
        private void RecoverPreviousSession()
        {
            if (_sessionRecovered || _session == null)
                return;
            _sessionRecovered = true;
            var t = AnalyticsProf.Begin();
            var previous = _bridge.LoadSessionState();
            var exit = string.IsNullOrEmpty(previous) ? "" : _bridge.GetPreviousExitInfo();
            _session.Recover(previous, exit);
            AnalyticsProf.End(Stage.SessionRecover, t);
        }

        private void SaveSessionState(bool force)
        {
            var session = _session;
            if (session == null)
                return;
            if (Interlocked.Exchange(ref _heartbeatDue, 0) == 1)
                session.Touch();
            var version = session.StateVersion;
            if (version == _savedSessionVersion && !force)
                return;
            var snapshot = session.Snapshot();
            if (snapshot.Length > 0)
                _bridge.SaveSessionState(snapshot);
            _savedSessionVersion = version;
        }

        private List<TaskCompletionSource<FlushResult>> TakeFlushWaiters()
        {
            lock (_sync)
            {
                var taken = new List<TaskCompletionSource<FlushResult>>(_flushWaiters);
                _flushWaiters.Clear();
                return taken;
            }
        }

        private void CompleteFlushes(List<TaskCompletionSource<FlushResult>> completions, FlushStatus status)
        {
            var result = new FlushResult(status, HandoffCount);
            foreach (var completion in completions)
                completion.TrySetResult(result);
        }

        private bool HasFlushWaiters()
        {
            lock (_sync)
                return _flushWaiters.Count > 0;
        }
    }
}
