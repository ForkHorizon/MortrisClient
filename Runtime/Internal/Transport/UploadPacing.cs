// Upload schedule and retry backoff after a failed upload.
using System;

namespace Daliys.Analytics.Internal.Transport
{
    /// <summary>
    /// When to try again after a failed upload. The wait starts at <c>initial</c>, doubles after every failure up to <c>maximum</c>, and each wait is spread over its
    /// upper half ("equal jitter": between half and all of the current step) so that clients that failed together (a server outage) do not come back together.
    /// A <c>Retry-After</c> from the server replaces the step (capped at <see cref="RetryAfterCap"/>, with a little spread added).
    /// </summary>
    internal sealed class RetryBackoff
    {
        internal static readonly TimeSpan RetryAfterCap = TimeSpan.FromMinutes(10);
        private readonly TimeSpan _initial, _maximum;
        private readonly Func<double> _random;
        private TimeSpan _step;

        internal RetryBackoff(TimeSpan initial, TimeSpan maximum, Func<double> random)
        {
            _initial = initial; _maximum = maximum; _random = random; _step = initial;
        }

        /// <summary>The step the next failure will use before jitter (for tests and diagnostics).</summary>
        internal TimeSpan CurrentStep => _step;

        /// <summary>Registers a failure and returns how long to wait.</summary>
        internal TimeSpan OnFailure(TimeSpan? retryAfter)
        {
            if (retryAfter.HasValue && retryAfter.Value > TimeSpan.Zero)
            {
                var asked = retryAfter.Value > RetryAfterCap ? RetryAfterCap : retryAfter.Value;
                return asked + TimeSpan.FromMilliseconds(asked.TotalMilliseconds * 0.1 * _random());   // never earlier than the server asked
            }
            var wait = TimeSpan.FromMilliseconds(_step.TotalMilliseconds * (0.5 + 0.5 * _random()));
            _step = TimeSpan.FromMilliseconds(Math.Min(_step.TotalMilliseconds * 2, _maximum.TotalMilliseconds));
            return wait;
        }

        internal void Reset() => _step = _initial;
    }

    /// <summary>
    /// How many events to put into the next packet. A packet is at most <c>cap</c> events (the option, or the backlog size while a lot is waiting). After a failed or
    /// very slow request the size is cut so the next try has a better chance on a poor connection; fast successes grow it back. It needs no permission and no
    /// guess about the kind of network: it only looks at how long the requests took.
    /// </summary>
    internal sealed class PacketSizer
    {
        internal const int Minimum = 20;
        internal static readonly TimeSpan Slow = TimeSpan.FromSeconds(8), Fast = TimeSpan.FromSeconds(3);
        private int _size;

        internal PacketSizer(int start) { _size = Math.Max(Minimum, start); }

        internal int Current => _size;

        /// <summary>The size for the next packet given the ceiling that applies now.</summary>
        internal int Next(int cap)
        {
            cap = Math.Max(Minimum, cap);
            if (_size > cap) _size = cap;
            return Math.Min(_size, cap);
        }

        internal void OnSuccess(TimeSpan took, int cap)
        {
            cap = Math.Max(Minimum, cap);
            if (took >= Slow) _size = Math.Max(Minimum, _size * 3 / 4);
            else if (took <= Fast) _size = Math.Min(cap, _size + Math.Max(10, _size / 2));
        }

        internal void OnFailure() => _size = Math.Max(Minimum, _size / 2);

        /// <summary>The V1 batch endpoint takes at most this many events per request.</summary>
        internal const int V1BatchLimit = 100;

        /// <summary>Events that make a "full" packet: the binary transport (V8) takes up to <paramref name="cap"/>, the V1 fallback at most <see cref="V1BatchLimit"/>.</summary>
        internal static int FullPacket(int cap, int maxPacketEvents, bool binaryTransport)
        {
            var full = Math.Min(cap, maxPacketEvents);
            return binaryTransport ? full : Math.Min(full, V1BatchLimit);
        }
    }
}
