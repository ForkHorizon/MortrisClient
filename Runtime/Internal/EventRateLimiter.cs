using System;
using System.Collections.Generic;
using System.Diagnostics;

namespace Daliys.Analytics.Internal
{
    /// <summary>
    /// Per-name token buckets: an event name may be tracked at most N times per second (a burst of N is allowed). Protects the queue, the battery and the
    /// bill from a game that reports something every frame. With no limits configured <see cref="TryAcquire"/> is a single volatile read.
    /// </summary>
    internal sealed class EventRateLimiter
    {
        private sealed class Bucket { internal double Tokens; internal long LastTicks; }

        private readonly object _sync = new object();
        private readonly Dictionary<string, int> _limits = new Dictionary<string, int>(StringComparer.Ordinal);
        private readonly Dictionary<string, Bucket> _buckets = new Dictionary<string, Bucket>(StringComparer.Ordinal);
        private readonly Func<long> _ticks;
        private readonly double _ticksPerSecond;
        private int _defaultLimit;
        private volatile bool _active;
        private long _limited;

        internal EventRateLimiter(int defaultPerSecond, Func<long> ticks = null, double ticksPerSecond = 0)
        {
            _defaultLimit = Math.Max(0, defaultPerSecond);
            _ticks = ticks ?? Stopwatch.GetTimestamp;
            _ticksPerSecond = ticks == null ? Stopwatch.Frequency : ticksPerSecond;
            _active = _defaultLimit > 0;
        }

        /// <summary>Events refused so far.</summary>
        internal long Limited => System.Threading.Interlocked.Read(ref _limited);

        /// <summary>Sets the limit for one name (0 removes it, falling back to the default). A negative value exempts the name from any limit.</summary>
        internal void SetLimit(string name, int perSecond)
        {
            lock (_sync)
            {
                if (perSecond == 0) _limits.Remove(name); else _limits[name] = perSecond;
                _buckets.Remove(name);
                _active = _defaultLimit > 0 || _limits.Count > 0;
            }
        }

        /// <summary>Replaces the default limit (0 = none), e.g. when the server's policy changes.</summary>
        internal void SetDefault(int perSecond)
        {
            lock (_sync)
            {
                _defaultLimit = Math.Max(0, perSecond);
                _buckets.Clear();
                _active = _defaultLimit > 0 || _limits.Count > 0;
            }
        }

        internal bool TryAcquire(string name)
        {
            if (!_active) return true;
            lock (_sync)
            {
                if (!_limits.TryGetValue(name, out var limit)) limit = _defaultLimit;
                if (limit <= 0) return true;
                var now = _ticks();
                if (!_buckets.TryGetValue(name, out var bucket))
                {
                    bucket = new Bucket { Tokens = limit, LastTicks = now };
                    _buckets.Add(name, bucket);
                }
                else
                {
                    bucket.Tokens = Math.Min(limit, bucket.Tokens + (now - bucket.LastTicks) / _ticksPerSecond * limit);
                    bucket.LastTicks = now;
                }
                if (bucket.Tokens >= 1) { bucket.Tokens -= 1; return true; }
            }
            System.Threading.Interlocked.Increment(ref _limited);
            return false;
        }
    }
}
