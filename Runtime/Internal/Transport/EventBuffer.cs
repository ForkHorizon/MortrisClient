using System;

namespace Daliys.Analytics.Internal.Transport
{
    /// <summary>
    /// The in-memory stage between <c>Track()</c> and the durable queue: event records are appended under a short lock and handed to the queue in
    /// one call every few hundred milliseconds. Frame layout (what the Java queue reads): per record <c>int32 length (big-endian)</c> then the record.
    /// </summary>
    internal sealed class EventBuffer
    {
        private readonly object _sync = new object();
        /// <summary>A buffer array bigger than this is given back after it was drained.</summary>
        private const int ShrinkAbove = 256 * 1024;
        private byte[] _data = new byte[16 * 1024];
        private int _length, _count;

        internal EventBuffer(int maxCount, int maxBytes) { MaxCount = maxCount; MaxBytes = maxBytes; }

        internal int MaxCount { get; }
        internal int MaxBytes { get; }
        /// <summary>Extra room that lifecycle events may use after the buffer is full, so a burst of game events cannot hide a session boundary.</summary>
        internal const int PriorityHeadroom = 64;

        internal int Count { get { lock (_sync) return _count; } }

        internal bool TryAppend(byte[] record, int length, bool priority = false)
        {
            lock (_sync)
            {
                var limit = priority ? MaxCount + PriorityHeadroom : MaxCount;
                if (_count >= limit || _length + 4 + length > MaxBytes + (priority ? 64 * 1024 : 0)) return false;
                Ensure(4 + length);
                _data[_length] = (byte)(length >> 24); _data[_length + 1] = (byte)(length >> 16); _data[_length + 2] = (byte)(length >> 8); _data[_length + 3] = (byte)length;
                Buffer.BlockCopy(record, 0, _data, _length + 4, length);
                _length += 4 + length;
                _count++;
                return true;
            }
        }

        /// <summary>Removes and returns everything buffered as an exactly sized frame array (empty array when nothing was buffered).</summary>
        internal byte[] Drain(out int count)
        {
            lock (_sync)
            {
                count = _count;
                if (count == 0) return Array.Empty<byte>();
                var frame = new byte[_length];
                Buffer.BlockCopy(_data, 0, frame, 0, _length);
                _length = 0; _count = 0;
                if (_data.Length > ShrinkAbove) _data = new byte[16 * 1024];   // a burst grew the array; do not keep it for the rest of the process
                return frame;
            }
        }

        /// <summary>Puts a drained frame back in front of whatever arrived since (the queue refused it).</summary>
        internal void Restore(byte[] frame, int count)
        {
            if (count == 0) return;
            lock (_sync)
            {
                var combined = new byte[Math.Max(_data.Length, frame.Length + _length)];
                Buffer.BlockCopy(frame, 0, combined, 0, frame.Length);
                Buffer.BlockCopy(_data, 0, combined, frame.Length, _length);
                _data = combined;
                _length += frame.Length;
                _count += count;
            }
        }

        internal void Clear()
        {
            lock (_sync) { _length = 0; _count = 0; }
        }

        private void Ensure(int extra)
        {
            if (_length + extra <= _data.Length) return;
            var size = _data.Length;
            while (size < _length + extra) size *= 2;
            Array.Resize(ref _data, size);
        }
    }
}
