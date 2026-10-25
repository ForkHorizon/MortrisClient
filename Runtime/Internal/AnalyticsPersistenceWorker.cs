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
        internal const int BufferCapacity = 1024, BufferBytes = 1024 * 1024;
        private static readonly TimeSpan RetryDelay = TimeSpan.FromSeconds(2);
        private static readonly TimeSpan HeartbeatInterval = TimeSpan.FromSeconds(30);

        private readonly object _sync = new object();
        private readonly AnalyticsOptions _options;
        private readonly AnalyticsDeviceContext _device;
        private readonly AnalyticsUploader _uploader;
        private readonly Action<ServerPolicy> _policyChanged;
        private readonly Timer _uploadTimer, _flushTimer, _heartbeatTimer;
        private readonly EventBuffer _buffer = new EventBuffer(BufferCapacity, BufferBytes);
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

        internal AnalyticsPersistenceWorker(AnalyticsOptions options, Action<ServerPolicy> policyChanged)
        {
            _options = options;
            _device = AnalyticsDeviceContext.Create(options);
            ContextBytes = EventContext.Build(_device.AppVersion, _device.BuildNumber, _device.Platform, _device.OSVersion, _device.DeviceClass, _device.Locale, _device.TimezoneOffsetMinutes);
            _policyChanged = policyChanged;
            _uploader = new AnalyticsUploader(options, _device, policyChanged);
            _uploadTimer = new Timer(_ => Schedule(), null, options.UploadInterval, options.UploadInterval);
            _flushTimer = new Timer(_ => { Volatile.Write(ref _timerArmed, 0); Schedule(); }, null, Timeout.Infinite, Timeout.Infinite);
            _heartbeatTimer = new Timer(_ => { Volatile.Write(ref _heartbeatDue, 1); Schedule(); }, null, HeartbeatInterval, HeartbeatInterval);
        }

        /// <summary>The device fields every record carries, encoded once.</summary>
        internal byte[] ContextBytes { get; }

        /// <summary>Connects the session tracker whose state is saved with the queue and whose predecessor is recovered on the first run.</summary>
        internal void AttachSession(SessionTracker session) => _session = session;

        internal int HandoffCount => _buffer.Count;

        internal bool TryEnqueue(byte[] record, int length, bool priority = false)
        {
            if (Volatile.Read(ref _isDisposed) != 0 || !_buffer.TryAppend(record, length, priority))
                return false;

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
            var status = FlushStatus.PersistedToDevice;
#if UNITY_ANDROID && !UNITY_EDITOR
            var jniAttached = false;
#endif
            try
            {
                if (IsIdle())
                    return; // a timer tick with nothing buffered, no state change and no upload due: no need to attach to the JVM

#if UNITY_ANDROID && !UNITY_EDITOR
                if (AndroidJNI.AttachCurrentThread() != 0)
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
                    var force = HasFlushWaiters();
                    while (Volatile.Read(ref _isDisposed) == 0)
                    {
                        if (Interlocked.Exchange(ref _clearRequested, 0) == 1)
                            _bridge.ClearAllPendingEvents();

                        WriteBuffer();
                        // A window write moves what is buffered; a forced one empties the buffer, including what arrives meanwhile.
                        if (!force || _buffer.Count == 0)
                            break;
                    }
                    SaveSessionState(false);
                }

                // A clear requested after the write step above must not let the upload send what it was meant to remove; the finally block reschedules.
                if (Volatile.Read(ref _clearRequested) == 1)
                    return;
                var background = Interlocked.Exchange(ref _backgroundUploadRequested, 0) == 1;
                var upload = background
                    ? _uploader.Flush(_bridge, true, _options.BackgroundUploadTimeout)
                    : _uploader.Flush(_bridge, HasFlushWaiters());
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
                    AndroidJNI.DetachCurrentThread();
#endif
                Interlocked.Exchange(ref _isScheduled, 0);
                CompleteFlushes(status);

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
            var frames = _buffer.Drain(out var count);
            if (count == 0)
                return;

            try
            {
                _bridge.EnqueueRecords(frames, count, _options.DurableEventLimit, _options.DurableByteLimit, (long)_options.MaxEventAge.TotalMilliseconds);
            }
            catch
            {
                _buffer.Restore(frames, count); // the records stay in memory for the next attempt
                throw;
            }
        }

        private bool IsIdle() =>
            _bridge != null && _sessionRecovered && _buffer.Count == 0 && Volatile.Read(ref _clearRequested) == 0 && Volatile.Read(ref _heartbeatDue) == 0 &&
            Volatile.Read(ref _backgroundUploadRequested) == 0 && !HasFlushWaiters() && (_session == null || _session.StateVersion == _savedSessionVersion) && _uploader.NothingToDo(_bridge, false);

        private IAnalyticsQueueBridge EnsureBridge() => _bridge ?? (_bridge = AndroidQueueBridge.TryCreate());

        /// <summary>The first run of a process closes the session its predecessor left open (see SessionTracker.Recover).</summary>
        private void RecoverPreviousSession()
        {
            if (_sessionRecovered || _session == null)
                return;
            _sessionRecovered = true;
            var previous = _bridge.LoadSessionState();
            var exit = string.IsNullOrEmpty(previous) ? "" : _bridge.GetPreviousExitInfo();
            _session.Recover(previous, exit);
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

        private void CompleteFlushes(FlushStatus status)
        {
            List<TaskCompletionSource<FlushResult>> completions;
            lock (_sync)
            {
                completions = new List<TaskCompletionSource<FlushResult>>(_flushWaiters);
                _flushWaiters.Clear();
            }

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
