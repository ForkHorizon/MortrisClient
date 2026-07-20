using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

namespace Daliys.Analytics.Internal
{
    internal sealed class AnalyticsPersistenceWorker : IDisposable
    {
        private const int BatchSize = 32;

        private readonly object _sync = new object();
        private readonly AnalyticsOptions _options;
        private readonly AnalyticsDeviceContext _device;
        private readonly AnalyticsUploader _uploader;
        private readonly Action<ServerPolicy> _policyChanged;
        private readonly Timer _uploadTimer;
        private readonly Queue<AnalyticsRuntime.TrackedEvent> _handoff = new Queue<AnalyticsRuntime.TrackedEvent>();
        private readonly List<TaskCompletionSource<FlushResult>> _flushWaiters = new List<TaskCompletionSource<FlushResult>>();
        private IAnalyticsQueueBridge _bridge;
        private int _clearRequested;
        private int _isScheduled;
        private int _isDisposed;

        internal AnalyticsPersistenceWorker(AnalyticsOptions options, Action<ServerPolicy> policyChanged)
        {
            _options = options;
            _device = AnalyticsDeviceContext.Create(options);
            _policyChanged = policyChanged;
            _uploader = new AnalyticsUploader(options, _device, policyChanged);
            _uploadTimer = new Timer(_ => Schedule(), null, options.UploadInterval, options.UploadInterval);
        }

        internal int HandoffCount
        {
            get
            {
                lock (_sync)
                    return _handoff.Count;
            }
        }

        internal bool TryEnqueue(AnalyticsRuntime.TrackedEvent trackedEvent)
        {
            lock (_sync)
            {
                if (Volatile.Read(ref _isDisposed) != 0 || _handoff.Count >= AnalyticsRuntime.HandoffCapacity)
                    return false;

                _handoff.Enqueue(trackedEvent);
            }

            Schedule();
            return true;
        }

        internal void ClearPending()
        {
            lock (_sync)
                _handoff.Clear();

            Interlocked.Exchange(ref _clearRequested, 1);
            Schedule();
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

            lock (_sync)
                _handoff.Clear();

            _bridge?.Dispose();
            _bridge = null;
            _uploader.Dispose();
            _uploadTimer.Dispose();
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
            var jniAttached = false;
            try
            {
#if UNITY_ANDROID && !UNITY_EDITOR
                if (AndroidJNI.AttachCurrentThread() != 0)
                    throw new InvalidOperationException("Unable to attach the analytics persistence worker to the Android JVM.");
                jniAttached = true;
#endif
                _bridge ??= AndroidQueueBridge.TryCreate();
                if (_bridge == null)
                {
                    status = FlushStatus.PersistenceUnavailable;
                    return;
                }

                while (Volatile.Read(ref _isDisposed) == 0)
                {
                    if (Interlocked.Exchange(ref _clearRequested, 0) == 1)
                        _bridge.ClearAllPendingEvents();

                    var batch = SnapshotBatch();
                    if (batch.Count == 0)
                        break;

                    _bridge.EnqueueBatch(
                        PersistenceEventSerializer.Serialize(batch, _device),
                        _options.DurableEventLimit,
                        _options.DurableByteLimit,
                        (long)_options.MaxEventAge.TotalMilliseconds);
                    RemovePersistedPrefix(batch);
                }

                var upload = _uploader.Flush(_bridge, HasFlushWaiters());
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

                if (status != FlushStatus.PersistenceUnavailable && status != FlushStatus.PersistenceFailed &&
                    (HandoffCount > 0 || Volatile.Read(ref _clearRequested) == 1))
                    Schedule();
            }
        }

        private List<AnalyticsRuntime.TrackedEvent> SnapshotBatch()
        {
            lock (_sync)
            {
                var count = Math.Min(BatchSize, _handoff.Count);
                var batch = new List<AnalyticsRuntime.TrackedEvent>(count);
                foreach (var trackedEvent in _handoff)
                {
                    batch.Add(trackedEvent);
                    if (batch.Count == count)
                        break;
                }
                return batch;
            }
        }

        private void RemovePersistedPrefix(IReadOnlyList<AnalyticsRuntime.TrackedEvent> persistedBatch)
        {
            lock (_sync)
            {
                for (var index = 0; index < persistedBatch.Count && _handoff.Count > 0; index++)
                {
                    if (!string.Equals(_handoff.Peek().EventId, persistedBatch[index].EventId, StringComparison.Ordinal))
                        break;
                    _handoff.Dequeue();
                }
            }
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
